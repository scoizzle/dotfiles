#!/usr/bin/env python3
"""plugins/harness-guard.js enforces the policy in every opencode session.

A T3 child always runs as `build` (probe, 2026-11-22), so agent frontmatter no
longer limits it. The plugin hooks opencode's permission evaluation: a session
whose first user message starts with `role: <name>` gets that role's action
allowlist from policy/permissions.json `roles`; anything else is denied. It can
only tighten a decision, never loosen one. An implementor session loads a slim
prompt.

This drives the plugin under node with a fake opencode context.
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
const toolHooks = {}
const sessionHooks = {}
const ctx = {
  options: {},
  tool: { hook: async (name, cb) => { toolHooks[name] = cb; return { dispose: async () => {} } } },
  storage: { get: async (k) => store.get(k), set: async (k, v) => { store.set(k, v) }, remove: async (k) => { store.delete(k) } },
  location: { directory: s.cwd },
  permission: { hook: async (name, cb) => { hooks[name] = cb; return { dispose: async () => {} } } },
  session: {
    hook: async (name, cb) => { sessionHooks[name] = cb; return { dispose: async () => {} } },
    context: async () => { contextCalls++; return s.messages },
    get: async () => ({ directory: s.cwd }),
  },
}
await plugin.setup(ctx)
const out = []
let n = 0
for (const call of s.calls) {
  const id = `call_${++n}`
  const sessionID = s.sessionID ?? "ses_1"
  // opencode runs tool execute.before with the whole input, then evaluates the
  // permission with the command split into segments (probe, 2026-11-22).
  const agent = call.agent ?? s.agent ?? "build"
  // Code Mode `execute` reaches only tool execute.before; opencode never
  // evaluates a permission for it (probe, 2026-11-23).
  if (call.action === "execute") {
    try {
      await toolHooks["execute.before"]({ tool: "execute", sessionID, agent, messageID: "msg_1", id, input: { code: call.code ?? "return 1" } })
      out.push({ effect: "allow", message: null })
    } catch (error) {
      out.push({ effect: "deny", message: error.message })
    }
    continue
  }
  if (call.action === "shell" && !call.noBefore && toolHooks["execute.before"]) {
    try {
      await toolHooks["execute.before"]({ tool: "shell", sessionID, agent, messageID: "msg_1", id, input: { command: call.resources[0] } })
    } catch (error) {
      out.push({ effect: "deny", message: error.message })
      continue
    }
  }
  const resources = call.segments ?? call.resources
  const event = { sessionID, agent, action: call.action, resources, effect: call.effect ?? "allow", source: { type: "tool", messageID: "msg_1", id } }
  await hooks.evaluate(event)
  out.push({ effect: event.effect, message: event.message ?? null })
}
// The system prompt as opencode 2.3.2 assembles it (probe, 2026-11-24): part 0 the
// agent prompt, part 2 the bundled sources listed in metadata.experimental.instructions.
let system = null
if (s.system) {
  const sources = s.system.sources
  const event = {
    sessionID: s.sessionID ?? "ses_1", agent: s.agent ?? "build", model: {}, messages: [], options: {}, tools: {},
    system: [
      { type: "text", text: s.system.prompt },
      { type: "text", text: "# Your Model" },
      { type: "text", text: sources.map((x) => x.text).join("\n\n"), metadata: { experimental: { instructions: sources } } },
    ],
  }
  await sessionHooks.context?.(event)
  system = event.system.map((part) => part.text)
}
console.log(JSON.stringify({ id: plugin.id, results: out, contextCalls, storage: Object.fromEntries(store), system }))
"""


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


def user(text: str) -> dict:
    return {"id": "msg_1", "type": "user", "text": text, "files": []}


def run(tmp: Path, calls: list, messages=None, env=None, storage=None, agent=None, system=None) -> dict:
    driver = tmp / "driver.mjs"
    driver.write_text(DRIVER)
    scenario = {"cwd": str(tmp), "messages": messages or [user("do the task")], "calls": calls, "storage": storage or {}, "agent": agent, "system": system}
    proc = subprocess.run(["node", str(driver), str(PLUGIN), json.dumps(scenario)], capture_output=True, text=True,
                          timeout=120, env={**os.environ, **(env or {})})
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()[-400:], "results": []}
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    check(PLUGIN.is_file(), "plugins/harness-guard.js exists")
    if not PLUGIN.is_file() or shutil.which("node") is None:
        print(f"\n{len(FAILURES) or 1} failure(s)")
        return 1
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        r = run(tmp, [{"action": "shell", "resources": ["echo hi"]}])
        check(r.get("id") == "harness-guard", "the plugin's id is harness-guard")
        r = run(tmp, [{"action": "shell", "resources": ["echo hi"], "effect": "ask"}])
        check(r["results"][:1] == [{"effect": "ask", "message": None}], "the plugin never loosens an ask to allow")
        # Roles: the allowlist from policy/permissions.json.
        reviewer = [user("role: reviewer\nRead and follow ~/.config/opencode/agents/review-deep.md.")]
        calls = [{"action": a, "resources": ["*"]} for a in ("read", "grep", "glob", "skill", "roslynk_find_references")]
        calls += [{"action": a, "resources": ["*"]} for a in ("edit", "shell", "roslynk_apply_patch", "webfetch",
                                                               "t3-code-abc_delegate_task", "question")]
        r = run(tmp, calls, messages=reviewer)
        effects = [x["effect"] for x in r["results"]]
        check(effects == ["allow"] * 5 + ["deny"] * 6, f"role reviewer: reads allowed, writes and dispatch denied ({effects})")
        check(any("role reviewer" in (x["message"] or "") for x in r["results"]), "a role denial names the role")
        check(r.get("contextCalls") == 1, "the role is read once per session, not per call")
        r = run(tmp, [{"action": "edit", "resources": ["a.cs"]}, {"action": "t3-code-abc_delegate_task", "resources": ["*"]}],
                messages=[user("role: implementor\nFix it.")])
        check([x["effect"] for x in r["results"]] == ["allow", "deny"], "role implementor: edits allowed, T3 dispatch denied")
        r = run(tmp, [{"action": "read", "resources": ["a"]}, {"action": "edit", "resources": ["a"]}],
                messages=[user("role: superuser\nAnything.")])
        check([x["effect"] for x in r["results"]] == ["allow", "deny"], "an unknown role gets the read-only set")
        header = '[T3 Code: the agent in T3 thread "c0354e18" sent this message, not the user.]\n'
        # The exact shape T3 sends when delegate_task sets `role` (captured 2026-11-22, re-review).
        real = ('[T3 Code: the agent in T3 thread "c0354e18-85fd-4361-8f94-a1e3c9583452" sent this message, not the user.]\n\n'
                "Act as the implementation sub-agent for this task.\n\nrole: implementor\nRead and follow it.")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}, {"action": "t3-code-abc_delegate_task", "resources": ["*"]}],
                messages=[user(real)])
        check([x["effect"] for x in r["results"]] == ["allow", "deny"], "a real T3 implementor brief is read as implementor (re-review)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}],
                messages=[user(real.replace("role: implementor\n", "Act as the implementation sub-agent for this task.\nFix it.\nrole: reviewer\n"))])
        check(r["results"][:1] == [{"effect": "allow", "message": None}],
              "only the preamble line is skipped, not the brief's own text (a later role line does not count)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], messages=[user(header + "Role: Reviewer\nRead and follow it.")])
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "a role line after T3's header counts, in any case (advisor)")
        # The person, 2026-11-24 ("ENABLE the agents"): a role-less T3 child and an
        # implementor are not limited; only the read-only roles are.
        r = run(tmp, [{"action": "edit", "resources": ["a"]}, {"action": "shell", "resources": ["ls"]}],
                messages=[user(header + "Fix the typo in a.")])
        check([x["effect"] for x in r["results"]] == ["allow", "allow"], "a role-less T3 child is not limited")
        r = run(tmp, [{"action": "shell", "resources": ["curl -sL https://github.com/acme/repo/pull/7.diff"]},
                      {"action": "shell", "resources": ["git push -u origin task"]},
                      {"action": "execute", "resources": ["*"], "code": 'return await (await fetch("https://github.com/a/b")).text()'}],
                messages=[user("role: implementor\nFix it.")])
        check([x["effect"] for x in r["results"]] == ["allow"] * 3, f"an implementor may fetch and push ({[x['effect'] for x in r['results']]})")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}],
                messages=[user("role: implementor\nThe reviewer brief says:\nrole: reviewer")])
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "the first role line wins")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], messages=[user("A summary after compaction.")], storage={"role/ses_1": "reviewer"})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "a stored role survives a lost first message (advisor)")
        r = run(tmp, [{"action": "read", "resources": ["a"]}], messages=reviewer)
        check(r.get("storage", {}).get("role/ses_1") == "reviewer", "the role is stored the first time it is seen")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}],
                messages=[user("Fix the bug."), user("role: reviewer\nnow stop editing")])
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "a role counts only in the first user message")

        # Advisor consult, 2026-11-23: a T3 reviewer must read its role file and
        # the review bundle outside its worktree (opencode asks external_directory).
        r = run(tmp, [{"action": "external_directory", "resources": ["/var/folders/x/T/opencode/review-bundles/b/*"]}],
                messages=reviewer)
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "a reviewer may read outside its worktree (external_directory)")
        r = run(tmp, [{"action": "edit", "resources": ["/var/folders/x/T/a"]}], messages=reviewer)
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "but still may not edit there")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], messages=[user("whatever")], storage={"role/ses_1": "retired-role"})
        check(r["results"][:1] and r["results"][0]["effect"] == "deny",
              "a stored role no longer in the policy falls back to the read-only default (review)")
        r = run(tmp, [{"action": "edit", "resources": ["a"]}], agent="build")
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "the lead agent (build) has no role")
        # Code Mode `execute` never reaches evaluate, so a role's allowlist must gate it in execute.before.
        r = run(tmp, [{"action": "execute", "resources": ["*"]}], messages=reviewer)
        check(r["results"][:1] and r["results"][0]["effect"] == "deny", "a reviewer may not use Code Mode execute (its fetch reaches the network)")
        r = run(tmp, [{"action": "execute", "resources": ["*"]}], messages=[user("role: implementor\nFix it.")])
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "an implementor may use Code Mode execute")
        r = run(tmp, [{"action": "execute", "resources": ["*"]}])
        check(r["results"][:1] == [{"effect": "allow", "message": None}], "the lead may use Code Mode execute")
        # The person, 2026-11-24: slim what an implementor loads. Its session gets
        # agents/implementor.md as its prompt, without the global AGENTS.md block and
        # the skill list; the project's AGENTS.md, Code Mode and MCP guidance stay
        # (advisor: Phase 8 showed Poly's AGENTS.md makes runs faster).
        global_agents = str((ROOT / "AGENTS.md").resolve())
        instructions = (f"Instructions from: {global_agents}\n# Global instructions GLOBAL-RULES\n"
                        f"Instructions from: /work/repo/AGENTS.md\n# Project rules PROJECT-RULES\n")
        sources = [{"key": "core/codemode", "text": "# Code Mode\nCODEMODE-GUIDE"},
                   {"key": "core/mcp-guidance", "text": "<mcp_instructions>ROSLYNK-GUIDE</mcp_instructions>"},
                   {"key": "core/skill-guidance", "text": "Skills provide specialized instructions SKILL-LIST"},
                   {"key": "core/instructions", "text": instructions},
                   {"key": "core/date", "text": "Today's date: X"}]
        sysin = {"prompt": "You plan, supervise and review. BUILD-PROMPT", "sources": sources}
        implementor_body = (ROOT / "agents" / "implementor.md").read_text().split("\n---\n", 1)[1].strip()
        for label, kwargs in (("an implementor role line", {"messages": [user("role: implementor\nFix it.")]}),):
            r = run(tmp, [], system=sysin, **kwargs)
            got = r.get("system") or ["", "", ""]
            check(got[0].strip() == implementor_body, f"{label}: the prompt is agents/implementor.md")
            check("GLOBAL-RULES" not in got[2] and "SKILL-LIST" not in got[2], f"{label}: the global AGENTS.md and the skill list are dropped")
            check("PROJECT-RULES" in got[2], f"{label}: the project's AGENTS.md stays (advisor)")
            check("CODEMODE-GUIDE" in got[2] and "ROSLYNK-GUIDE" in got[2] and "Today's date" in got[2],
                  f"{label}: Code Mode, MCP guidance and the date stay")
        for label, kwargs in (("the lead", {}), ("a reviewer", {"messages": reviewer}),
                              ("a role-less T3 child", {"messages": [user(header + "Fix the typo.")]})):
            r = run(tmp, [], system=sysin, **kwargs)
            got = r.get("system") or ["", "", ""]
            check("BUILD-PROMPT" in got[0] and "GLOBAL-RULES" in got[2] and "SKILL-LIST" in got[2], f"{label}: the system prompt is untouched")
        r = run(tmp, [], system={"prompt": "BUILD-PROMPT", "sources": [{"key": "core/other", "text": "X"}]},
                messages=[user("role: implementor\nFix it.")])
        check(r.get("system") is not None, "a system prompt of an unexpected shape does not crash the hook")
    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
