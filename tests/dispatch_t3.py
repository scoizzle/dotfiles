#!/usr/bin/env python3
"""All agent orchestration goes through T3 delegate_task (the person, 2026-11-22).

opencode's own `subagent` tool is denied everywhere, so plain opencode has no
dispatch and a sensitive change stops and asks. A T3 child on opencode always
runs as the default `build` agent (probe, 2026-11-22: delegate_task has no agent
selector, and plan mode leaves the write tools listed), so a read-only role is
dispatched with isolation "worktree", interactionMode "plan", and a brief that
opens with its agents/<role>.md.
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


def frontmatter(path: Path) -> str:
    text = path.read_text()
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return match.group(1) if match else ""


def subagent_effects(front: str) -> list[str]:
    """Effects of the `subagent` rules in an agent's permissions, in order."""
    return re.findall(r"- action: subagent\n\s+resource: [^\n]*\n\s+effect: (\w+)", front)


config = json.loads((ROOT / "opencode.json").read_text())
rules = config.get("permissions", [])
global_subagent = [r["effect"] for r in rules if r.get("action") == "subagent" and r.get("resource") == "*"]
check(global_subagent[-1:] == ["deny"], "opencode.json denies the subagent tool globally")

policy = json.loads((ROOT / "policy" / "permissions.json").read_text())
check("subagent" in policy["opencode"].get("tool_deny", []), "policy/permissions.json is the source of that deny")

for path in sorted((ROOT / "agents").glob("*.md")):
    check("allow" not in subagent_effects(frontmatter(path)), f"agents/{path.name} does not re-allow subagent")

for path in sorted((ROOT / "commands").glob("*.md")):
    check(re.search(r"(?m)^subagent:\s*true", frontmatter(path)) is None,
          f"commands/{path.name} does not run as an opencode subagent")

agents_md = (ROOT / "AGENTS.md").read_text()
t3 = agents_md.split("## T3 Code", 1)[-1].split("\n## ", 1)[0]
for word in ("delegate_task", "isolation", "worktree", "plan", "agents/<role>.md", "role: <role>"):
    check(word in t3, f"AGENTS.md → T3 Code names {word!r}")

build = (ROOT / "agents" / "build.md").read_text()
check("delegate_task" in build, "agents/build.md dispatches through delegate_task")
check(re.search(r"call `advisor`|go to the explore agent", build) is None,
      "agents/build.md no longer names an opencode subagent call")

# Advisor consult, 2026-11-22: each brief names its role file, and the verifier,
# which runs tests, is not sent in plan mode.
check('Read and follow ~/.config/opencode/agents/<role>.md' in build and 'never the copy in the checkout under review' in build, "agents/build.md gives the read-only brief's opening line")
check(re.search(r"verifier brief the same without plan mode", build) is not None, "agents/build.md sends the verifier without plan mode")
check(re.search(r"(?i)that file's limits govern", build) is not None, "agents/build.md defers to a role brief")
brief = (ROOT / "skills" / "implementor-brief" / "SKILL.md").read_text()
check("delegate_task" in brief and "agents/implementor.md" in brief, "implementor-brief dispatches via delegate_task and names agents/implementor.md")
check("agents/review-deep.md" in (ROOT / "commands" / "verify.md").read_text().split("delegate_task", 1)[-1],
      "commands/verify.md sends review-deep through delegate_task")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
