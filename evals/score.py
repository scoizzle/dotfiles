#!/usr/bin/env python3
"""Grade golden-set results against each case's expected findings.

    ./score.py <run-dir>            # a directory written by run.sh

Reads <run-dir>/results/<case>/<model>.txt, keeps only the reviewer's final
report, and checks each expected finding for its file (when the case names one)
plus its concept patterns.

This measures RECALL ONLY. It answers "did the reviewer surface the defect this
artifact introduced". It deliberately does not score precision: a finding about a
file the diff never touched may be a legitimate cross-boundary catch rather than
noise, so unmatched findings are listed for a human to judge.

Exit code is 1 when any expected finding was missed, so this can gate a change.
"""
from __future__ import annotations

import json
import os
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MARKER = re.compile(r"^>\s")
TRAILER = re.compile(r"^\[(?:eval|bakeoff\d?)\]")


def final_report(text: str) -> str:
    """Return the text of the reviewer's last message.

    opencode run prints each message after a `> agent · model` marker, so the
    last marker separates the final answer from the transcript. Falling back to
    the whole text keeps the scorer useful if that marker changes.
    """
    text = ANSI.sub("", text)
    lines = [line for line in text.splitlines() if not TRAILER.match(line)]
    last = -1
    for index, line in enumerate(lines):
        if MARKER.match(line):
            last = index
    return "\n".join(lines[last + 1:] if last >= 0 else lines)


def load_cases(cases_dir: str) -> list[dict]:
    cases = []
    for name in sorted(os.listdir(cases_dir)):
        cfg = os.path.join(cases_dir, name, "case.json")
        if os.path.exists(cfg):
            with open(cfg) as handle:
                case = json.load(handle)
            case.setdefault("id", name)
            cases.append(case)
    return cases


def expected_files(case_entry: dict) -> list[str]:
    names = case_entry.get("files")
    if names:
        return [str(name).lower() for name in names]
    single = case_entry.get("file")
    return [single.lower()] if single else []


def grade(case: dict, report: str) -> tuple[list[dict], list[dict]]:
    low = report.lower()
    found, missed = [], []
    for expected in case.get("expected", []):
        names = expected_files(expected)
        ok_file = not names or any(name in low for name in names)
        ok_patterns = all(re.search(p, report, re.I) for p in expected.get("require", []))
        (found if (ok_file and ok_patterns) else missed).append(expected)
    return found, missed


def headings(report: str) -> list[str]:
    """Severity-tagged lines, used to show what the reviewer actually claimed."""
    out = []
    for line in report.splitlines():
        stripped = line.strip()
        if re.match(r"^(?:[-*]\s*)?(?:#{1,4}\s*)?(?:🔴|🟠|🟡|🟢)", stripped):
            out.append(re.sub(r"[*#]", "", stripped)[:150])
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    run_dir = sys.argv[1]
    results = os.path.join(run_dir, "results")
    if not os.path.isdir(results):
        results = run_dir
    cases_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases")

    model = ""
    model_file = os.path.join(run_dir, "model")
    if os.path.exists(model_file):
        model = open(model_file).read().strip()

    print(f"golden set: {cases_dir}")
    if model:
        print(f"model:      {model}")
    print()

    any_missed = False
    got = want = 0

    for case in load_cases(cases_dir):
        case_dir = os.path.join(results, case["id"])
        if not os.path.isdir(case_dir):
            continue
        if os.path.exists(os.path.join(case_dir, "FAILED")):
            kind = case.get("artifact", "change")
            print(f"== {case['id']}  ({kind})  [FAILED]")
            print("   failed before a review result")
            any_missed = True
            want += len(case.get("expected", []))
            continue
        for name in sorted(os.listdir(case_dir)):
            if not name.endswith(".txt"):
                continue
            report = final_report(open(os.path.join(case_dir, name), errors="replace").read())
            found, missed = grade(case, report)
            total = len(case.get("expected", []))
            got += len(found)
            want += total

            kind = case.get("artifact", "change")
            print(f"== {case['id']}  ({kind})  [{name[:-4]}]")
            print(f"   recall {len(found)}/{total}")
            for item in found:
                print(f"     ✅ {item['severity']} {item['id']}")
            for item in missed:
                print(f"     ❌ {item['severity']} {item['id']}  <- {item['notes']}")
                any_missed = True
            for line in headings(report):
                print(f"     · {line}")
            print()

    if want:
        print(f"TOTAL {got}/{want} expected findings recovered")
    return 1 if any_missed else 0


if __name__ == "__main__":
    sys.exit(main())
