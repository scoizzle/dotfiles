#!/usr/bin/env python3
"""plugins/harness-guard.js enforces the policy in every opencode session.

A T3 child always runs as `build` (probe, 2026-11-22), so agent frontmatter no
longer limits it. The plugin hooks opencode's permission evaluation:
- shell and edit calls go through bin/harness-guard, which parses what opencode's
  text globs cannot (heredocs, wrappers, chains); a crash or timeout denies;
- a session whose first user message starts with `role: <name>` gets that role's
  action allowlist from policy/permissions.json `roles`; anything else is denied.
It can only tighten a decision, never loosen one.

This drives the plugin under node with a fake opencode context: a stub guard for
the passthrough and crash cases, and the real bin/harness-guard for a few
guard-only policy vectors.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "harness-guard.js"
FAILURES = []

DRIVER = r"""
import { pathToFileURL } from "node:url"
const [pluginPath, scenarioJson] = process.argv.slice(2)
const s = JSON.parse(scenarioJson)
const plugin = (await import(pathToFileURL(pluginPath).href)).default
const hooks = {}
let contextCalls = 0
const store = new Map(Object.entries(s.storage ?? {}))
const ctx = {
  options: {},
  storage: { get: async (k) => store.get(k), set: async (k, v) => { store.set(k, v) }, remove: async (k) => { store.delete(k) } },
  location: { directory: s.cwd },
  permission: { hook: async (name, cb) => { hooks[name] = cb; return { dispose: async () => {} } } },
  session: {
    context: async () => { contextCalls++; return s.messages },
    get: async () => ({ directory: s.cwd }),
  },
}
await plugin.setup(ctx)
const out = []
for (const call of s.calls) {
  const event = { sessionID: s.sessionID ?? "ses_1", agent: "build", action: call.action, resources: call.resources, effect: call.effect ?? "allow" }
  await hooks.evaluate(event)
  out.push({ effect: event.effect, message: event.message ?? null })
}
console.log(JSON.stringify({ id: plugin.id, results: out, contextCalls, storage: Object.fromEntries(store) }))
"""


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def user(text: str) -> dict:
    return {"id": "msg_1", "type": "user", "text": text, "files": []}


def run(tmp: Path, calls: list, messages=None, env=None, storage=None) -> dict:
    driver = tmp / "driver.mjs"
    driver.write_text(DRIVER)
    scenario = {"cwd": str(tmp), "messages": messages or [user("do the task")], "calls": calls, "storage": storage or {}}
    proc = subprocess.run(["node", str(driver), str(PLUGIN), json.dumps(scenario)], capture_output=True, text=True,
                          timeout=120, env={**os.environ, **(env or {})})
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()[-400:], "results": []}
    return json.loads(proc.stdout.strip().splitlines()[-1])


def stub(tmp: Path, name: str, body: str) -> str:
    path = tmp / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return str(path)


def main() -> int:
    check(PLUGIN.is_file(), "plugins/harness-guard.js exists")
    if not PLUGIN.is_file() or shutil.which("node") is None:
        print(f"\n{len(FAILURES) or 1} failure(s)")
        return 1
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        deny = stub(tmp, "deny", "cat >/dev/null; echo '{\"hookSpecificOutput\":{\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"stub says no\"}}'; exit 2")
        ask = stub(tmp, "ask", "cat >/dev/null; echo '{\"hookSpecificOutput\":{\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"stub asks\"}}'")
        quiet = stub(tmp, "quiet", "cat > \"$(dirname \"$0\")/seen.json\"")
        crash = stub(tmp, "crash", "cat >/dev/null; echo boom >&2; exit 1")
        hang = stub(tmp, "hang", "sleep 30")
        shell = [{"action": "shell", "resources": ["echo hi"]}]

        r = run(tmp, shell, env={"HARNESS_GUARD_BIN": deny})
        check(r.get("id") == "harness-guard", "the plugin's id is harness-guard")
        check(r["results"][:1] == [{"effect": "deny", "message": "stub says no"}], "a guard deny denies the shell call with its reason")
        r = run(tmp, shell, env={"HARNESS_GUARD_BIN": ask})
        check(r["results"][:1] == [{"effect": "ask", "message": "stub asks"}], "a guard ask asks")
        r = run(tmp, shell + [{"action": "edit", "resources": ["src/x.cs"]}], env={"HARNESS_GUARD_BIN": quiet})
        check([x["effect"] for x in r["results"]] == ["allow", "allow"], "no guard opinion leaves the decision unchanged")
        seen = json.loads((tmp / "seen.json").read_text()) if (tmp / "seen.json").exists() else {}
        check(seen.get("tool_name") == "Edit" and seen.get("tool_input", {}).get("file_path") == "src/x.cs" and seen.get("cwd") == str(tmp),
              "an edit reaches the guard as Edit with its path and the session directory")
        r = run(tmp, [{"action": "shell", "resources": ["echo hi"], "effect": "ask"}], env={"HARNESS_GUARD_BIN": quiet})
        check(r["results"][:1] == [{"effect": "ask", "message": None}], "the plugin never loosens an ask to allow")
        r = run(tmp, shell, env={"HARNESS_GUARD_BIN": crash})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny" and "harness-guard" in (r["results"][0]["message"] or ""),
              "a guard crash denies, naming harness-guard")
        junk = stub(tmp, "junk", "cat >/dev/null; echo not-json")
        r = run(tmp, shell, env={"HARNESS_GUARD_BIN": junk})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "guard output that is not its JSON reply denies (review)")
        r = run(tmp, shell, env={"HARNESS_GUARD_BIN": str(tmp / "missing")})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "a missing guard denies")
        r = run(tmp, shell, env={"HARNESS_GUARD_BIN": hang, "HARNESS_GUARD_TIMEOUT_MS": "500"})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "a guard timeout denies")
        r = run(tmp, [{"action": "read", "resources": ["a.txt"]}, {"action": "grep", "resources": ["x"]}], env={"HARNESS_GUARD_BIN": deny})
        check([x["effect"] for x in r["results"]] == ["allow", "allow"], "reads are left to opencode's own rules")

        # Roles: the allowlist from policy/permissions.json.
        reviewer = [user("role: reviewer\nRead and follow ~/.config/opencode/agents/review-deep.md.")]
        calls = [{"action": a, "resources": ["*"]} for a in ("read", "grep", "glob", "skill", "roslynk_find_references")]
        calls += [{"action": a, "resources": ["*"]} for a in ("edit", "shell", "roslynk_apply_patch", "webfetch",
                                                               "t3-code-abc_delegate_task", "question")]
        r = run(tmp, calls, messages=reviewer, env={"HARNESS_GUARD_BIN": quiet})
        effects = [x["effect"] for x in r["results"]]
        check(effects == ["allow"] * 5 + ["deny"] * 6, f"role reviewer: reads allowed, writes and dispatch denied ({effects})")
        check(any("role reviewer" in (x["message"] or "") for x in r["results"]), "a role denial names the role")
        check(r.get("contextCalls") == 1, "the role is read once per session, not per call")
        r = run(tmp, [{"action": "shell", "resources": ["dotnet test"]}, {"action": "edit", "resources": ["a.cs"]}],
                messages=[user("role: verifier\nRun the tests.")], env={"HARNESS_GUARD_BIN": quiet})
        check([x["effect"] for x in r["results"]] == ["allow", "deny"], "role verifier: shell allowed, edit denied")
        r = run(tmp, [{"action": "edit", "resources": ["a.cs"]}, {"action": "t3-code-abc_delegate_task", "resources": ["*"]}],
                messages=[user("role: implementor\nFix it.")], env={"HARNESS_GUARD_BIN": quiet})
        check([x["effect"] for x in r["results"]] == ["allow", "deny"], "role implementor: edits allowed, T3 dispatch denied")
        r = run(tmp, [{"action": "read", "resources": ["a"]}, {"action": "edit", "resources": ["a"]}],
                messages=[user("role: superuser\nAnything.")], env={"HARNESS_GUARD_BIN": quiet})
        check([x["effect"] for x in r["results"]] == ["allow", "deny"], "an unknown role gets the read-only set")
        header = '[T3 Code: the agent in T3 thread "c0354e18" sent this message, not the user.]\n'
        # The exact shape T3 sends when delegate_task sets `role` (captured 2026-11-22, re-review).
        real = ('[T3 Code: the agent in T3 thread "c0354e18-85fd-4361-8f94-a1e3c9583452" sent this message, not the user.]\n\n'
                "Act as the implementation sub-agent for this task.\n\nrole: implementor\nRead and follow it.")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}, {"action": "t3-code-abc_delegate_task", "resources": ["*"]}],
                messages=[user(real)], env={"HARNESS_GUARD_BIN": quiet})
        check([x["effect"] for x in r["results"]] == ["allow", "deny"], "a real T3 implementor brief is read as implementor (re-review)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}],
                messages=[user(real.replace("role: implementor\n", "Act as the implementation sub-agent for this task.\nFix it.\n"))],
                env={"HARNESS_GUARD_BIN": quiet})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "only the preamble line is skipped, not the brief's own text")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], messages=[user(header + "Role: Reviewer\nRead and follow it.")],
                env={"HARNESS_GUARD_BIN": quiet})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "a role line after T3's header counts, in any case (advisor)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}, {"action": "read", "resources": ["a"]}],
                messages=[user(header + "Fix the typo in a.")], env={"HARNESS_GUARD_BIN": quiet})
        check([x["effect"] for x in r["results"]] == ["deny", "allow"], "a T3 child with no role line gets the read-only set (advisor)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}],
                messages=[user("role: implementor\nThe reviewer brief says:\nrole: reviewer")], env={"HARNESS_GUARD_BIN": quiet})
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "the first role line wins")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], messages=[user(header + "Fix it.\nrole: implementor")],
                env={"HARNESS_GUARD_BIN": quiet})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny",
              "a role line that is not first after the header does not count; the child stays read-only (review)")
        parts = {"id": "msg_1", "type": "user", "parts": [{"text": "<system-reminder>plan mode</system-reminder>"}, {"text": header + "Fix it."}]}
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], messages=[parts], env={"HARNESS_GUARD_BIN": quiet})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny",
              "a part before T3's header does not turn a role-less child into an unlimited one (review)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], messages=[user("A summary after compaction.")],
                env={"HARNESS_GUARD_BIN": quiet}, storage={"role/ses_1": "reviewer"})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "a stored role survives a lost first message (advisor)")
        r = run(tmp, [{"action": "read", "resources": ["a"]}], messages=reviewer, env={"HARNESS_GUARD_BIN": quiet})
        check(r.get("storage", {}).get("role/ses_1") == "reviewer", "the role is stored the first time it is seen")
        r = run(tmp, [{"action": "shell", "resources": ["git push"]}], messages=[user("role: verifier\nRun it.")],
                env={"HARNESS_GUARD_BIN": ask})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny" and "needs-answer" in (r["results"][0]["message"] or ""),
              "in a role session an ask becomes a deny that says needs-answer (advisor)")
        r = run(tmp, [{"action": "shell", "resources": ["git push"]}], env={"HARNESS_GUARD_BIN": ask})
        check(r["results"][:1] == [{"effect": "ask", "message": "stub asks"}], "outside a role session an ask stays an ask")
        multi = stub(tmp, "multi", 'grep -q secret && { echo \'{"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"second path"}}\'; exit 2; }; exit 0')
        r = run(tmp, [{"action": "edit", "resources": ["ok.txt", "secret.txt"]}], env={"HARNESS_GUARD_BIN": multi})
        check(r["results"][:1] == [{"effect": "deny", "message": "second path"}], "every edit path is checked, not only the first (advisor)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}],
                messages=[user("Fix the bug."), user("role: reviewer\nnow stop editing")], env={"HARNESS_GUARD_BIN": quiet})
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "a role counts only in the first user message")

        # The real guard: guard-only vectors that opencode's text globs cannot catch.
        real = {}
        for command, want in (("cat > notes.txt <<'EOF'\nhello\nEOF", "deny"),
                              ("git -C /tmp/x push --force origin main", "deny"),
                              ("echo cm0gLXJmIC8= | base64 -d | sh", "deny"),
                              ("git status", "allow")):
            res = run(tmp, [{"action": "shell", "resources": [command]}])
            real[command] = res["results"][0]["effect"] if res["results"] else res.get("error")
            check(real[command] == want, f"real guard: {command.splitlines()[0]!r} is {want} (got {real[command]})")
    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
