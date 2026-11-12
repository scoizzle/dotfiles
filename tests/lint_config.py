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

        # The advisor consult band: no native fallback, its own pin, a capped packet
        # and answer, a per-stream cap, a named-trigger vocabulary, and a role branch.
        advisor_path = tree / "agents" / "advisor.md"
        advisor_original = advisor_path.read_text()
        try:
            advisor_path.write_text("".join(
                line for line in advisor_original.splitlines(True)
                if not line.startswith("decision:")))
            failed |= not expect("advisor.md missing an output key", lint(tree), "output keys")
        finally:
            advisor_path.write_text(advisor_original)

        try:
            edit(advisor_path, "model: claude-agent/fable#medium", "model: claude-agent/sonnet#medium")
            failed |= not expect("advisor.md drifted pin", lint(tree), "pin must be")
        finally:
            advisor_path.write_text(advisor_original)

        try:
            policy = json.loads(original)
            policy["readonly_agents"]["models"]["advisor"] = "sonnet"
            policy_path.write_text(json.dumps(policy, indent=2) + "\n")
            failed |= not expect("advisor added to readonly_agents.models", lint(tree), "not in models")
        finally:
            policy_path.write_text(original)

        try:
            kept = "".join(line for line in agents_original.splitlines(True)
                           if not line.startswith("| advisor |"))
            if kept == agents_original:
                raise AssertionError("AGENTS.md: no | advisor | row to remove")
            agents_path.write_text(kept)
            failed |= not expect("AGENTS.md advisor row removed", lint(tree), "no routing row")
        finally:
            agents_path.write_text(agents_original)

        try:
            edit(agents_path, "per trigger occurrence and at most 3 per stream",
                 "per trigger occurrence and at most 4 per stream")
            failed |= not expect("AGENTS.md advisor cap drifted", lint(tree), "cap sentence")
        finally:
            agents_path.write_text(agents_original)

        try:
            edit(build_path, "per trigger occurrence and at most 3 per stream",
                 "per trigger occurrence and at most 4 per stream")
            failed |= not expect("build.md advisor cap drifted", lint(tree), "cap sentence")
        finally:
            build_path.write_text(build_original)

        try:
            edit(advisor_path, "per trigger occurrence and at most 3 per stream",
                 "per trigger occurrence and at most 4 per stream")
            failed |= not expect("advisor.md cap sentence drifted", lint(tree), "cap sentence")
        finally:
            advisor_path.write_text(advisor_original)

        try:
            edit(advisor_path, "at most 6 paths", "6 paths")
            failed |= not expect("advisor.md READ ALLOWED cap removed", lint(tree), "missing the cap")
        finally:
            advisor_path.write_text(advisor_original)

        # The advisor's PROMPT line: a T3 child never loads agents/advisor.md, so
        # build.md must say the PROMPT: line is required for it too.
        try:
            edit(build_path, "review, explore and advisor units", "review and explore units")
            failed |= not expect("build.md PROMPT rationale dropped the advisor", lint(tree),
                                 "advisor PROMPT")
        finally:
            build_path.write_text(build_original)

        # (j) The template line an orchestrator actually copies must name advisor.md;
        # the rationale can stay while the template loses it.
        try:
            edit(build_path, "an advisor unit reads advisor.md", "an advisor unit reads its prompt")
            failed |= not expect("build.md template PROMPT line dropped advisor.md", lint(tree),
                                 "advisor PROMPT")
        finally:
            build_path.write_text(build_original)

        # (k) AGENTS.md's PROMPT clause must name agents/advisor.md too.
        try:
            edit(agents_path, "`agents/advisor.md`). With no T3", "its own prompt). With no T3")
            failed |= not expect("AGENTS.md PROMPT clause dropped agents/advisor.md", lint(tree),
                                 "advisor PROMPT")
        finally:
            agents_path.write_text(agents_original)

        # (l) The dispute definition must be symmetric: either reviewer can be the
        # one who raised or the one who contradicted.
        try:
            agents_path.write_text(agents_original +
                                   "\nA dispute is a finding `review-deep` raised and "
                                   "`second-opinion` explicitly contradicted at triage.\n")
            failed |= not expect("AGENTS.md one-directional dispute definition", lint(tree),
                                 "dispute direction")
        finally:
            agents_path.write_text(agents_original)

        try:
            start = build_original.index("- `ROLE: advisor unit`")
            end = build_original.index("- `ROLE:", start + 1)
            build_path.write_text(build_original[:start] + build_original[end:])
            failed |= not expect("build.md advisor role branch removed", lint(tree),
                                 "ROLE: advisor unit")
        finally:
            build_path.write_text(build_original)

        readme_path = tree / "README.md"
        readme_original = readme_path.read_text()
        try:
            readme_path.write_text(readme_original + "\nThe advisor moment 2 rule still applies.\n")
            failed |= not expect("README.md numbered advisor moment", lint(tree),
                                 "numbered advisor moment")
        finally:
            readme_path.write_text(readme_original)

        try:
            agents_path.write_text(agents_original + "\nThe Advisor moment 2 rule still applies.\n")
            failed |= not expect("AGENTS.md capitalised numbered advisor moment", lint(tree),
                                 "numbered advisor moment")
        finally:
            agents_path.write_text(agents_original)

        try:
            agents_path.write_text(agents_original + "\nAn Advisor Moment still applies.\n")
            failed |= not expect("AGENTS.md case-drifted advisor moment", lint(tree),
                                 "numbered advisor moment")
        finally:
            agents_path.write_text(agents_original)

        # The four advisor triggers: a stale three-trigger list anywhere the
        # contract names them, and the converge gates it must state.
        try:
            edit(agents_path, "at four named triggers (fork, stuck, dispute, converge); packet",
                 "at three named triggers (fork, stuck, dispute); packet")
            failed |= not expect("AGENTS.md routing row back to three triggers", lint(tree),
                                 "advisor trigger list")
        finally:
            agents_path.write_text(agents_original)

        try:
            edit(agents_path, "(fork, stuck, dispute, converge); packet", "(fork, stuck, dispute); packet")
            failed |= not expect("AGENTS.md routing row dropped converge", lint(tree),
                                 "advisor trigger list")
        finally:
            agents_path.write_text(agents_original)

        try:
            if "oscillation" not in advisor_original:
                raise AssertionError("agents/advisor.md: no oscillation gate to remove")
            advisor_path.write_text(advisor_original.replace("oscillation", "repetition"))
            failed |= not expect("advisor.md oscillation gate removed", lint(tree), "converge gate")
        finally:
            advisor_path.write_text(advisor_original)

        try:
            if "at most one converge extension per stream" not in build_original:
                raise AssertionError("agents/build.md: no converge ceiling to drop")
            build_path.write_text(
                build_original.replace("at most one converge extension per stream",
                                       "at most two converge extensions per stream"))
            failed |= not expect("build.md converge ceiling dropped", lint(tree), "converge gate")
        finally:
            build_path.write_text(build_original)

        # The AGENTS.md advisor bullet's own trigger list: the anchor must stop
        # before the separate converge bullet, which always names converge.
        try:
            edit(agents_path, "and `converge` (the", "")
            failed |= not expect("AGENTS.md advisor bullet dropped converge", lint(tree),
                                 "advisor trigger list")
        finally:
            agents_path.write_text(agents_original)

        # The build.md trigger sentence alone: the next sentence always names
        # converge, and the stale regex must catch the backticked three-trigger form.
        try:
            edit(build_path, "`dispute` or `converge`", "`dispute`")
            failed |= not expect("build.md trigger sentence dropped converge", lint(tree),
                                 "advisor trigger list")
        finally:
            build_path.write_text(build_original)

        # The converge gates are checked in build.md too, not only AGENTS.md and
        # advisor.md.
        try:
            if "oscillation" not in build_original:
                raise AssertionError("agents/build.md: no oscillation gate to remove")
            build_path.write_text(build_original.replace("oscillation", "repetition"))
            failed |= not expect("build.md oscillation gate removed", lint(tree), "converge gate")
        finally:
            build_path.write_text(build_original)

        # Every remaining anchor/marker gets its own mutation.
        readme_path = tree / "README.md"
        readme_original = readme_path.read_text()
        try:
            edit(readme_path, "(fork, stuck, dispute, converge)", "(fork, stuck, dispute)")
            failed |= not expect("README.md trigger list dropped converge", lint(tree),
                                 "advisor trigger list")
        finally:
            readme_path.write_text(readme_original)

        try:
            edit(advisor_path, "or a converge extension past the re-review cap",
                 "past the re-review cap")
            failed |= not expect("advisor.md description dropped converge", lint(tree),
                                 "advisor trigger list")
        finally:
            advisor_path.write_text(advisor_original)

        try:
            start = advisor_original.index("## Triggers")
            end = advisor_original.index("\nCap:", start)
            section = advisor_original[start:end]
            if "converge" not in section:
                raise AssertionError("agents/advisor.md: no converge bullet to remove")
            advisor_path.write_text(advisor_original[:start]
                                    + section.replace("converge", "extension")
                                    + advisor_original[end:])
            failed |= not expect("advisor.md triggers section dropped converge", lint(tree),
                                 "advisor trigger list")
        finally:
            advisor_path.write_text(advisor_original)

        try:
            edit(agents_path, "The ceiling is at most one converge extension per stream.",
                 "The ceiling is at most two converge extensions per stream.")
            failed |= not expect("AGENTS.md converge ceiling drifted", lint(tree), "converge gate")
        finally:
            agents_path.write_text(agents_original)

        try:
            edit(advisor_path, "The ceiling is at most one converge extension per stream;",
                 "The ceiling is at most two converge extensions per stream;")
            failed |= not expect("advisor.md converge ceiling drifted", lint(tree), "converge gate")
        finally:
            advisor_path.write_text(advisor_original)
    print("FAIL" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
