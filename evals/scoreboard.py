#!/usr/bin/env python3
"""Scoreboard for the review gates, read from the local opencode session store.

    ./scoreboard.py                 # last 14 days
    ./scoreboard.py --days 30
    ./scoreboard.py --all           # lifetime, which doubles as the pre-gate baseline
    ./scoreboard.py --db /path/to/opencode.db

Opens the database read-only and reads `session_v2` only.

What it reports, and what it cannot:

- Reports which agent ran, what it cost, how long a review took, and how many
  parent sessions launched one. Those columns are reliable. Review agents counted:
  `reviewer`, `verifier`, `review-light`, `review-deep`, `plan-review-deep`,
  `second-opinion`.
- Reads yield and dismissal from the ledger the review gate appends to
  (`~/.config/opencode/reviews.jsonl`), not from `session_v2`. Reviewer
  transcripts are not persisted for `opencode run` sessions, so those metrics are
  logged at the source. If the ledger is absent, that section is skipped.
- Gate coverage is a proxy: reviewer launches over `build` sessions in the window.
  `build` is the primary that does work, so it stands in for "tasks that should
  have been reviewed". Treat the number as a floor, not an audit.

Cost delta from `cost.py` during a run is a different measurement; this is the
standing view.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import sys
import time

DEFAULT_DB = "~/.local/share/opencode/opencode.db"
DEFAULT_LEDGER = "~/.config/opencode/reviews.jsonl"


def read_ledger(path: str, since_ms: int) -> list[dict]:
    """Read the yield ledger. One JSON object per line. Returns entries in window."""
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        return []
    entries = []
    with open(resolved) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if since_ms:
                ts = entry.get("ts")
                if not isinstance(ts, str):
                    continue
                try:
                    when = datetime.datetime.fromisoformat(ts).timestamp() * 1000
                except ValueError:
                    continue
                if when < since_ms:
                    continue
            entries.append(entry)
    return entries


def as_int(value) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def connect(path: str) -> sqlite3.Connection:
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        sys.exit(f"no session store at {resolved}")
    return sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * q)))
    return ordered[index]


def rows(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    try:
        return connection.execute(sql, params).fetchall()
    except sqlite3.Error as error:
        sys.exit(f"query failed: {error}\n{sql.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--all", action="store_true", help="lifetime instead of a window")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--ledger", default=DEFAULT_LEDGER)
    args = parser.parse_args()

    connection = connect(args.db)
    since = 0 if args.all else int((time.time() - args.days * 86400) * 1000)
    label = "lifetime" if args.all else f"last {args.days} days"
    print(f"review gates · {label}")

    by_agent = rows(
        connection,
        """
        select coalesce(agent, '(none)') as agent,
               count(*) as runs,
               coalesce(sum(cost), 0) as cost,
               sum(case when parent_id is not null then 1 else 0 end) as children
        from session_v2
        where time_created >= ?
        group by 1
        order by cost desc
        """,
        (since,),
    )
    total_cost = sum(row[2] for row in by_agent) or 0.0

    print()
    print(f"{'agent':<10}{'runs':>7}{'cost':>10}{'$/run':>9}{'share':>8}{'children':>10}")
    for agent, runs, cost, children in by_agent:
        share = f"{(cost / total_cost * 100):.0f}%" if total_cost else "-"
        print(f"{agent:<10}{runs:>7}{cost:>10.2f}{(cost / runs if runs else 0):>9.3f}{share:>8}{children:>10}")
    print(f"{'TOTAL':<10}{'':>7}{total_cost:>10.2f}")

    review_cost, review_runs, parents, spans = rows(
        connection,
        """
        select coalesce(sum(cost), 0),
               count(*),
               count(distinct parent_id),
               coalesce(sum(case when time_updated > time_created
                                 then time_updated - time_created end), 0)
        from session_v2
        where agent in ('reviewer','verifier','review-light','review-deep','plan-review-deep','second-opinion') and time_created >= ?
        """,
        (since,),
    )[0]

    durations = [
        (row[0] or 0) / 1000.0
        for row in rows(
            connection,
            """
            select time_updated - time_created
            from session_v2
            where agent in ('reviewer','verifier','review-light','review-deep','plan-review-deep','second-opinion') and time_created >= ? and time_updated > time_created
            """,
            (since,),
        )
    ]

    build_sessions = rows(
        connection,
        "select count(*) from session_v2 where agent = 'build' and parent_id is null and time_created >= ?",
        (since,),
    )[0][0]

    days = max(1, (args.days if not args.all else _span_days(connection)))
    p50, p95 = percentile(durations, 0.5), percentile(durations, 0.95)

    print()
    print("gate")
    print(f"  reviewer runs              {review_runs}")
    print(f"  reviewer runs / day        {review_runs / days:.1f}")
    print(f"  reviewer cost              ${review_cost:.2f}"
          + (f"   ({(review_cost / total_cost * 100):.0f}% of spend)" if total_cost else ""))
    latency = f"{p50:.0f}s / {p95:.0f}s" if p50 is not None else "n/a"
    print(f"  review latency p50 / p95   {latency}")
    print(f"  parents that ran a review  {parents}")
    print(f"  build sessions in window   {build_sessions}")
    if build_sessions:
        print(f"  gate coverage (proxy)      {min(parents, build_sessions) / build_sessions * 100:.0f}%")

    ledger = read_ledger(args.ledger, since)
    if ledger:
        resolved = [entry for entry in ledger if not entry.get("pending")]
        pending = len(ledger) - len(resolved)
        reported = len(resolved)
        acted = sum(as_int(entry.get("acted")) for entry in resolved)
        dismissed = sum(as_int(entry.get("dismissed")) for entry in resolved)
        unique = sum(as_int(entry.get("unique")) for entry in resolved)
        # Yield is a share of actionable findings (nits are not actionable).
        # Dismissal is a share of all findings, nits included, because a nit can
        # be waved off too.
        actionable = sum(
            as_int(entry.get(key))
            for entry in resolved
            for key in ("red", "amber", "yellow")
        )
        all_findings = actionable + sum(as_int(entry.get("green")) for entry in resolved)
        print()
        print("yield (from reviews.jsonl)")
        print(f"  reviews resolved           {reported}")
        print(f"  reviews pending            {pending}")
        print(f"  findings reported          {all_findings}")
        print(f"  acted on                   {acted}")
        print(f"  dismissed                  {dismissed}")
        print(f"  unique (second opinion)    {unique}")
        if actionable:
            print(f"  yield (acted / actionable) {acted / actionable * 100:.0f}%")
        if all_findings:
            print(f"  dismissal (dismissed/all)  {dismissed / all_findings * 100:.0f}%")

        if resolved:
            print()
            print("yield by tier")
            for tier in ("T0", "T1", "T2", "(none)"):
                items = [entry for entry in resolved if entry.get("tier", "(none)") == tier]
                if not items:
                    continue
                tier_acted = sum(as_int(entry.get("acted")) for entry in items)
                tier_dismissed = sum(as_int(entry.get("dismissed")) for entry in items)
                tier_actionable = sum(
                    as_int(entry.get(key))
                    for entry in items
                    for key in ("red", "amber", "yellow")
                )
                if tier_actionable:
                    rate = tier_acted / tier_actionable * 100
                    print(
                        f"  {tier:<6} reviews {len(items):>3}  acted {tier_acted:>3}"
                        f"  dismissed {tier_dismissed:>3}  yield {rate:>3.0f}%"
                    )
                else:
                    print(
                        f"  {tier:<6} reviews {len(items):>3}  acted {tier_acted:>3}"
                        f"  dismissed {tier_dismissed:>3}  yield n/a"
                    )

    daily = rows(
        connection,
        """
        select date(time_created / 1000, 'unixepoch') as day,
               sum(agent in ('reviewer','verifier','review-light','review-deep','plan-review-deep','second-opinion')) as reviews,
               round(sum(case when agent in ('reviewer','verifier','review-light','review-deep','plan-review-deep','second-opinion') then cost else 0 end), 3) as cost
        from session_v2
        where time_created >= ?
        group by 1
        having reviews > 0
        order by 1 desc
        limit 14
        """,
        (since,),
    )
    if daily:
        print()
        print("reviews per day")
        for day, reviews, cost in daily:
            print(f"  {day}  {reviews:>3}  ${cost:.3f}")

    print()
    print("lifetime baseline (compare against it, not against zero)")
    base = rows(
        connection,
        """
        select coalesce(agent, '(none)'),
               count(*),
               coalesce(sum(cost), 0)
        from session_v2
        group by 1
        order by 3 desc
        """,
    )
    for agent, runs, cost in base:
        print(f"  {agent:<10}{runs:>7} runs  ${cost:>9.2f}  ${(cost / runs if runs else 0):>8.3f}/run")
    return 0


def _span_days(connection: sqlite3.Connection) -> int:
    row = rows(connection, "select min(time_created), max(time_created) from session_v2")[0]
    if not row or not row[0] or not row[1]:
        return 1
    return max(1, int((row[1] - row[0]) / 86400000))


if __name__ == "__main__":
    sys.exit(main())
