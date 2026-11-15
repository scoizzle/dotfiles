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

        agents_path = tree / "AGENTS.md"
        agents_original = agents_path.read_text()
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
            agents_path.write_text(agents_original)

    print("FAIL" if failed else "ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
