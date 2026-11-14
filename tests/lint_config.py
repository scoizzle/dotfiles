#!/usr/bin/env python3
"""bin/lint-config must pass on the tree and must fail when a policy surface
drifts: the native fallback models in policy/permissions.json or in the AGENTS.md
fallback bullet, a default-mode role branch that lost its TIER: stop, the
plan-review-deep trigger-code list, the routing table's quota `fallback` column,
the EXECUTE ALLOWLIST set, the PROMPT: rationale's implementor unit, or a U7
anchor (the 🟡 rule, the plan-mode anchor, the prose-lane stop exception,
UNIT-BASE..sha, steps >= 120, squash-before-return, review-log --list-pending), or
agents/build.md losing its `AGENTS.md, Classify` reference or restating the
implement-deep trigger codes AGENTS.md owns (U8)."""

import json
import re
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

        # U8: AGENTS.md is the single source of the trigger and classify rules.
        # build.md must point at it, and must not restate the code list (a second
        # copy is what drifted before).
        try:
            text, count = re.subn(r"AGENTS\.md,\s+Classify", "AGENTS.md", build_original)
            if not count:
                raise AssertionError("agents/build.md: no 'AGENTS.md, Classify' reference to remove")
            build_path.write_text(text)
            failed |= not expect("build.md lacks the AGENTS.md, Classify reference", lint(tree),
                                 "AGENTS.md, Classify")
        finally:
            build_path.write_text(build_original)

        try:
            build_path.write_text(build_original +
                                  "\nwith `<code>` one of `coupled-invariants`, `no-oracle`, "
                                  "`security-logic`.\n")
            failed |= not expect("build.md restates the trigger code list", lint(tree),
                                 "agents/build.md: restates the implement-deep trigger code")
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
            edit(build_path, "review, explore, advisor, implementor and",
                 "review, explore, implementor and")
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
            edit(agents_path, "reading\n  `agents/advisor.md`, and for", "reading\n  its own prompt, and for")
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

        # U6: the quota fallback column. Each case edits one routing row's sixth
        # cell; the row is matched by its band so the edit lands on that row only.
        def edit_row(band: str, old: str, new: str) -> None:
            lines = agents_original.splitlines(True)
            hits = [i for i, line in enumerate(lines) if line.startswith(f"| {band} |")]
            if len(hits) != 1 or not lines[hits[0]].rstrip().endswith(f"| {old} |"):
                raise AssertionError(f"AGENTS.md: no single | {band} | row ending in {old!r}")
            line = lines[hits[0]].rstrip("\n")
            lines[hits[0]] = line[: -len(f"{old} |")] + f"{new} |\n"
            agents_path.write_text("".join(lines))

        for name, band, old, new in (
            ("fallback cell names an unroutable model", "implementor, plan",
             "`claude-agent/opus` `variant=medium`", "`claude-agent/nope` `variant=medium`"),
            ("review-critical has a fallback", "review-critical",
             "none", "`claude-agent/sonnet` `variant=high`"),
            ("advisor has a fallback", "advisor", "none", "`claude-agent/opus` `variant=medium`"),
            ("fallback equals its own pin", "second-opinion",
             "`claude-agent/sonnet` `variant=high`",
             "`opencode-go/muse-spark-1.3-contributor` `variant=high`"),
            ("fallback option id is not valid for the instance", "general, check, checkpoint, integrate",
             "`claude-agent/sonnet` `variant=medium`", "`claude-agent/sonnet` `effort=medium`"),
            ("fallback cell is malformed", "explore", "`claude-agent/haiku` none", "haiku"),
        ):
            try:
                edit_row(band, old, new)
                failed |= not expect(name, lint(tree), "fallback")
            finally:
                agents_path.write_text(agents_original)

        try:
            lines = agents_original.splitlines(True)
            index = next(i for i, line in enumerate(lines) if line.startswith("| review-light |"))
            lines[index] = lines[index].rstrip("\n").removesuffix(" none |") + "\n"
            agents_path.write_text("".join(lines))
            failed |= not expect("routing row without a fallback cell", lint(tree), "fallback")
        finally:
            agents_path.write_text(agents_original)

        # U6 D1: the EXECUTE ALLOWLIST is an exact set on exactly one line.
        allow_line = next(line for line in build_original.splitlines()
                          if line.startswith("EXECUTE ALLOWLIST:"))
        for name, new in (
            ("allowlist plus t3_thread_send", allow_line + ", t3_thread_send"),
            ("allowlist without orchestrator_capabilities",
             allow_line.replace(" orchestrator_capabilities,", "")),
            ("allowlist with a duplicate name", allow_line + ", task_cancel"),
            ("allowlist on two lines", allow_line + "\n\n" + allow_line),
        ):
            try:
                if new == allow_line:
                    raise AssertionError(f"{name}: edit changed nothing")
                edit(build_path, allow_line, new)
                failed |= not expect(name, lint(tree), "EXECUTE ALLOWLIST set")
            finally:
                build_path.write_text(build_original)

        # U6 D2: the PROMPT: rationale names the implementor unit (implement-deep
        # alone does not count).
        try:
            edit(build_path, "advisor, implementor and\nimplement-deep units",
                 "advisor and\nimplement-deep units")
            failed |= not expect("build.md PROMPT rationale without implementor", lint(tree),
                                 "implementor PROMPT")
        finally:
            build_path.write_text(build_original)

        # U7: review cost, step caps, plan-mode anchor, prose-lane stop rule,
        # squash-before-return and the close-out ledger check. Each anchor is
        # removed everywhere it appears (line wraps included), so a second copy
        # cannot mask the drift.
        def edit_all(path: Path, old: str, new: str) -> None:
            pattern = r"\s+".join(re.escape(word) for word in old.split())
            text, count = re.subn(pattern, new, path.read_text())
            if not count:
                raise AssertionError(f"{path}: missing {old!r}")
            path.write_text(text)

        implementor_path = tree / "agents" / "implementor.md"
        deep_path = tree / "agents" / "implement-deep.md"
        stop_rule = "skips the T2-floor stop only when its classify printed `prose-lane: candidate`"
        for name, path, old, new, marker in (
            ("AGENTS.md lost the 🟡 rule", agents_path,
             "🟡 findings never trigger a fix round", "🟡 findings are optional", "🟡 rule"),
            ("build.md lost the 🟡 rule", build_path,
             "🟡 findings never trigger a fix round", "🟡 findings are optional", "🟡 rule"),
            ("AGENTS.md lost the plan-mode anchor", agents_path,
             "Editing, check, checkpoint and integrate units never get plan mode.", "",
             "plan-mode anchor"),
            ("build.md lost the plan-mode anchor", build_path,
             "Editing, check, checkpoint and integrate units never get plan mode.", "",
             "plan-mode anchor"),
            ("AGENTS.md stop rule lost the candidate exception", agents_path,
             stop_rule, "skips the T2-floor stop", "prose-lane exception"),
            ("build.md stop rule lost the candidate exception", build_path,
             stop_rule, "skips the T2-floor stop", "prose-lane exception"),
            ("AGENTS.md integrate lost prose-lane: eligible", agents_path,
             "must print `prose-lane: eligible`", "may print anything", "prose-lane exception"),
            ("build.md integrate lost UNIT-BASE..sha", build_path,
             "`git cherry-pick UNIT-BASE..sha`", "`git cherry-pick <sha>`", "UNIT-BASE..sha"),
            ("implementor steps 80", implementor_path, "steps: 120", "steps: 80", "steps"),
            ("implement-deep steps 80", deep_path, "steps: 120", "steps: 80", "steps"),
            ("implementor lost the squash rule", implementor_path,
             'git add -A -- <FILES> && git reset --soft <UNIT-BASE> && git commit -m "<msg>"',
             "git reset --soft <UNIT-BASE> && git commit", "squash"),
            ("implement-deep lost the squash rule", deep_path,
             'git add -A -- <FILES> && git reset --soft <UNIT-BASE> && git commit -m "<msg>"',
             "git reset --soft <UNIT-BASE> && git commit", "squash"),
            ("AGENTS.md close-out lost --list-pending", agents_path,
             "review-log --list-pending", "review-log", "list-pending"),
            ("build.md close-out lost --list-pending", build_path,
             "review-log --list-pending", "review-log", "list-pending"),
        ):
            saved = path.read_text()
            try:
                edit_all(path, old, new)
                failed |= not expect(name, lint(tree), marker)
            finally:
                path.write_text(saved)
    print("FAIL" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
