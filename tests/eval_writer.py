#!/usr/bin/env python3
"""Regression tests for evals/run-writer.sh, driven by EVAL_WRITER_CMD stubs.

The harness is exercised against a throwaway repository and case directory, so
it never reads evals/cases or a fixture repo.
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_WRITER = os.path.join(ROOT, "evals", "run-writer.sh")

GIT_ID = ["-c", "user.name=eval-test", "-c", "user.email=eval@example.invalid"]


def git(cwd, *args):
    return subprocess.run(
        ["git", *GIT_ID, *args], cwd=cwd, check=True,
        capture_output=True, text=True,
    ).stdout


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, mode)


def build_fixture(root):
    """A repo whose base commit is the fixed state; the patch reverts it."""
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    git(repo, "init", "-q")
    write(os.path.join(repo, "app.txt"), "fixed\n")
    write(os.path.join(repo, "oracle", "check.sh"),
          "#!/bin/sh\ngrep -q fixed app.txt\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fixed")
    base = git(repo, "rev-parse", "HEAD").strip()

    write(os.path.join(repo, "app.txt"), "buggy\n")
    patch = git(repo, "diff")
    git(repo, "checkout", "--", "app.txt")

    cases_root = os.path.join(root, "cases")
    cases = os.path.join(cases_root, "demo")
    os.makedirs(cases)
    write(os.path.join(cases, "change.patch"), patch)
    write(os.path.join(cases, "case.json"), json.dumps({
        "id": "demo",
        "tier": "T1",
        "repo": repo,
        "base": base,
        "patch": "change.patch",
        "expected": [{"id": "demo-defect", "severity": "🟠",
                      "notes": "app.txt is not fixed."}],
    }, indent=2) + "\n")

    checks = os.path.join(root, "writer-checks.json")
    write(checks, json.dumps({
        "demo": {"check": "sh oracle/check.sh", "protect": ["oracle/check.sh"]}
    }, indent=2) + "\n")
    return cases_root, checks


def build_stubs(root):
    stubs = os.path.join(root, "stubs")
    write(os.path.join(stubs, "fix.sh"), "#!/bin/sh\nprintf 'fixed\\n' > app.txt\n",
          mode=0o755)
    write(os.path.join(stubs, "noop.sh"), "#!/bin/sh\nexit 0\n", mode=0o755)
    write(os.path.join(stubs, "cheat.sh"),
          "#!/bin/sh\nprintf '#!/bin/sh\\nexit 0\\n' > oracle/check.sh\n",
          mode=0o755)
    # A writer has shell and runs with --auto, so it could push to the clone's
    # origin, which is the fixture repository itself.
    write(os.path.join(stubs, "push.sh"),
          "#!/bin/sh\nprintf 'fixed\\n' > app.txt\n"
          "git push -q origin HEAD:refs/heads/leak >/dev/null 2>&1\nexit 0\n",
          mode=0o755)
    return stubs


def run(root, cases, checks, stub, *extra):
    env = dict(os.environ)
    env.update({
        "EVAL_CASES_DIR": cases,
        "EVAL_WRITER_CHECKS": checks,
        "EVAL_WORK_ROOT": os.path.join(root, "work"),
        "EVAL_WRITER_CMD": stub,
        "EVAL_CASE_TIMEOUT": "120",
    })
    return subprocess.run(
        ["bash", RUN_WRITER, "-m", "test/model", "-c", "demo", *extra],
        env=env, capture_output=True, text=True,
    )


def main():
    failures = 0

    def check(name, condition, detail):
        nonlocal failures
        print(f"{'ok  ' if condition else 'FAIL'} {name}")
        if not condition:
            print(detail)
            failures += 1

    if not os.path.isfile(RUN_WRITER):
        print(f"FAIL missing {RUN_WRITER}")
        return 1

    with tempfile.TemporaryDirectory() as root:
        cases, checks = build_fixture(root)
        stubs = build_stubs(root)

        result = run(root, cases, checks, os.path.join(stubs, "fix.sh"))
        check("fixed stub passes",
              result.returncode == 0 and "PASS" in result.stdout,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}")

        result = run(root, cases, checks, os.path.join(stubs, "noop.sh"))
        check("no-op stub fails on the check",
              result.returncode != 0
              and "FAIL" in result.stdout
              and "check failed" in result.stdout,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}")

        result = run(root, cases, checks, os.path.join(stubs, "cheat.sh"))
        check("editing a protected path fails",
              result.returncode != 0
              and "FAIL" in result.stdout
              and "touched tests" in result.stdout,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}")

        result = run(root, cases, checks, os.path.join(stubs, "fix.sh"), "--runs", "2")
        check("--runs 2 prints 2/2",
              result.returncode == 0 and "2/2" in result.stdout,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}")

        run(root, cases, checks, os.path.join(stubs, "push.sh"))
        leaked = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", "refs/heads/leak"],
            cwd=os.path.join(root, "repo"), capture_output=True, text=True,
        )
        check("a writer cannot push to the fixture repository",
              leaked.returncode != 0,
              f"refs/heads/leak exists in the fixture repo: {leaked.stdout}")

        # Without EVAL_WRITER_CMD the harness calls `opencode run`. A stub on
        # PATH records its arguments: the writer agent defaults to build, the
        # default agent whose pin this eval measures, and -a overrides it.
        fake_bin = os.path.join(root, "fake-bin")
        argv_log = os.path.join(root, "opencode-argv.txt")
        write(os.path.join(fake_bin, "opencode"),
              f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{argv_log}'\nprintf 'fixed\\n' > app.txt\n",
              mode=0o755)
        for extra, want in (((), "build"), (("-a", "other-agent"), "other-agent")):
            env = dict(os.environ)
            env.pop("EVAL_WRITER_CMD", None)
            env.update({
                "EVAL_CASES_DIR": cases,
                "EVAL_WRITER_CHECKS": checks,
                "EVAL_WORK_ROOT": os.path.join(root, "work"),
                "EVAL_CASE_TIMEOUT": "120",
                "PATH": fake_bin + os.pathsep + env.get("PATH", ""),
            })
            result = subprocess.run(
                ["bash", RUN_WRITER, "-m", "test/model", "-c", "demo", *extra],
                env=env, capture_output=True, text=True,
            )
            logged = open(argv_log, encoding="utf-8").read().split("\n") if os.path.exists(argv_log) else []
            agent = logged[logged.index("--agent") + 1] if "--agent" in logged else None
            check(f"the writer agent is {want}",
                  result.returncode == 0 and agent == want,
                  f"rc={result.returncode} agent={agent}\n{result.stdout}\n{result.stderr}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
