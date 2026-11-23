#!/usr/bin/env python3
"""A write to live harness configuration asks; a denial says it is a boundary.

tests/guard_windows.py covers the Windows path normalization. This covers the
control plane: ~/.config/opencode/{AGENTS.md,opencode.json,bin,policy,agents,
plugins}, ~/.claude/{CLAUDE.md,settings.json} (on machines an earlier install set up) are links into
one checkout, so an edit through any of them is live for every session at once.
The guard resolves both sides, so the same file in another checkout is not asked.

The checkout the running guard was loaded from is live even when install.cs did
not link a "policy" entry into the home, and a `cd` in a command moves the base
that later relative paths resolve against.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "bin" / "harness-guard"
POLICY = ROOT / "policy" / "permissions.json"
BOUNDARY = ("This is a boundary, not an obstacle: do not retry it in another form; "
            "take a safer path or stop and ask.")

failures = 0


def fail(message):
    global failures
    failures += 1
    print(f"FAIL {message}")


def run(home, payload, cwd, root=None):
    env = dict(os.environ, HARNESS_HOME=str(home), HARNESS_POLICY=str(POLICY))
    if root is None:
        env.pop("HARNESS_ROOT", None)
    else:
        env["HARNESS_ROOT"] = str(root)
    return subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(cwd))


def said(completed):
    if not completed.stdout.strip():
        return None
    return json.loads(completed.stdout)["hookSpecificOutput"]["permissionDecision"]


def reason(completed):
    return json.loads(completed.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


def edit(path, cwd=None):
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(path), "old_string": "a", "new_string": "b"}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return payload


def shell(command, cwd=None):
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return payload


def make_checkout(root):
    for rel in ("bin/harness-guard", "policy/permissions.json", "agents/build.md", "AGENTS.md", "opencode.json"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{rel}\n")
    return root


def expect_ask(name, completed):
    if completed.returncode != 0 or said(completed) != "ask" or "control-plane" not in reason(completed):
        fail(f"{name}: expected ask with rule control-plane, got rc={completed.returncode} "
             f"decision={said(completed)} stderr={completed.stderr.strip()!r}")


def expect_silent(name, completed):
    if completed.returncode != 0 or completed.stdout.strip():
        fail(f"{name}: expected no output and exit 0, got rc={completed.returncode} "
             f"stdout={completed.stdout.strip()!r} stderr={completed.stderr.strip()!r}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        home = tmp / "home"
        live = make_checkout(tmp / "live")
        config = home / ".config" / "opencode"
        config.mkdir(parents=True)
        for rel in ("bin", "policy", "agents", "AGENTS.md"):
            (config / rel).symlink_to(live / rel)
        worktree = make_checkout(tmp / "worktree")

        expect_ask("edit live bin/harness-guard by its real path",
                   run(home, edit(live / "bin" / "harness-guard"), home))
        expect_ask("edit live bin/harness-guard through ~/.config/opencode",
                   run(home, edit("~/.config/opencode/bin/harness-guard"), home))
        expect_ask("write live AGENTS.md",
                   run(home, {"tool_name": "Write", "tool_input": {"file_path": str(live / "AGENTS.md"), "content": "x"}}, home))
        expect_ask("edit a relative path against the event cwd",
                   run(home, edit("AGENTS.md", cwd=live), home))

        expect_silent("edit the same file in another checkout",
                      run(home, edit(worktree / "bin" / "harness-guard"), home))
        expect_silent("read the live file",
                      run(home, {"tool_name": "Read", "tool_input": {"file_path": str(live / "bin" / "harness-guard")}}, home))

        expect_ask("redirect into live policy",
                   run(home, shell(f"echo x > {live}/policy/permissions.json"), home))
        expect_ask("sed -i on the live guard",
                   run(home, shell(f"sed -i s/a/b/ {live}/bin/harness-guard"), home))
        expect_ask("cp onto a live agent",
                   run(home, shell(f"cp x {live}/agents/build.md"), home))

        bare = tmp / "bare"
        bare.mkdir()
        expect_silent("no symlinks installed",
                      run(bare, edit(live / "bin" / "harness-guard"), bare))

        # The checkout the running guard was loaded from is live, even when the
        # home has no links at all (install.cs links no "policy" entry).
        checkout_policy = run(bare, edit(live / "policy" / "permissions.json"), bare, root=live)
        expect_ask("edit the live policy file with only the checkout known", checkout_policy)
        if "policy/ in the live checkout" not in reason(checkout_policy):
            fail(f"the control-plane label must name the repo path, got {reason(checkout_policy)!r}")
        expect_ask("write the live policy by a relative path",
                   run(bare, {"tool_name": "Write",
                              "tool_input": {"file_path": "policy/permissions.json", "content": "x"}},
                       live, root=live))
        expect_ask("cd into the live checkout then sed a relative path",
                   run(home, shell(f"cd {live} && sed -i.bak s/a/b/ bin/harness-guard"), home, root=live))
        expect_ask("cd twice, then write a relative file",
                   run(home, shell(f"cd {live} && cd policy && echo x > permissions.json"), home, root=live))
        expect_silent("cd into another checkout then sed",
                      run(home, shell(f"cd {worktree} && sed -i.bak s/a/b/ bin/harness-guard"), home, root=live))
        expect_silent("a bare cd leaves the base alone",
                      run(home, shell("cd && echo x > notes.txt"), worktree, root=live))

        denied = run(home, shell("rm -rf build", cwd=worktree), home)
        if denied.returncode != 2 or not denied.stderr.strip().endswith(BOUNDARY) or not reason(denied).endswith(BOUNDARY):
            fail(f"a denied command must say it is a boundary: rc={denied.returncode} "
                 f"stderr={denied.stderr.strip()!r}")

        memory = run(home, edit("memory/core/safety.md", cwd=worktree), home)
        if memory.returncode != 2 or "no-edit" not in reason(memory):
            fail(f"an edit under memory/core must still deny: rc={memory.returncode} reason={reason(memory)!r}")

    print("FAIL" if failures else "ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
