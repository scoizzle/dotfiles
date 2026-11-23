#!/usr/bin/env python3
"""Compare review arms over repeated attempts.

    ./compare.py --arm A=<run>,<run>,<run> --arm B=<run>,<run>,<run> [--cases DIR]

Each <run> is a directory written by run.sh. Every case-attempt
is scored with score.py's own grader and counts as a pass or a fail:

- a defect case passes when every expected finding is recovered;
- a must_pass case passes when its report has no blocking (🔴/🟠) finding;
- a missing or FAILED result fails;
- a report that names the case's answer key (its case.json or change.patch)
  fails, whatever it found: access to the answer is enough.

Per arm it prints the pass count and the rerun flip rate (cases whose outcome
differs between attempts). For each later arm it prints the paired difference
from the first arm, with a 95% bootstrap CI over cases; two arms are "tied"
unless that CI excludes zero.

One run per case cannot rank anything: on the harness leaderboard a rerun of the
same harness flipped about 25% of tasks. Fewer than 3 attempts per arm exits 2.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_loader = importlib.machinery.SourceFileLoader("score", str(HERE / "score.py"))
_spec = importlib.util.spec_from_loader("score", _loader)
score = importlib.util.module_from_spec(_spec)
_loader.exec_module(score)

MIN_ATTEMPTS = 3
ANSWER_FILES = ("case.json", "change.patch")


def attempt_passes(case: dict, run: Path, cases_dir: Path) -> bool:
    case_dir = run / "results" / case["id"]
    if not case_dir.is_dir() or (case_dir / "FAILED").exists():
        return False
    reports = sorted(case_dir.glob("*.txt"))
    if not reports:
        return False
    raw = reports[0].read_text(errors="replace")
    key = cases_dir / case["id"]
    if any(str(key / name) in raw or f"cases/{case['id']}/{name}" in raw for name in ANSWER_FILES):
        return False
    report = score.final_report(raw)
    if case.get("must_pass"):
        return bool(report.strip()) and not score.blocking_findings(report)
    _, missed = score.grade(case, report)
    return not missed


def bootstrap_ci(diffs: list[float], rounds: int = 10000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(rounds))
    return means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", action="append", required=True, help="NAME=run,run,run")
    parser.add_argument("--cases", default=str(HERE / "cases"))
    args = parser.parse_args(argv)

    cases_dir = Path(args.cases)
    cases = [c for c in score.load_cases(str(cases_dir)) if c.get("artifact", "change") == "change"]
    arms: list[tuple[str, list[Path]]] = []
    for spec in args.arm:
        name, _, runs = spec.partition("=")
        paths = [Path(p) for p in runs.split(",") if p]
        if len(paths) < MIN_ATTEMPTS:
            print(f"arm {name}: {len(paths)} attempt(s); need at least {MIN_ATTEMPTS} attempts per arm", file=sys.stderr)
            return 2
        arms.append((name, paths))

    # outcome[arm][case] = list of pass/fail per attempt
    outcome: dict[str, dict[str, list[bool]]] = {}
    for name, runs in arms:
        outcome[name] = {c["id"]: [attempt_passes(c, run, cases_dir) for run in runs] for c in cases}
        passes = sum(sum(v) for v in outcome[name].values())
        total = sum(len(v) for v in outcome[name].values())
        flips = sum(1 for v in outcome[name].values() if len(set(v)) > 1)
        print(f"{name}  pass {passes}/{total}  flip {flips}/{len(cases)}")
        for c in cases:
            marks = "".join("✓" if ok else "✗" for ok in outcome[name][c["id"]])
            print(f"    {c['id']:28} {marks}")

    first, base = arms[0][0], outcome[arms[0][0]]
    for name, _ in arms[1:]:
        diffs = [
            sum(base[c["id"]]) / len(base[c["id"]]) - sum(outcome[name][c["id"]]) / len(outcome[name][c["id"]])
            for c in cases
        ]
        mean = sum(diffs) / len(diffs)
        low, high = bootstrap_ci(diffs)
        verdict = "excludes 0" if low > 0 or high < 0 else "tied"
        print(f"{first} - {name}: {mean:+.2f} per case, 95% CI [{low:+.2f}, {high:+.2f}] {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
