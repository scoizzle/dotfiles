#!/usr/bin/env python3
"""Build the large writer cases from merged Poly PRs.

Each case's base is the integration merge (the fixed state). Its patch reverts
every file the merge changed except the behavioural oracle tests, so the fix's
own tests stay and fail, and test edits that pin implementation names are
reverted with the fix (a different correct fix must not fail them).
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "Projects" / "Poly" / "Poly"
OUT = Path(sys.argv[1])
FILTER = "dotnet run --project Poly.Tests/Poly.Tests.csproj -- --treenode-filter '/*/*/{cls}/*' --no-ansi"

CASES = [
    {"id": "large-numeric-builtins", "pr": 1088, "merge": "eb0bce7f6",
     "oracle": ["Poly.Tests/DomainModeling/Lowering/NumericBuiltinParityTests.cs"],
     "classes": ["NumericBuiltinParityTests"]},
    {"id": "large-create-entry-notify", "pr": 1053, "merge": "cfe2a4c0a",
     "oracle": ["Poly.Tests/DomainModeling/Lowering/CreateEntryNotificationParityTests.cs"],
     "classes": ["CreateEntryNotificationParityTests"]},
    {"id": "large-interval-precision", "pr": 1112, "merge": "5122652fa",
     # ExactIntervalTests pins the original fix's exact endpoints (review, 2026-11-23),
     # so it is reverted with the fix; the oracle is the behavioural write checks.
     "oracle": ["Poly.Tests/DomainModeling/Analysis/UnverifiedWriteTests.cs",
                "Poly.Tests/DomainModeling/Analysis/VerificationSummaryTests.cs"],
     "classes": ["UnverifiedWriteTests", "VerificationSummaryTests"]},
]


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout


def pr(number: int) -> dict:
    out = subprocess.run(["gh", "pr", "view", str(number), "--repo", "scoizzle/Poly", "--json", "title,body"],
                         check=True, capture_output=True, text=True, cwd=REPO).stdout
    return json.loads(out)


checks = {}
for case in CASES:
    merge = git("rev-parse", case["merge"]).strip()
    changed = [p for p in git("diff", "--name-only", f"{merge}^1", merge).splitlines() if p]
    revert = [p for p in changed if p not in case["oracle"]]
    patch = git("diff", "--binary", merge, f"{merge}^1", "--", *revert)
    meta = pr(case["pr"])
    body = meta["body"]
    cause = body.split("## Cause", 1)[1].split("\n## ", 1)[0].strip() if "## Cause" in body else body[:1500]
    prod_lines = sum(int(a) + int(b) for a, b, *_ in (l.split("\t") for l in git(
        "diff", "--numstat", f"{merge}^1", merge, "--", *revert).splitlines()) if a.isdigit())
    d = OUT / case["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "change.patch").write_text(patch)
    (d / "case.json").write_text(json.dumps({
        "id": case["id"],
        "tier": "T2",
        "repo": "~/Projects/Poly/Poly",
        "base": merge,
        "patch": "change.patch",
        "claim": meta["title"],
        "source": f"scoizzle/Poly#{case['pr']}, integration merge {merge[:9]}",
        "reverted_files": len(revert),
        "reverted_lines": prod_lines,
        "expected": [{"id": "fix", "severity": "🟠", "notes": cause[:2500]}],
    }, indent=2, ensure_ascii=False) + "\n")
    checks[case["id"]] = {
        "check": " && ".join(FILTER.format(cls=c) for c in case["classes"]),
        "protect": case["oracle"],
    }
    print(f"{case['id']}: base {merge[:9]}, reverts {len(revert)} files / {prod_lines} lines, oracle {len(case['oracle'])}")
(OUT / "writer-checks.json").write_text(json.dumps(checks, indent=2) + "\n")
