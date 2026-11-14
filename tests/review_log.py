#!/usr/bin/env python3
"""Contract for bin/review-log: append, resolve and --list-pending.

Run from the repo root: python3 tests/review_log.py

Every case uses a temp ledger; the real ~/.config/opencode/reviews.jsonl is
never touched. --list-pending is read-only: the ledger bytes stay identical.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_LOG = ROOT / "bin" / "review-log"
MALFORMED = "{not json at all"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def run(ledger: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REVIEW_LOG), "--ledger", str(ledger), *args],
        capture_output=True, text=True,
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "reviews.jsonl"

        # append
        a = run(ledger, "--tier", "T1", "--model", "review-light",
                "--red", "1", "--amber", "2", "--yellow", "3", "--pending")
        b = run(ledger, "--tier", "T2", "--artifact", "plan", "--model", "review-deep",
                "--amber", "1", "--pending")
        c = run(ledger, "--tier", "T0", "--model", "review-light")
        check("append exits 0", a.returncode == b.returncode == c.returncode == 0,
              a.stderr + b.stderr + c.stderr)
        id_a, id_b = a.stdout.strip(), b.stdout.strip()
        entries = [json.loads(line) for line in lines(ledger)]
        check("append writes three lines", len(entries) == 3, str(entries))
        check("append records pending",
              [e.get("pending") for e in entries] == [True, True, False], str(entries))

        # a malformed line passes through unchanged
        with ledger.open("a") as handle:
            handle.write(MALFORMED + "\n")

        # resolve
        r = run(ledger, "--resolve", id_b, "--acted", "1", "--dismissed", "0")
        check("resolve exits 0", r.returncode == 0, r.stderr)
        by_id = {}
        for line in lines(ledger):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            by_id[entry["id"]] = entry
        check("resolve clears pending", by_id[id_b]["pending"] is False, str(by_id[id_b]))
        check("resolve leaves other line pending", by_id[id_a]["pending"] is True)
        check("malformed line survives resolve", MALFORMED in lines(ledger),
              str(lines(ledger)))

        # list-pending: count, row content, bytes unchanged
        before = digest(ledger)
        lp = run(ledger, "--list-pending")
        after = digest(ledger)
        check("list-pending exits 0", lp.returncode == 0, lp.stderr)
        out = lp.stdout.splitlines()
        rows = [line for line in out if line.split(" ", 1)[0] in by_id]
        check("list-pending lists one entry", len(rows) == 1 and rows[0].startswith(id_a), lp.stdout)
        check("list-pending row has tier artifact model counts",
              bool(rows) and all(t in rows[0].split() for t in ("T1", "change", "review-light", "1/2/3")),
              lp.stdout)
        check("list-pending prints count", bool(out) and out[-1] == "pending: 1", lp.stdout)
        check("list-pending leaves bytes unchanged", before == after)
        check("list-pending leaves no tmp file", not Path(f"{ledger}.tmp").exists())
        check("malformed line survives list-pending", MALFORMED in lines(ledger))

        # --fail-if-any exit code
        fa = run(ledger, "--list-pending", "--fail-if-any")
        check("--fail-if-any exits 1 with pending", fa.returncode == 1,
              f"rc={fa.returncode} {fa.stderr}")
        run(ledger, "--resolve", id_a, "--acted", "0", "--dismissed", "1")
        before = digest(ledger)
        fz = run(ledger, "--list-pending", "--fail-if-any")
        check("--fail-if-any exits 0 with none pending", fz.returncode == 0,
              f"rc={fz.returncode} {fz.stderr}")
        check("count is zero when none pending",
              fz.stdout.splitlines()[-1:] == ["pending: 0"], fz.stdout)
        check("list-pending (none) leaves bytes unchanged", before == digest(ledger))

        # missing ledger: list-pending does not create it
        missing = Path(tmp) / "absent.jsonl"
        m = run(missing, "--list-pending", "--fail-if-any")
        check("missing ledger exits 0 and is not created",
              m.returncode == 0 and not missing.exists(), f"rc={m.returncode} {m.stderr}")

    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("review-log ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
