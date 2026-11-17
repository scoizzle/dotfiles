#!/usr/bin/env python3
"""bin/lint-config must pass on the tree and must fail when a policy surface
drifts: the native fallback models in policy/permissions.json, the default
agent losing permission to edit, or the short contract phrases leaving
AGENTS.md."""

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
        for name in ("explore", "review-deep"):
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

        for name, path, old, new, marker in (
            ("AGENTS.md lost 'You do the work'", agents_path,
             "You do the work", "You might do the work", "You do the work"),
            ("AGENTS.md lost 'Do not dispatch a writer'", agents_path,
             "Do not dispatch a writer", "You may dispatch a writer", "Do not dispatch a writer"),
            ("build.md lost 'You do the work'", build_path,
             "You do the work", "You might do the work", "You do the work"),
        ):
            saved = path.read_text()
            try:
                edit(path, old, new)
                failed |= not expect(name, lint(tree), marker)
            finally:
                path.write_text(saved)

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
            ("AGENTS.md", "### Skills"),
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

        build_path = tree / "agents" / "build.md"
        saved = build_path.read_text()
        try:
            build_path.write_text(saved.replace("T3 Code", "shell git"))
            failed |= not expect("build.md lost the T3 pointer", lint(tree), "T3 Code")
        finally:
            build_path.write_text(saved)

        agents_path = tree / "AGENTS.md"
        saved = agents_path.read_text()
        try:
            agents_path.write_text(saved.replace("ends the live session", "moves you"))
            failed |= not expect("AGENTS.md lost the handoff caveat", lint(tree), "ends the live session")
        finally:
            agents_path.write_text(saved)

        for needle in (
            "this review is required",
            "different family than the one that wrote the diff",
            "skipping the review is not the fallback",
            "stops for a person",
            "Family means vendor",
            "dispatch the review on a different-family model",
            "returns `unreviewed` to its parent",
        ):
            saved = agents_path.read_text()
            try:
                agents_path.write_text(saved.replace(needle, "optional"))
                failed |= not expect(f"AGENTS.md: sensitive review skippable ({needle!r})", lint(tree), "sensitive review")
            finally:
                agents_path.write_text(saved)

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

        for needle in ("required for a sensitive change", "never skip the review"):
            build_saved = build_path.read_text()
            try:
                build_path.write_text(build_saved.replace(needle, "optional"))
                failed |= not expect(f"agents/build.md: sensitive review skippable ({needle!r})", lint(tree), "sensitive review")
            finally:
                build_path.write_text(build_saved)

    print("FAIL" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
