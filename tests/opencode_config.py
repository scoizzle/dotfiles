#!/usr/bin/env python3
"""opencode.json carries the few rules v2 keeps (the person, 2026-11-24).

All dispatch is T3 delegate_task, so opencode's own `subagent` tool is denied;
writes outside the checkout do not ask; every agent reads its model from its
role file. Everything else agents may do (the person: "ENABLE the agents").
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


config = json.loads((ROOT / "opencode.json").read_text())
rules = config.get("permissions", [])


def effect(action: str) -> str | None:
    found = [r["effect"] for r in rules if r.get("action") == action and r.get("resource") == "*"]
    return found[-1] if found else None


check(effect("subagent") == "deny", "opencode's subagent tool is denied: dispatch is T3 delegate_task")
# Two skills no session loads (they conflict with this harness); this held only
# through bin/sync-harness's drift check before it went (advisor, 2026-11-24).
skills = {r["resource"] for r in rules if r.get("action") == "skill" and r.get("effect") == "deny"}
check({"antigravity2.0", "pre-ship-review"} <= skills, f"the antigravity2.0 and pre-ship-review skills are denied ({sorted(skills)})")
check(effect("external_directory") == "allow", "writes outside the checkout do not ask")
check(not [r for r in rules if r.get("action") in ("shell", "read", "edit")],
      "no shell, read or edit rules remain: agents are not limited there")
roles = json.loads((ROOT / "models" / "roles.json").read_text())
agents = config.get("agents", config.get("agent", {}))
for name, role in roles["agents"].items():
    model = (agents.get(name) or {}).get("model")
    check(model == "{file:~/.config/opencode/models/%s}" % role, f"agent {name} reads its model from the {role} role file")
# Review, 2026-11-24: agent frontmatter outranks the global rule, so no agent
# may re-allow opencode's own dispatch.
# Each `- key: value` list entry is read whole, in any key order, quotes stripped.
def entries(front: str) -> list[dict]:
    out = []
    for line in front.splitlines():
        m = re.match(r"^\s*(-\s+)?(\w+):\s*(.*?)\s*$", line)
        if not m:
            continue
        if m.group(1):
            out.append({})
        if out:
            out[-1][m.group(2)] = m.group(3).strip("'\"")
    return out


for path in sorted((ROOT / "agents").glob("*.md")):
    front = path.read_text().split("\n---\n", 1)[0]
    bad = [e for e in entries(front) if e.get("action") == "subagent" and e.get("effect") != "deny"]
    check(not bad, f"agents/{path.name} does not re-allow subagent ({bad})")
for path in (ROOT / "agents").glob("*.md"):
    check(path.stem in agents or path.stem in ("build",), f"agents/{path.name} is rendered into opencode.json")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
