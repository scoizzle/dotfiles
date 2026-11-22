#!/usr/bin/env python3
"""dream stops drafting into a queue nobody has read for two weeks.

By 2026-11-21 dream had staged 12 pending files since the last promote on
2026-11-02, and agents do not read pending/, so none of it had reached a
session. v2 Phase 9: when the oldest pending file is over 14 days old and no
dated file has been promoted in 14 days, staging stops with a message to
promote first. --promote is never blocked.
"""
import datetime
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DREAM = ROOT / "bin" / "dream"
FAILURES = []
TODAY = datetime.datetime.now(datetime.timezone.utc).date()


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def day(offset: int) -> str:
    return (TODAY - datetime.timedelta(days=offset)).isoformat()


def memory(tmp: Path, name: str, promoted: list[int], pending: list[int]) -> Path:
    root = tmp / name
    (root / "learnings" / "pending").mkdir(parents=True)
    (root / "core").mkdir()
    for offset in promoted:
        (root / "learnings" / f"{day(offset)}.md").write_text("- known: x [loop]\n")
    for offset in pending:
        (root / "learnings" / "pending" / f"{day(offset)}.md").write_text("- known: y [loop]\n")
    return root


def dream(mem: Path, *extra: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(DREAM), "--memory", str(mem), "--source", "opencode",
            "--db", str(mem / "no-such.db"), *extra]
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


with tempfile.TemporaryDirectory() as raw:
    tmp = Path(raw)

    stale = memory(tmp, "stale", promoted=[20], pending=[18, 3])
    r = dream(stale)
    check(r.returncode == 0, f"a stale queue is not an error (got {r.returncode})")
    check("promote first" in r.stdout, "a stale queue stops drafting and says to promote first")
    check(day(18) in r.stdout, "the message names the oldest unread pending file")

    never = memory(tmp, "never", promoted=[], pending=[16])
    check("promote first" in dream(never).stdout, "a queue with no promote ever, over 14 days old, is stale too")

    fresh = memory(tmp, "fresh", promoted=[20], pending=[5])
    check("promote first" not in dream(fresh).stdout, "a pending queue under 14 days old keeps drafting")

    recent = memory(tmp, "recent", promoted=[2], pending=[18])
    check("promote first" not in dream(recent).stdout, "a promote in the last 14 days keeps drafting")

    empty = memory(tmp, "empty", promoted=[40], pending=[])
    check("promote first" not in dream(empty).stdout, "no pending files is not stale")

    r = subprocess.run([sys.executable, str(DREAM), "--memory", str(stale), "--promote", "--dry-run"],
                       capture_output=True, text=True, timeout=120)
    check("promote first" not in r.stdout + r.stderr, "--promote is never blocked by the cadence check")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
