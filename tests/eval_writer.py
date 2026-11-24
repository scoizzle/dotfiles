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

        # The fix must not be reachable from the writer's clone (review of PR #57,
        # 2026-11-23: writers ran `git show HEAD~1:<file>` and copied it).
        probe_log = os.path.join(root, "history.txt")
        write(os.path.join(stubs, "history.sh"),
              "#!/bin/sh\n"
              f"{{ git rev-parse --verify -q HEAD~1 >/dev/null && echo parent; "
              f"git log --all --oneline | wc -l | tr -d ' '; "
              f"git cat-file -e '{git(os.path.join(root, 'repo'), 'rev-parse', 'HEAD').strip()}' 2>/dev/null && echo base-object; "
              f"git remote | wc -l | tr -d ' '; }} > '{probe_log}'\n"
              "printf 'fixed\\n' > app.txt\n", mode=0o755)
        result = run(root, cases, checks, os.path.join(stubs, "history.sh"))
        seen = open(probe_log).read().split() if os.path.exists(probe_log) else ["missing"]
        check("the writer's clone has one commit, no parent, no remote, and not the fixed base's objects",
              result.returncode == 0 and seen == ["1", "0"], f"probe={seen}\n{result.stdout}")

        # --blind and --lead (v2 Phase 6b): the default prompt hands the writer
        # each case's cause notes, so every arm scored 18/18. --blind drops
        # them; --lead runs a lead first, which writes .eval-brief.md and must not
        # edit, and the writer gets that brief instead.
        prompt_log = os.path.join(root, "prompt.txt")
        write(os.path.join(stubs, "record-fix.sh"),
              f"#!/bin/sh\nprintf '%s' \"$1\" > '{prompt_log}'\nprintf 'fixed\\n' > app.txt\n", mode=0o755)
        write(os.path.join(stubs, "lead.sh"),
              "#!/bin/sh\nprintf 'BRIEF-MARKER: set app.txt to fixed\\n' > .eval-brief.md\n", mode=0o755)
        write(os.path.join(stubs, "lead-edits.sh"),
              "#!/bin/sh\nprintf 'fixed\\n' > app.txt\nprintf 'brief\\n' > .eval-brief.md\n", mode=0o755)
        write(os.path.join(stubs, "lead-silent.sh"), "#!/bin/sh\nexit 0\n", mode=0o755)

        result = run(root, cases, checks, os.path.join(stubs, "record-fix.sh"))
        seen = open(prompt_log, encoding="utf-8").read() if os.path.exists(prompt_log) else ""
        check("the default prompt carries the cause notes", "app.txt is not fixed." in seen, seen[-400:])
        result = run(root, cases, checks, os.path.join(stubs, "record-fix.sh"), "--blind")
        seen = open(prompt_log, encoding="utf-8").read() if os.path.exists(prompt_log) else ""
        check("--blind drops the cause notes but keeps the check",
              result.returncode == 0 and "app.txt is not fixed." not in seen and "sh oracle/check.sh" in seen,
              f"rc={result.returncode}\n{seen[-400:]}\n{result.stdout}")

        def run_lead(lead_stub, writer_stub):
            env = {"EVAL_LEAD_CMD": lead_stub}
            os.environ.update(env)
            try:
                return run(root, cases, checks, writer_stub, "--lead", "test/lead")
            finally:
                for key in env:
                    os.environ.pop(key, None)

        result = run_lead(os.path.join(stubs, "lead.sh"), os.path.join(stubs, "record-fix.sh"))
        seen = open(prompt_log, encoding="utf-8").read() if os.path.exists(prompt_log) else ""
        check("--lead hands the writer the lead's brief, blind",
              result.returncode == 0 and "BRIEF-MARKER" in seen and "app.txt is not fixed." not in seen
              and "sh oracle/check.sh" in seen,
              f"rc={result.returncode}\n{seen[-400:]}\n{result.stdout}\n{result.stderr}")
        briefs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "brief.md"]
        check("the brief is kept in the results, outside the clone", bool(briefs), str(briefs))
        result = run_lead(os.path.join(stubs, "lead-edits.sh"), os.path.join(stubs, "noop.sh"))
        check("a lead that edits fails the run", result.returncode != 0 and "lead edited" in result.stdout, result.stdout)
        result = run_lead(os.path.join(stubs, "lead-silent.sh"), os.path.join(stubs, "fix.sh"))
        check("a lead that writes no brief fails the run", result.returncode != 0 and "no brief" in result.stdout, result.stdout)
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        tail = open(sorted(logs)[-1], encoding="utf-8").read() if logs else ""
        check("each run records its cost and whether the brief carried code",
              " cost=" in tail and " brief_code=" in tail, tail[-300:])

        # --supervise (the person, 2026-11-23): DeepSeek does the work, Opus is
        # the skeptical supervisor. The writer runs blind; the supervisor reruns
        # the check, reads the diff, and writes .eval-verdict.md (first line
        # ACCEPT or REJECT, then findings); a REJECT gets the writer one fix round
        # with the findings. Each run records pre_pass (was the writer's first
        # attempt right), the verdict, and catch/false_alarm/miss.
        write(os.path.join(stubs, "late-fix.sh"),
              "#!/bin/sh\ncase \"$1\" in *SUPERVISOR*) printf 'fixed\\n' > app.txt ;; esac\n", mode=0o755)
        write(os.path.join(stubs, "sup-accept.sh"), "#!/bin/sh\nprintf 'ACCEPT\\nlooks right\\n' > .eval-verdict.md\n", mode=0o755)
        write(os.path.join(stubs, "sup-reject.sh"),
              "#!/bin/sh\nif grep -q fixed app.txt; then printf 'ACCEPT\\n' > .eval-verdict.md; "
              "else printf 'REJECT\\napp.txt is still buggy\\n' > .eval-verdict.md; fi\n", mode=0o755)
        write(os.path.join(stubs, "sup-edits.sh"),
              "#!/bin/sh\nprintf 'fixed\\n' > app.txt\nprintf 'ACCEPT\\n' > .eval-verdict.md\n", mode=0o755)
        write(os.path.join(stubs, "sup-silent.sh"), "#!/bin/sh\nexit 0\n", mode=0o755)

        def run_sup(sup_stub, writer_stub):
            os.environ["EVAL_SUPERVISOR_CMD"] = sup_stub
            try:
                return run(root, cases, checks, writer_stub, "--supervise", "test/sup")
            finally:
                os.environ.pop("EVAL_SUPERVISOR_CMD", None)

        def last_line():
            logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
            newest = max(logs, key=os.path.getmtime) if logs else None
            return open(newest, encoding="utf-8").read().strip().splitlines()[-1] if newest else ""

        result = run_sup(os.path.join(stubs, "sup-accept.sh"), os.path.join(stubs, "fix.sh"))
        line = last_line()
        check("--supervise: a right fix the supervisor accepts passes",
              result.returncode == 0 and "pre_pass=1" in line and "verdict=ACCEPT" in line and "sup=ok" in line,
              f"{result.stdout}\n{line}")
        result = run_sup(os.path.join(stubs, "sup-reject.sh"), os.path.join(stubs, "late-fix.sh"))
        line = last_line()
        check("--supervise: a REJECT gets one fix round with the findings, and counts as a catch",
              result.returncode == 0 and "pre_pass=0" in line and "verdict=REJECT" in line and "sup=catch" in line,
              f"{result.stdout}\n{line}")
        result = run_sup(os.path.join(stubs, "sup-accept.sh"), os.path.join(stubs, "noop.sh"))
        line = last_line()
        check("--supervise: accepting broken work is a miss, and the run fails",
              result.returncode != 0 and "sup=miss" in line, f"{result.stdout}\n{line}")
        result = run_sup(os.path.join(stubs, "sup-reject.sh"), os.path.join(stubs, "noop.sh"))
        line = last_line()
        check("--supervise: a rejection the writer cannot fix still fails the run",
              result.returncode != 0 and "sup=catch" in line, f"{result.stdout}\n{line}")
        result = run_sup(os.path.join(stubs, "sup-edits.sh"), os.path.join(stubs, "noop.sh"))
        check("--supervise: a supervisor that edits fails the run",
              result.returncode != 0 and "supervisor edited" in result.stdout, result.stdout)
        result = run_sup(os.path.join(stubs, "sup-silent.sh"), os.path.join(stubs, "fix.sh"))
        check("--supervise: a supervisor that writes no verdict fails the run",
              result.returncode != 0 and "no verdict" in result.stdout, result.stdout)

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

        # --bare (the person, 2026-11-23: "is bare t3/opencode better than what I
        # have?"): the writer runs with an empty opencode config and no Claude Code
        # compatibility, so no AGENTS.md, skills, plugin, policy or MCP servers load.
        env_log = os.path.join(root, "opencode-env.txt")
        write(os.path.join(fake_bin, "opencode"),
              "#!/bin/sh\n"
              f"printf 'XDG=%s\\nDISABLE=%s\\n' \"$XDG_CONFIG_HOME\" \"$OPENCODE_DISABLE_CLAUDE_CODE\" > '{env_log}'\n"
              f"printf '%s\\n' \"$@\" > '{argv_log}'\n"
              "ls \"$XDG_CONFIG_HOME/opencode\" 2>/dev/null | wc -l | tr -d ' ' >> '" + env_log + "'\n"
              "printf 'fixed\\n' > app.txt\n", mode=0o755)
        env = dict(os.environ)
        env.pop("EVAL_WRITER_CMD", None)
        env.update({"EVAL_CASES_DIR": cases, "EVAL_WRITER_CHECKS": checks,
                    "EVAL_WORK_ROOT": os.path.join(root, "work"), "EVAL_CASE_TIMEOUT": "120",
                    "PATH": fake_bin + os.pathsep + env.get("PATH", "")})
        result = subprocess.run(["bash", RUN_WRITER, "-m", "test/model", "-c", "demo", "--bare"],
                                env=env, capture_output=True, text=True)
        seen = open(env_log).read().split("\n") if os.path.exists(env_log) else []
        xdg = seen[0][4:] if seen and seen[0].startswith("XDG=") else ""
        check("--bare runs opencode with an empty config and Claude Code compatibility off",
              result.returncode == 0 and xdg and xdg != os.path.join(os.path.expanduser("~"), ".config")
              and len(seen) > 2 and seen[1] == "DISABLE=1" and seen[2] == "0",
              f"rc={result.returncode} seen={seen}\n{result.stdout}\n{result.stderr}")
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        newest = max(logs, key=os.path.getmtime) if logs else None
        tail = open(newest).read().strip().splitlines()[-1] if newest else ""
        check("a --bare run is marked bare=1", " bare=1" in tail, tail)
        # --no-project (the person, 2026-11-23: "is poly's agent stuff crap too?"):
        # also skip the repository's own AGENTS.md, to isolate it.
        write(os.path.join(fake_bin, "opencode"),
              "#!/bin/sh\n"
              f"printf 'PROJECT=%s\\n' \"$OPENCODE_DISABLE_PROJECT_CONFIG\" > '{env_log}'\n"
              "printf 'fixed\\n' > app.txt\n", mode=0o755)
        result = subprocess.run(["bash", RUN_WRITER, "-m", "test/model", "-c", "demo", "--bare", "--no-project"],
                                env=env, capture_output=True, text=True)
        seen = open(env_log).read().split("\n") if os.path.exists(env_log) else []
        check("--no-project skips the project's AGENTS.md", result.returncode == 0 and seen[:1] == ["PROJECT=1"],
              f"rc={result.returncode} {seen}\n{result.stderr}")
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        tail = open(max(logs, key=os.path.getmtime)).read().strip().splitlines()[-1] if logs else ""
        check("a --no-project run is marked project=0", " project=0" in tail, tail)
        # The fixture repository is still on disk; a writer that reads it is marked
        # (review, 2026-11-23), so a leak shows in the results instead of hiding.
        repo_path = os.path.join(root, "repo")
        write(os.path.join(stubs, "peek.sh"), f"#!/bin/sh\necho 'looking at {repo_path}'\nprintf 'fixed\\n' > app.txt\n", mode=0o755)
        result = run(root, cases, checks, os.path.join(stubs, "peek.sh"))
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        tail = open(max(logs, key=os.path.getmtime)).read().strip().splitlines()[-1] if logs else ""
        check("a writer that names the fixture repository is marked fixture_ref=1", " fixture_ref=1" in tail, tail)
        result = run(root, cases, checks, os.path.join(stubs, "fix.sh"))
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        tail = open(max(logs, key=os.path.getmtime)).read().strip().splitlines()[-1] if logs else ""
        check("an honest writer is fixture_ref=0", " fixture_ref=0" in tail, tail)
        check("an honest writer is web_ref=0", " web_ref=0" in tail, tail)
        # Phase 8c: DeepSeek writers fetched the merged fix from GitHub (`curl
        # .../pull/1053.diff`, `git clone https://github.com/...`); mark it.
        write(os.path.join(stubs, "fetch.sh"),
              "#!/bin/sh\necho 'curl -sL https://github.com/acme/repo/pull/7.diff'\nprintf 'fixed\\n' > app.txt\n", mode=0o755)
        result = run(root, cases, checks, os.path.join(stubs, "fetch.sh"))
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        tail = open(max(logs, key=os.path.getmtime)).read().strip().splitlines()[-1] if logs else ""
        check("a writer that reaches GitHub is marked web_ref=1", " web_ref=1" in tail, tail)
        # Phase 9: a grep that prints repository docs with GitHub links is not a fetch.
        write(os.path.join(stubs, "doclink.sh"),
              "#!/bin/sh\necho './docs/x.md:3: see [#659](https://github.com/acme/repo/issues/659)'\nprintf 'fixed\\n' > app.txt\n", mode=0o755)
        result = run(root, cases, checks, os.path.join(stubs, "doclink.sh"))
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        tail = open(max(logs, key=os.path.getmtime)).read().strip().splitlines()[-1] if logs else ""
        check("a GitHub link printed by grep is not web_ref", " web_ref=0" in tail, tail)
        # --role NAME runs the writer as a T3 brief would: its prompt opens with
        # `role: NAME`, so the plugin applies that role (2026-11-24: the slim
        # implementor, measured as production runs it).
        result = run(root, cases, checks, os.path.join(stubs, "record-fix.sh"), "--role", "implementor")
        seen = open(prompt_log, encoding="utf-8").read() if os.path.exists(prompt_log) else ""
        check("--role puts the role line first", result.returncode == 0 and seen.startswith("role: implementor\n"), seen[:120])
        logs = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(root, "work")) for f in fs if f == "writer.txt"]
        tail = open(max(logs, key=os.path.getmtime)).read().strip().splitlines()[-1] if logs else ""
        check("a --role run is marked role=implementor", " role=implementor" in tail, tail)
        check("every writer prompt says not to download the fix", "Do not download code or patches" in seen, seen[-300:])

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
