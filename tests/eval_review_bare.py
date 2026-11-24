#!/usr/bin/env python3
"""evals/run.sh --bare reviews on bare opencode (the person, 2026-11-23: "is bare
t3/opencode better than what I have?").

With --bare the reviewer runs as opencode's built-in `build` agent with an empty
config directory and OPENCODE_DISABLE_CLAUDE_CODE=1, so no AGENTS.md, harness
skills, plugin, policy or MCP servers load. It has no review prompt of its own,
so the case prompt names the severity markers score.py reads; it has a shell, so
the prompt does not claim otherwise. Without --bare nothing changes. A fake
`opencode` on PATH records its environment, arguments and prompt.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, "evals", "run.sh")
FAILURES = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)
        if detail:
            print(detail)


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, mode)


def main() -> int:
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q")
        write(os.path.join(repo, "app.txt"), "fixed\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "fixed")
        base = git(repo, "rev-parse", "HEAD").strip()
        write(os.path.join(repo, "app.txt"), "buggy\n")
        patch = git(repo, "diff")
        git(repo, "checkout", "--", "app.txt")
        cases = os.path.join(root, "cases")
        write(os.path.join(cases, "demo", "change.patch"), patch)
        write(os.path.join(cases, "demo", "case.json"), json.dumps({
            "id": "demo", "tier": "T1", "repo": repo, "base": base, "patch": "change.patch",
            "expected": [{"id": "d", "severity": "🟠", "files": ["app.txt"], "require": ["buggy"], "notes": "x"}]}))
        log = os.path.join(root, "log.json")
        fake = os.path.join(root, "bin", "opencode")
        # run.sh also calls `opencode stats` afterwards; record only the reviewer's `run`.
        write(fake, "#!/usr/bin/env python3\nimport json, os, sys\n"
                    "if sys.argv[1:2] != ['run']:\n    print('{}'); sys.exit(0)\n"
                    f"json.dump({{'argv': sys.argv[1:], 'xdg': os.environ.get('XDG_CONFIG_HOME', ''),"
                    f" 'disable': os.environ.get('OPENCODE_DISABLE_CLAUDE_CODE', ''), 'project': os.environ.get('OPENCODE_DISABLE_PROJECT_CONFIG', '')}}, open({log!r}, 'w'))\n"
                    "print('no findings')\n", mode=0o755)
        env = dict(os.environ, EVAL_CASES_DIR=cases, EVAL_WORK_ROOT=os.path.join(root, "work"),
                   PATH=os.path.dirname(fake) + os.pathsep + os.environ["PATH"])
        env.pop("XDG_CONFIG_HOME", None)

        def run(*extra):
            if os.path.exists(log):
                os.remove(log)
            proc = subprocess.run(["bash", RUN, "-m", "test/model", "-c", "demo", *extra],
                                  env=env, capture_output=True, text=True, timeout=120)
            seen = json.load(open(log)) if os.path.exists(log) else {}
            return proc, seen

        proc, seen = run()
        argv = seen.get("argv", [])
        agent = argv[argv.index("--agent") + 1] if "--agent" in argv else None
        check(proc.returncode == 0 and agent == "review-deep" and seen.get("xdg") == "" and seen.get("disable") == "",
              "without --bare: review-deep on the normal config", f"rc={proc.returncode} {seen}\n{proc.stderr}")

        proc, seen = run("--bare")
        argv = seen.get("argv", [])
        agent = argv[argv.index("--agent") + 1] if "--agent" in argv else None
        prompt = argv[-1] if argv else ""
        xdg = seen.get("xdg", "")
        check(proc.returncode == 0 and agent == "build", "--bare: opencode's built-in build agent", f"rc={proc.returncode} {seen}\n{proc.stderr}")
        check(bool(xdg) and os.path.isdir(os.path.join(xdg, "opencode")) and not os.listdir(os.path.join(xdg, "opencode"))
              and seen.get("disable") == "1", "--bare: an empty config directory and Claude Code compatibility off", str(seen))
        check(all(m in prompt for m in ("🔴", "🟠", "🟡", "🟢")), "--bare: the prompt names the severity markers score.py reads", prompt[-400:])
        check("you have no shell" not in prompt, "--bare: the prompt does not claim the reviewer has no shell")
        check("demo" in prompt or "app.txt" in prompt, "--bare: the diff is still in the prompt", prompt[:300])
        check(seen.get("project") == "", "--bare alone keeps the project's AGENTS.md", str(seen))
        proc, seen = run("--bare", "--no-project")
        check(proc.returncode == 0 and seen.get("project") == "1", "--no-project skips the project's AGENTS.md", f"rc={proc.returncode} {seen}\n{proc.stderr}")
    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
