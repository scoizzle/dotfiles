#!/usr/bin/env python3
"""evals/compare.py ranks review arms only on repeated attempts.

A single run per case cannot rank anything: on the harness leaderboard a rerun
of the same harness flipped about a quarter of tasks. compare.py takes three or
more run directories per arm, scores each case-attempt with score.py's own
grader, reports each arm's pass rate and its rerun flip rate, and a paired
bootstrap CI for the difference between two arms. Fewer than three attempts
is refused. A report that quotes the case's answer key counts as a fail.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPARE = ROOT / "evals" / "compare.py"
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def make_cases(root: Path) -> Path:
    cases = root / "cases"
    for cid, case in {
        "bug-a": {"tier": "T1", "expected": [{"id": "x", "severity": "🟠", "require": ["off.by.one"], "notes": ""}]},
        "bug-b": {"tier": "T1", "expected": [{"id": "y", "severity": "🔴", "require": ["null deref"], "notes": ""}]},
        "clean": {"tier": "T2", "must_pass": True, "expected": []},
    }.items():
        (cases / cid).mkdir(parents=True)
        (cases / cid / "case.json").write_text(json.dumps(case))
    return cases


def make_run(root: Path, name: str, reports: dict[str, str]) -> Path:
    run = root / name
    for cid, text in reports.items():
        (run / "results" / cid).mkdir(parents=True)
        (run / "results" / cid / "m.txt").write_text(text)
    return run


GOOD = {"bug-a": "🟠 off by one in the loop", "bug-b": "🔴 null deref on load", "clean": "🟢 looks fine"}
WEAK = {"bug-a": "🟡 naming", "bug-b": "🟡 style", "clean": "🟠 invented problem"}
PARTIAL = {**GOOD, "bug-b": "🟡 style"}


def compare(cases: Path, *arms: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(COMPARE), "--cases", str(cases)]
    for arm in arms:
        argv += ["--arm", arm]
    return subprocess.run(argv, capture_output=True, text=True, timeout=60)


with tempfile.TemporaryDirectory() as raw:
    tmp = Path(raw)
    cases = make_cases(tmp)
    a = [make_run(tmp, f"a{i}", GOOD) for i in range(3)]
    b = [make_run(tmp, f"b{i}", WEAK) for i in range(3)]
    a_arm = "A=" + ",".join(map(str, a))
    b_arm = "B=" + ",".join(map(str, b))

    r = compare(cases, a_arm, b_arm)
    check(r.returncode == 0, f"three attempts per arm are accepted (got {r.returncode}: {r.stderr.strip()[-200:]})")
    out = r.stdout
    check("A  pass 9/9" in out, "arm A passes every case-attempt")
    check("B  pass 0/9" in out, "arm B fails every case-attempt")
    check("flip 0/3" in out, "identical attempts flip no case")
    check("A - B" in out and "excludes 0" in out, "a consistent gap gets a paired CI that excludes zero")

    r = compare(cases, "A=" + ",".join(map(str, a[:2])), b_arm)
    check(r.returncode == 2 and "at least 3 attempts" in r.stderr, f"two attempts are refused (got {r.returncode})")

    flaky = [make_run(tmp, "f0", GOOD), make_run(tmp, "f1", PARTIAL), make_run(tmp, "f2", GOOD)]
    r = compare(cases, "A=" + ",".join(map(str, a)), "F=" + ",".join(map(str, flaky)))
    check("F  pass 8/9" in r.stdout and "flip 1/3" in r.stdout, "a flaky arm reports its rerun flip rate")
    check("A - F" in r.stdout and "tied" in r.stdout, "one flip in nine is inside the noise: tied")

    leaky = {**GOOD, "bug-a": f"🟠 off by one, see {cases / 'bug-a' / 'case.json'}"}
    lk = [make_run(tmp, f"l{i}", leaky) for i in range(3)]
    r = compare(cases, "L=" + ",".join(map(str, lk)), a_arm)
    check("L  pass 6/9" in r.stdout, "a report that names the answer key fails that attempt")
    check("L - A" in r.stdout, "later arms are compared with the first")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
