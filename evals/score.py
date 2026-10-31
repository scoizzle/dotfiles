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

The one exception is a case marked `"must_pass": true`, which has no expected
defects and asserts the opposite direction: the reviewer must not report a 🔴 or
🟠 on a change that is known clean. 🟡 and 🟢 stay unscored, as above.

Exit code is 1 when any expected finding was missed, or when a `must_pass` case
reports a blocking finding, so this can gate a change.
"""
from __future__ import annotations

import json
import os
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# `opencode run` prints `> agent · model` before each message. Match the whole
# line so a markdown blockquote that happens to contain ` · ` cannot truncate the
# report and hide a finding.
MARKER = re.compile(r"^>\s+\S+\s·\s+\S+\s*$")
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


FENCE = re.compile(r"^\s*(?:```|~~~)")
BLOCKING = ("🔴", "🟠")
NEGATION = re.compile(r"\b(?:no|not|none|zero|without|nothing)\b", re.I)


def blocking_findings(report: str) -> list[str]:
    """Report lines, outside fenced code blocks, that name a blocking severity.

    Fail-closed on formatting: the marker counts wherever it appears on the line,
    not only at the start of a bullet. A bolded, numbered, or quoted finding is
    still a finding, and a gate that misses one is worse than a gate that flags a
    report which quotes the severity legend. Fenced blocks are skipped because
    repro output is not a claim.

    A line whose negation comes before its first marker ("no 🔴 or 🟠 findings")
    is a statement of cleanliness, not a finding.
    """
    out, fenced = [], False
    for line in ANSI.sub("", report).splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        first = min((line.find(mark) for mark in BLOCKING if mark in line), default=-1)
        if first < 0:
            continue
        if NEGATION.search(line[:first]):
            continue
        out.append(line.strip()[:200])
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
    clean_passed = clean_failed = 0

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
            if case.get("must_pass"):
                flagged = blocking_findings(report)
                print(f"== {case['id']}  (clean)  [{name[:-4]}]")
                if case.get("expected"):
                    print("   warning: must_pass ignores expected[]")
                if not report.strip():
                    clean_failed += 1
                    print("   clean: FAIL (no report)")
                    any_missed = True
                elif flagged:
                    clean_failed += 1
                    print("   clean: FAIL")
                    for line in flagged:
                        print(f"     ❌ blocking finding on a clean change: {line}")
                        any_missed = True
                else:
                    clean_passed += 1
                    print("   clean: PASS")
                for line in headings(report):
                    print(f"     · {line}")
                print()
                continue
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
    if clean_passed or clean_failed:
        print(f"CLEAN {clean_passed} passed, {clean_failed} failed")
    return 1 if any_missed else 0


if __name__ == "__main__":
    sys.exit(main())
