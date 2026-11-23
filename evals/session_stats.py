#!/usr/bin/env python3
"""Compare harness versions on real use, from the opencode session store.

    evals/session_stats.py --window v1=2026-11-14T22:42-06:00:2026-11-21T20:50-06:00 \\
                           --window v2=2026-11-23T00:00-06:00:2026-11-30T00:00-06:00

A window is NAME=START:END, each an ISO time (an offset is allowed) or epoch
milliseconds. Per window it reports top-level sessions, active days, sessions
per day, list cost per day (opencode's estimate from list price, not a bill;
it includes child sessions), tokens per day, and children per session, split
into real work and temp/eval directories (/private, /tmp, /var/folders).
Claude sessions run through T3's own Claude provider are not in this store.

The store is opened read-only. v1 baseline (2026-11-14 to 11-21): 54 sessions
and $9.19 a day, all sessions counted.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
TEMP_PREFIXES = ("/private/", "/tmp/", "/var/folders/")


def instant(text: str) -> int:
    if text.isdigit():
        return int(text)
    return int(datetime.datetime.fromisoformat(text).timestamp() * 1000)


def window(spec: str) -> tuple[str, int, int]:
    name, _, span = spec.partition("=")
    # The split point is the ':' that starts the end: an ISO time has colons of its own.
    for i, ch in enumerate(span):
        if ch == ":" and i > 0:
            try:
                return name, instant(span[:i]), instant(span[i + 1:])
            except ValueError:
                continue
    raise argparse.ArgumentTypeError(f"window must be NAME=START:END, got {spec!r}")


def kind(directory: str | None) -> str:
    return "temp" if (directory or "").startswith(TEMP_PREFIXES) else "real"


def stats(db: sqlite3.Connection, start: int, end: int) -> dict:
    rows = db.execute("SELECT id, parent_id, directory, cost, tokens_input, tokens_output, tokens_cache_read, time_created "
                      "FROM session_v2 WHERE time_created >= ? AND time_created < ?", (start, end)).fetchall()
    children: dict[str, list] = {}
    for r in rows:
        if r[1]:
            children.setdefault(r[1], []).append(r)
    out = {}
    for group in ("real", "temp"):
        top = [r for r in rows if not r[1] and kind(r[2]) == group]
        days = {datetime.datetime.fromtimestamp(r[7] / 1000).date() for r in top}
        family = top + [c for r in top for c in children.get(r[0], [])]
        cost = round(sum(r[3] or 0 for r in family), 2)
        tokens = sum((r[4] or 0) + (r[5] or 0) + (r[6] or 0) for r in family)
        n, d = len(top), len(days)
        out[group] = {
            "sessions": n,
            "active_days": d,
            "sessions_per_day": round(n / d, 2) if d else 0,
            "cost": cost,
            "cost_per_day": round(cost / d, 2) if d else 0,
            "tokens": tokens,
            "tokens_per_day": round(tokens / d) if d else 0,
            "children_per_session": round(sum(len(children.get(r[0], [])) for r in top) / n, 2) if n else 0,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--window", type=window, action="append", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.db.is_file():
        print(f"no session store at {args.db}", file=sys.stderr)
        return 2
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    result = [{"name": name, "start": start, "end": end, **stats(db, start, end)} for name, start, end in args.window]
    if args.json:
        print(json.dumps(result, indent=1))
        return 0
    cols = ("sessions", "active_days", "sessions_per_day", "cost_per_day", "tokens_per_day", "children_per_session")
    print(f"{'window':<10}{'kind':<6}" + "".join(f"{c:>22}" for c in cols))
    for w in result:
        for group in ("real", "temp"):
            print(f"{w['name']:<10}{group:<6}" + "".join(f"{w[group][c]:>22}" for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
