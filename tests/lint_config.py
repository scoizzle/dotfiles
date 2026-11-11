#!/usr/bin/env python3
"""bin/lint-config must pass on the tree and must fail when a policy surface
drifts: the native fallback models in policy/permissions.json or in the AGENTS.md
fallback bullet, a default-mode role branch that lost its TIER: stop, or the
plan-review-deep trigger-code list."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def lint(tree: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(tree / "bin" / "lint-config"), str(tree)],
                          capture_output=True, text=True)


def expect(name: str, run: subprocess.CompletedProcess, marker: str) -> bool:
    out = run.stdout + run.stderr
    if run.returncode != 1 or marker not in out:
        print(f"FAIL: {name}: rc={run.returncode}, expected 1 mentioning {marker!r}\n{out}")
        return False
    print(f"ok {name}")
    return True


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise AssertionError(f"{path}: missing {old!r}")
    path.write_text(text.replace(old, new, 1))


def main() -> int:
    failed = False
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "repo"
        shutil.copytree(ROOT, tree, symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        run = lint(tree)
        if run.returncode != 0:
            print(f"FAIL: unmodified copy: rc={run.returncode}\n{run.stdout}{run.stderr}")
            failed = True
        policy_path = tree / "policy" / "permissions.json"
        original = policy_path.read_text()
        for name in ("explore", "second-opinion"):
            policy = json.loads(original)
            current = policy["readonly_agents"]["models"][name]
            policy["readonly_agents"]["models"][name] = "opus" if current != "opus" else "haiku"
            policy_path.write_text(json.dumps(policy, indent=2) + "\n")
            run = lint(tree)
            out = run.stdout + run.stderr
            if run.returncode != 1 or "readonly_agents" not in out:
                print(f"FAIL: drifted {name} model: rc={run.returncode}, expected 1 mentioning readonly_agents\n{out}")
                failed = True
            else:
                print(f"ok drift detected: {name}")
        policy_path.write_text(original)

        # The fallback map is the bullet, not the whole file: a stray later line
        # must not mask drift in the bullet.
        agents_path = tree / "AGENTS.md"
        agents_original = agents_path.read_text()
        try:
            edit(agents_path, "`explore`=`haiku`.", "`explore`=`opus`.")
            agents_path.write_text(agents_path.read_text() + "\n`explore`=`haiku` is the old value.\n")
            failed |= not expect("AGENTS.md bullet drift masked by a later line", lint(tree), "fallback map")
        finally:
            agents_path.write_text(agents_original)

        keep = agents_path.read_text()
        try:
            edit(agents_path, "`review-deep`=`sonnet`", "`review-deep`=`haiku`")
            failed |= not expect("AGENTS.md bullet drift", lint(tree), "fallback map")
        finally:
            agents_path.write_text(keep)

        # Every default-mode role branch keeps its own TIER: stop; an extra copy
        # elsewhere does not replace the one that drifted.
        build_path = tree / "agents" / "build.md"
        build_original = build_path.read_text()
        try:
            edit(build_path,
                 "`ROLE: integrate unit` — a brief with no `TIER:` line naming a tier and a band:\n"
                 "  stop and report, do no work.",
                 "`ROLE: integrate unit` — a brief with no `TIER:` line naming a tier and a band:")
            edit(build_path, "Branch on the `ROLE:` prefix:",
                 "Branch on the `ROLE:` prefix; stop and report, do no work on a brief with no TIER: line.")
            failed |= not expect("build.md integrate branch lost its TIER: stop", lint(tree), "integrate unit branch")
        finally:
            build_path.write_text(build_original)

        # Only the three implement-deep trigger codes are valid: each file that
        # states the list is checked, not just plan-review-deep.
        review_path = tree / "agents" / "plan-review-deep.md"
        review_original = review_path.read_text()
        try:
            edit(review_path, "`security-logic`.", "`security-logic`, `performance`.")
            failed |= not expect("plan-review-deep fourth trigger code", lint(tree),
                                 "agents/plan-review-deep.md: unknown implement-deep trigger code")
        finally:
            review_path.write_text(review_original)

        # The separator sentence sits after the code list's terminator, so the
        # lint must read the list span, not the whole file, and still catch a
        # fourth code there.
        try:
            edit(agents_path, "`security-logic`;", "`security-logic`, `performance`;")
            failed |= not expect("AGENTS.md fourth trigger code", lint(tree),
                                 "AGENTS.md: unknown implement-deep trigger code")
        finally:
            agents_path.write_text(agents_original)

        try:
            edit(build_path, "`security-logic`. The separator", "`security-logic`, `performance`. The separator")
            failed |= not expect("build.md fourth trigger code", lint(tree),
                                 "agents/build.md: unknown implement-deep trigger code")
        finally:
            build_path.write_text(build_original)

        # A code list missing one of the three fails, and a list whose `<code>`
        # anchor is gone fails as no list at all.
        try:
            edit(agents_path, "`no-oracle`, ", "")
            failed |= not expect("AGENTS.md missing trigger code", lint(tree),
                                 "AGENTS.md: missing the implement-deep trigger code")
        finally:
            agents_path.write_text(agents_original)

        try:
            edit(build_path, "with `<code>` one of", "with code one of")
            failed |= not expect("build.md missing code list", lint(tree),
                                 "agents/build.md: missing the implement-deep code list")
        finally:
            build_path.write_text(build_original)
    print("FAIL" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
