#!/usr/bin/env python3
"""Regression tests for evals/run-claude.sh, driven by EVAL_CLAUDE_CMD stubs.

The harness is exercised against a throwaway repository and case directory, so
it never reads evals/cases or a fixture repo. A fake `claude` on PATH covers the
real invocation, so the flag contract is checked without a model.
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_CLAUDE = os.path.join(ROOT, "evals", "run-claude.sh")

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
    """A repo with one base commit, plus two change cases and one plan case."""
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    git(repo, "init", "-q")
    write(os.path.join(repo, "app.txt"), "base\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD").strip()

    write(os.path.join(repo, "app.txt"), "changed\n")
    patch = git(repo, "diff")
    git(repo, "checkout", "--", "app.txt")

    cases = os.path.join(root, "cases")
    for cid, tier in (("alpha", "T1"), ("beta", "T2")):
        case = os.path.join(cases, cid)
        write(os.path.join(case, "change.patch"), patch)
        write(os.path.join(case, "case.json"), json.dumps({
            "id": cid,
            "tier": tier,
            "repo": repo,
            "base": base,
            "patch": "change.patch",
            "claim": f"{cid} claim",
            "expected": [{"id": f"{cid}-defect", "severity": "🟠",
                          "notes": "app.txt lost its change."}],
        }, indent=2) + "\n")

    plan = os.path.join(cases, "plan-only")
    write(os.path.join(plan, "plan.md"), "Do the thing.\n")
    write(os.path.join(plan, "case.json"), json.dumps({
        "id": "plan-only",
        "tier": "T1",
        "artifact": "plan",
        "repo": repo,
        "base": base,
        "plan": "plan.md",
        "goal": "Do the thing.",
    }, indent=2) + "\n")
    return cases


def build_stubs(root):
    stubs = os.path.join(root, "stubs")
    log = os.path.join(root, "stub-log.txt")
    write(os.path.join(stubs, "ok.sh"),
          "#!/bin/sh\nprintf '%s\\n' \"$1\" > \"$STUB_LOG\"\n"
          "printf '%s\\n' '{\"result\":\"🟠 concat | string in app.txt\","
          "\"total_cost_usd\":0.0123,\"num_turns\":4}'\n",
          mode=0o755)
    write(os.path.join(stubs, "bad.sh"),
          "#!/bin/sh\nprintf '%s\\n' 'not json, a crash trace'\n", mode=0o755)
    return stubs, log


def run(cases, stub, *extra, log=None, path=None):
    env = dict(os.environ)
    env.pop("EVAL_CLAUDE_CMD", None)
    env.update({
        "EVAL_CASES_DIR": cases,
        "EVAL_WORK_ROOT": os.path.join(os.path.dirname(cases), "work"),
        "EVAL_CASE_TIMEOUT": "120",
    })
    if stub:
        env["EVAL_CLAUDE_CMD"] = stub
    if log:
        env["STUB_LOG"] = log
    if path:
        env["PATH"] = path + os.pathsep + env.get("PATH", "")
    return subprocess.run(
        ["bash", RUN_CLAUDE, *extra],
        env=env, capture_output=True, text=True,
    )


def run_dir(result):
    """The runner's own `results: <path>` line, so the test never guesses a name."""
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("results: "):
            return line[len("results: "):]
    return ""


def main():
    failures = 0

    def check(name, condition, detail):
        nonlocal failures
        print(f"{'ok  ' if condition else 'FAIL'} {name}")
        if not condition:
            print(detail)
            failures += 1

    if not os.path.isfile(RUN_CLAUDE):
        print(f"FAIL missing {RUN_CLAUDE}")
        return 1

    with tempfile.TemporaryDirectory() as root:
        cases = build_fixture(root)
        stubs, log = build_stubs(root)

        result = run(cases, os.path.join(stubs, "ok.sh"), "-c", "alpha", log=log)
        work = run_dir(result)
        case = os.path.join(work, "results", "alpha")
        report = os.path.join(case, "claude-code-opus-medium.txt")
        text = open(report, encoding="utf-8").read() if os.path.exists(report) else ""
        prompt = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
        model = open(os.path.join(work, "model"), encoding="utf-8").read().strip() if work else ""
        check("a JSON result becomes the scoreable report",
              result.returncode == 0
              and "concat | string in app.txt" in text
              and "[eval]" in text
              and "cost_usd=0.0123" in text
              and "turns=4" in text,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}\ntext={text!r}")
        check("the model file names the native harness",
              model == "claude-code/opus#medium", f"model={model!r}")
        check("the raw JSON envelope is kept beside the report",
              os.path.exists(os.path.join(case, "claude-code-opus-medium.json")),
              os.listdir(case) if os.path.isdir(case) else "no case dir")
        check("the prompt carries the diff and the claim",
              "--- DIFF" in prompt and "alpha claim" in prompt,
              prompt[:400])
        check("-c runs only the named case",
              not os.path.isdir(os.path.join(work, "results", "beta")),
              os.listdir(os.path.join(work, "results")))

        result = run(cases, os.path.join(stubs, "ok.sh"), "-t", "T2", log=log)
        work = run_dir(result)
        check("--tier selects change cases only",
              result.returncode == 0
              and os.path.isdir(os.path.join(work, "results", "beta"))
              and not os.path.isdir(os.path.join(work, "results", "alpha"))
              and not os.path.isdir(os.path.join(work, "results", "plan-only")),
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}")

        result = run(cases, os.path.join(stubs, "bad.sh"), "-c", "alpha")
        work = run_dir(result)
        case = os.path.join(work, "results", "alpha")
        text = open(os.path.join(case, "claude-code-opus-medium.txt"), encoding="utf-8").read()
        check("a non-JSON result fails the case and keeps the raw text",
              result.returncode != 0
              and os.path.exists(os.path.join(case, "FAILED"))
              and "not json" in text,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}\ntext={text!r}")

        result = run(cases, os.path.join(stubs, "ok.sh"), "-c", "plan-only")
        check("a plan case is refused and points at run.sh",
              result.returncode == 2 and "run.sh -a verifier" in result.stderr,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}")

        # The real invocation: a fake `claude` records argv so the read-only
        # flag contract is checked without a model.
        fake_bin = os.path.join(root, "fake-bin")
        argv_log = os.path.join(root, "claude-argv.txt")
        write(os.path.join(fake_bin, "claude"),
              f"#!/bin/sh\nprintf '%s\\000' \"$@\" > '{argv_log}'\n"
              "printf '%s\\n' '{\"result\":\"ok\",\"total_cost_usd\":0,\"num_turns\":1}'\n",
              mode=0o755)
        result = run(cases, None, "-c", "alpha", path=fake_bin)
        argv = [a for a in open(argv_log, encoding="utf-8").read().split("\0") if a] if os.path.exists(argv_log) else []
        def flag(name):
            return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None
        check("the real invocation is read-only and scored as JSON",
              result.returncode == 0
              and flag("--model") == "opus"
              and flag("--effort") == "medium"
              and flag("--permission-mode") == "dontAsk"
              and flag("--output-format") == "json"
              and flag("--tools") == "Read,Grep,Glob"
              and "mcp__roslynk__get_symbol" in (flag("--allowedTools") or "")
              and "mcp__roslynk__rename_symbol" not in (flag("--allowedTools") or "")
              and flag("--append-system-prompt")
              and "--no-session-persistence" in argv,
              f"rc={result.returncode}\n{result.stdout}\n{result.stderr}\nargv={argv}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
