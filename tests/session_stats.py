#!/usr/bin/env python3
"""evals/session_stats.py compares harness versions on real use.

It reads the opencode session store read-only and reports, per window: active
days, top-level sessions per day, list cost per day, tokens per day and children
per session, split into real work and temp/eval directories. The v1 baseline
(2026-11-14 to 11-21) was 54 sessions and $9.19 a day; the v2 trial week is
compared against it with the same query.
"""
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "evals" / "session_stats.py"
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


DAY = 86_400_000
T0 = 1_795_000_000_000  # a fixed instant; windows are given in ms below


def make_db(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE session_v2 (id TEXT, parent_id TEXT, directory TEXT, cost REAL,
                  tokens_input INTEGER, tokens_output INTEGER, tokens_cache_read INTEGER,
                  time_created INTEGER, time_updated INTEGER)""")
    rows = [
        # window A: two real top-level sessions on day 0 (one with a child), one on day 1, one temp
        ("a1", None, "/Users/x/Projects/Poly", 1.00, 100, 10, 900, T0, T0 + 60_000),
        ("a1c", "a1", "/Users/x/Projects/Poly", 0.50, 50, 5, 0, T0 + 1000, T0 + 2000),
        ("a2", None, "/Users/x/dotfiles", 2.00, 200, 20, 0, T0 + 3_600_000, T0 + 3_700_000),
        ("a3", None, "/Users/x/dotfiles", 3.00, 300, 30, 0, T0 + DAY, T0 + DAY + 1),
        ("at", None, "/private/var/folders/q/T/opencode/evals-run/co", 9.00, 1, 1, 0, T0 + 5, T0 + 6),
        # window B
        ("b1", None, "/Users/x/dotfiles", 4.00, 400, 40, 0, T0 + 10 * DAY, T0 + 10 * DAY + 1),
    ]
    db.executemany("INSERT INTO session_v2 VALUES (?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    db.close()


def run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    check(TOOL.is_file(), "evals/session_stats.py exists")
    if not TOOL.is_file():
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    with tempfile.TemporaryDirectory() as raw:
        db = Path(raw) / "opencode.db"
        make_db(db)
        before = db.read_bytes()
        code, out = run("--db", str(db), "--json",
                        "--window", f"A={T0}:{T0 + 2 * DAY}", "--window", f"B={T0 + 10 * DAY}:{T0 + 11 * DAY}")
        check(code == 0, f"it runs (exit {code}): {out[-300:]}")
        try:
            data = {w["name"]: w for w in json.loads(out)}
        except ValueError:
            data = {}
        a = data.get("A", {})
        real = a.get("real", {})
        check(real.get("sessions") == 3, f"window A counts 3 real top-level sessions ({real.get('sessions')})")
        check(real.get("active_days") == 2, f"window A has 2 active days ({real.get('active_days')})")
        check(real.get("sessions_per_day") == 1.5, f"window A: 1.5 sessions a day ({real.get('sessions_per_day')})")
        check(real.get("cost") == 6.5, f"window A cost includes the child session ({real.get('cost')})")
        check(real.get("cost_per_day") == 3.25, f"window A: $3.25 a day ({real.get('cost_per_day')})")
        check(real.get("children_per_session") == round(1 / 3, 2), f"window A: children per session ({real.get('children_per_session')})")
        check(real.get("tokens") == 100 + 10 + 900 + 50 + 5 + 200 + 20 + 300 + 30, f"window A tokens ({real.get('tokens')})")
        check(a.get("temp", {}).get("sessions") == 1, "a session under /private/var/folders counts as temp, not real")
        check(data.get("B", {}).get("real", {}).get("sessions") == 1, "window B is separate")
        check(db.read_bytes() == before, "the store is opened read-only and left unchanged")
        code, out = run("--db", str(db), "--window", f"A={T0}:{T0 + 2 * DAY}")
        check(code == 0 and "A" in out and "3.25" in out, "the default output is a readable table")
        code, out = run("--db", str(Path(raw) / "missing.db"), "--window", f"A={T0}:{T0 + 1}")
        check(code == 2, "a missing store exits 2")
    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
