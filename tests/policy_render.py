#!/usr/bin/env python3
"""bin/sync-harness must render agents/verifier.md from policy/permissions.json,
and the native agent set for Claude Code / Grok Build."""

import importlib.machinery
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("sync_harness", str(ROOT / "bin" / "sync-harness"))
_spec = importlib.util.spec_from_loader("sync_harness", _loader)
sync = importlib.util.module_from_spec(_spec)
_loader.exec_module(sync)

policy = json.loads((ROOT / "policy" / "permissions.json").read_text())
targets = sync.repo_targets(policy, ROOT)
path = ROOT / "agents" / "verifier.md"
if path not in targets:
    print("FAIL: repo_targets does not render agents/verifier.md")
    sys.exit(1)
if targets[path] != path.read_text():
    print("FAIL: agents/verifier.md drifted from policy/permissions.json")
    sys.exit(1)

# The native set: implementor inherits the session model and tools; verifier
# keeps its sonnet pin and an explicit read+shell allowlist. `build` is absent on
# purpose: a rendered build is a dispatchable writer, which AGENTS.md forbids.
rendered = sync.render_claude_agents(policy, ROOT)
native = set(policy.get("native_agents", {}).get("agents", {}))
expected = {"implementor", "verifier"}
if native != expected:
    print(f"FAIL: policy native_agents {sorted(native)} != {sorted(expected)}")
    sys.exit(1)
if expected - set(rendered):
    print(f"FAIL: sync-harness does not render native agents: {sorted(expected - set(rendered))}")
    sys.exit(1)
if "build" in rendered:
    print("FAIL: sync-harness rendered build; it must stay a main-session role in AGENTS.md")
    sys.exit(1)

writers = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Task", "Agent", "WebFetch", "WebSearch"}


def tools_of(text: str) -> list[str] | None:
    match = re.search(r"^tools: (.+)$", text, flags=re.M)
    return match.group(1).split(", ") if match else None


def disallowed_of(text: str) -> list[str]:
    match = re.search(r"^disallowedTools: (.+)$", text, flags=re.M)
    return match.group(1).split(", ") if match else []


implementor = rendered["implementor"]
if re.search(r"^model:", implementor, flags=re.M):
    print("FAIL: native implementor pins a model; the session model must win")
    sys.exit(1)
if tools_of(implementor) is not None:
    print("FAIL: native implementor pins tools; it must inherit the harness default")
    sys.exit(1)
implementor_disallowed = disallowed_of(implementor)
for tool in ("Task", "Agent", "WebFetch", "WebSearch"):
    if tool not in implementor_disallowed:
        print(f"FAIL: native implementor must disallow {tool}, which agents/implementor.md denies")
        sys.exit(1)
if any(tool in implementor_disallowed for tool in ("Bash", "Edit", "Write", "Read")):
    print(f"FAIL: native implementor denies a tool it needs to write: {implementor_disallowed}")
    sys.exit(1)

verifier = rendered["verifier"]
model = re.search(r"^model: (.+)$", verifier, flags=re.M)
if not model or model.group(1) != "sonnet":
    print(f"FAIL: native verifier model is {model.group(1) if model else None!r}, expected 'sonnet'")
    sys.exit(1)
verifier_tools = tools_of(verifier) or []
bad = [t for t in verifier_tools if t in writers or (t.startswith("mcp__") and not t.startswith("mcp__roslynk__"))]
bad += [t for t in verifier_tools if t.startswith("mcp__roslynk__") and t[14:] not in policy["readonly_agents"]["roslynk_read_tools"]]
if not verifier_tools or bad:
    print(f"FAIL: native verifier tools must be an explicit read+shell allowlist; got {verifier_tools!r} bad={bad!r}")
    sys.exit(1)
if "Skill" not in verifier_tools:
    print("FAIL: native verifier must keep Skill so it can load run-tests")
    sys.exit(1)
if not {"Edit", "Write", "Task", "WebFetch", "WebSearch", "mcp__roslynk__apply_patch", "mcp__roslynk__rename_symbol"} <= set(disallowed_of(verifier)):
    print(f"FAIL: native verifier disallowedTools is incomplete: {disallowed_of(verifier)!r}")
    sys.exit(1)

for name, text in rendered.items():
    if text.count("---\n") < 2 or "BEGIN managed by bin/sync-harness" in text:
        print(f"FAIL: rendered native agent {name} leaked the opencode frontmatter")
        sys.exit(1)

# A native agent file the user wrote is backed up, never overwritten silently.
with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    agents = home / ".claude" / "agents"
    agents.mkdir(parents=True)
    foreign = agents / "verifier.md"
    foreign.write_text("---\nname: verifier\n---\nMy own prompt.\n")
    for path, text in sync.agents_changes(policy, ROOT, home):
        sync.write_agent(path, text)
    backups = list(agents.glob("verifier.md.bak-*"))
    if len(backups) != 1 or "My own prompt." not in backups[0].read_text():
        print("FAIL: a hand-written native agent file was not backed up before overwrite")
        sys.exit(1)

print("ok")
