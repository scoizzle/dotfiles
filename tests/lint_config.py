#!/usr/bin/env python3
"""bin/lint-config must pass on the tree and must fail when a policy surface
drifts: the native fallback models in policy/permissions.json, the default
agent losing permission to edit, an escape hatch or retired word returning to
AGENTS.md, or the contract outgrowing its cap or naming an enforcer that does
not exist."""

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
        else:
            print("ok unmodified copy")

        policy_path = tree / "policy" / "permissions.json"
        original = policy_path.read_text()
        for name in ("explore", "review-deep", "advisor"):
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

        # A sandbox write path must not reach a location whose contents run or are
        # loaded outside the sandbox: a sandboxed command could replace them.
        for entry in ("~/.dotnet", "~/.dotnet/tools", "~", "~/.config/opencode/bin"):
            policy = json.loads(original)
            policy["sandbox"]["allow_write"] = [entry]
            policy_path.write_text(json.dumps(policy, indent=2) + "\n")
            run = lint(tree)
            out = run.stdout + run.stderr
            if run.returncode != 1 or "could replace something that runs unsandboxed" not in out:
                print(f"FAIL: sandbox allow_write {entry!r}: rc={run.returncode}, "
                      f"expected 1 naming the entry\n{out}")
                failed = True
            elif entry not in out:
                print(f"FAIL: sandbox allow_write {entry!r}: the failure does not name the entry\n{out}")
                failed = True
            else:
                print(f"ok sandbox allow_write rejects {entry}")
        policy_path.write_text(original)

        agents_path = tree / "AGENTS.md"
        build_path = tree / "agents" / "build.md"
        build_original = build_path.read_text()

        try:
            edit(build_path, "mode: primary",
                 "mode: primary\npermissions:\n  - action: edit\n    resource: \"*\"\n    effect: deny")
            failed |= not expect("build denies edit", lint(tree), "edit must be allow")
        finally:
            build_path.write_text(build_original)

        verify_path = tree / "commands" / "verify.md"
        for old in ("--show AGENTS.md", "--show agents/review-deep.md", "base copies"):
            saved = verify_path.read_text()
            try:
                verify_path.write_text(saved.replace(old, ""))
                failed |= not expect(f"verify.md lost {old!r}", lint(tree), "commands/verify.md")
            finally:
                verify_path.write_text(saved)

        for name, needle in (
            ("AGENTS.md", "run-tests"),
            ("AGENTS.md", "platform-detection"),
            ("AGENTS.md", "test-anti-patterns"),
            ("AGENTS.md", "assertion-quality"),
            ("agents/build.md", "run-tests"),
            ("agents/implementor.md", "run-tests"),
            ("agents/implementor.md", "assertion-quality"),
            ("agents/verifier.md", "run-tests"),
            ("agents/review-deep.md", "assertion-quality"),
        ):
            path = tree / name
            saved = path.read_text()
            try:
                path.write_text(saved.replace(needle, "no-skill"))
                failed |= not expect(f"{name} lost skill wiring {needle!r}", lint(tree), "skill wiring")
            finally:
                path.write_text(saved)

        for name in ("AGENTS.md", "agents/build.md"):
            path = tree / name
            for stale in ("Tier: T0", "plan-review-deep", "second-opinion", "review-light"):
                saved = path.read_text()
                try:
                    path.write_text(saved.replace("## Memory", f"{stale}\n\n## Memory", 1)
                                    if name == "AGENTS.md" else saved + f"\n{stale}\n")
                    failed |= not expect(f"{name}: retired tier cascade restored ({stale!r})",
                                         lint(tree), "retired tier cascade")
                finally:
                    path.write_text(saved)

        for stale in (
            "or say that no second model was available",
            "say so and continue",
            "Do not stop to ask about fallbacks",
        ):
            saved = agents_path.read_text()
            try:
                agents_path.write_text(saved.replace("## Memory", f"{stale}\n\n## Memory"))
                failed |= not expect(f"AGENTS.md: old escape hatch restored ({stale!r})", lint(tree), "sensitive review")
            finally:
                agents_path.write_text(saved)

        saved = agents_path.read_text()
        try:
            agents_path.write_text(saved.replace(
                "## Memory", "Do not stage, commit, or push unless asked.\n\n## Memory"))
            failed |= not expect("AGENTS.md: old commit/push gate restored", lint(tree), "open and watch its PR")
        finally:
            agents_path.write_text(saved)

        # v2: the contract is capped, and every rule in its table names an
        # enforcer that exists. These replace ~100 exact-phrase needles.
        saved = agents_path.read_text()
        row = "| No agent merge in v2.0 |"
        contract_cases = (
            ("AGENTS.md over the cap", saved + "\n" + "x" * 8000, "over the 8000 cap"),
            ("rule table heading removed", saved.replace("## Rules and what enforces them", "## Rules"),
             "rules have no enforcers"),
            ("a policy enforcer that does not exist", saved.replace("policy:git-push-destructive", "policy:no-such-rule", 1),
             "no policy rule or key 'no-such-rule'"),
            ("a test enforcer that does not exist", saved.replace("test:install_root.py", "test:no_such.py", 1),
             "no tests/no_such.py"),
            ("a lint enforcer that does not exist", saved.replace("lint:check_no_claude_in_opencode", "lint:check_nothing", 1),
             "no lint check check_nothing"),
            ("an unknown enforcer kind", saved.replace("policy:git-push |", "hope:git-push |", 1), "unknown enforcer kind"),
            ("a judgment rule with no failure", saved.replace("| judgment | #39 landed unreviewed |", "| judgment | — |", 1),
             "names no failure it prevents"),
            # review of dba84ac (Opus): a top-level policy key such as `version` is not a rule.
            ("a policy key that is not a rule", saved.replace("policy:git-push-destructive", "policy:version", 1),
             "no policy rule or key 'version'"),
            ("the table loses its header row", saved.replace("| Rule | Enforcer | Failure it prevents |\n| --- | --- | --- |\n", "", 1),
             "header row"),
        )
        for name, text, marker in contract_cases:
            try:
                agents_path.write_text(text)
                failed |= not expect(f"contract: {name}", lint(tree), marker)
            finally:
                agents_path.write_text(saved)
        ci_path = tree / ".github" / "workflows" / "ci.yml"
        ci_saved = ci_path.read_text()
        try:
            ci_path.write_text(ci_saved.replace("python3 tests/install_root.py", "true"))
            failed |= not expect("contract: a test enforcer CI does not run", lint(tree), "does not run in CI")
        finally:
            ci_path.write_text(ci_saved)
        try:
            # Only a run line counts: a comment naming the test does not run it.
            ci_path.write_text(ci_saved.replace("python3 tests/install_root.py", "true  # python3 tests/install_root.py"))
            failed |= not expect("contract: a test enforcer named only in a CI comment", lint(tree), "does not run in CI")
        finally:
            ci_path.write_text(ci_saved)
        lint_path = tree / "bin" / "lint-config"
        lint_saved = lint_path.read_text()
        try:
            # Called from somewhere other than main() is not a running check.
            lint_path.write_text(lint_saved.replace("    check_no_claude_in_opencode()\n", "", 1)
                                 + "\n\ndef _unused() -> None:\n    check_no_claude_in_opencode()\n")
            failed |= not expect("contract: a lint enforcer not called from main", lint(tree), "called from main")
        finally:
            lint_path.write_text(lint_saved)

        # v2: Claude runs in Claude Code. A claude-agent/* pin in an opencode agent
        # file or opencode.json puts it back inside opencode.
        review_path = tree / "agents" / "review-deep.md"
        review_saved = review_path.read_text()
        try:
            review_path.write_text(review_saved.replace(
                "model: opencode-go/deepseek-v4.1-flash#high", "model: claude-agent/opus#medium", 1))
            failed |= not expect("an opencode agent pins a Claude model again", lint(tree), "runs Claude inside opencode")
        finally:
            review_path.write_text(review_saved)

        # OpenCode 2 rejects a v1 named export at load, and the only trace is a
        # warn line in a log, so the shape drift has to fail lint instead. The
        # fixture is a plugin of its own, so the check outlives any one plugin.
        probe = tree / "plugins" / "shape-probe.js"
        probe.parent.mkdir(exist_ok=True)
        try:
            probe.write_text("export const ShapeProbe = async () => ({})\n")
            failed |= not expect("plugin reverted to the v1 named export", lint(tree), "export default")
        finally:
            probe.unlink()

        # v2 runs Claude through opencode again: the entrypoint label is back.
        plugin_path = tree / "plugins" / "claude-entrypoint.js"
        plugin_saved = plugin_path.read_text() if plugin_path.exists() else ""
        try:
            plugin_path.write_text(plugin_saved.replace("CLAUDE_CODE_ENTRYPOINT", "SOME_OTHER_ENV"))
            failed |= not expect("plugin lost the entrypoint label", lint(tree), "CLAUDE_CODE_ENTRYPOINT")
        finally:
            plugin_path.write_text(plugin_saved)
        # The header comment names the variable, so only the assignment counts.
        try:
            plugin_path.write_text(plugin_saved.replace(
                'process.env.CLAUDE_CODE_ENTRYPOINT = "opencode"', "// label removed"))
            failed |= not expect("plugin mentions the label only in a comment", lint(tree), "CLAUDE_CODE_ENTRYPOINT")
        finally:
            plugin_path.write_text(plugin_saved)
        # A sibling plugin must not make a missing entrypoint file look fine.
        other = tree / "plugins" / "other.js"
        moved = plugin_path.with_suffix(".moved")
        other.write_text('export default { id: "other", setup() {} }\n')
        try:
            plugin_path.rename(moved)
            failed |= not expect("entrypoint plugin file is missing", lint(tree), "claude-entrypoint.js")
        finally:
            moved.rename(plugin_path)
            other.unlink()

    print("FAIL" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
