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
for word in ("delegate_task", "role: <role>"):
    check(word in t3, f"AGENTS.md → T3 Code names {word!r}")

build = (ROOT / "agents" / "build.md").read_text()
check("delegate_task" in build, "agents/build.md dispatches through delegate_task")
check(re.search(r"call `advisor`|go to the explore agent", build) is None,
      "agents/build.md no longer names an opencode subagent call")

# The dispatch recipe lives in skills/t3-dispatch, loaded before a dispatch,
# not in AGENTS.md or build.md, which every session loads (prune, 2026-11-23).
skill_path = ROOT / "skills" / "t3-dispatch" / "SKILL.md"
skill = skill_path.read_text() if skill_path.exists() else ""
check(bool(skill), "skills/t3-dispatch/SKILL.md exists")
check("t3-dispatch" in build and "t3-dispatch" in t3, "build.md and AGENTS.md -> T3 Code point at the t3-dispatch skill")
for needle, label in (
    ("role: <role>", "the brief's first line is the role line"),
    ("~/.config/opencode/agents/<role>.md", "the brief names the installed role file, not the copy under review"),
    ('isolation: "worktree"', "worktree isolation"),
    ('interactionMode: "plan"', "plan mode for the read-only roles"),
    ("models.resolved.json", "the target comes from the role's resolved model"),
    ('isolation: "shared"', "an uncommitted change is reviewed in the shared checkout"),
    ("restart", "a plugin code change needs a restart"),
    ("review-log", "every review and consult is recorded"),
):
    check(needle in skill, f"t3-dispatch: {label}")
check(re.search(r"(?i)verifier[^.]*(not|without)[^.]*plan", skill) is not None, "t3-dispatch: the verifier is not sent in plan mode")
check(len(build) < 2000, f"agents/build.md stays small ({len(build)} chars)")
# The lead is a skeptical supervisor; the implementor does the heavy lifting
# (the person, 2026-11-23). The skill says what supervising means.
for needle, label in (
    ("skeptical", "the lead supervises skeptically"),
    ("git diff", "the lead reads the diff, not the summary"),
    ("oracle", "the lead looks for edits to the tests or oracle"),
    ("special-cases", "the lead looks for a fix that special-cases the check"),
    ("REJECT", "the lead sends broken work back with findings"),
):
    check(needle in skill, f"t3-dispatch: {label}")
ib = (ROOT / "skills" / "implementor-brief" / "SKILL.md").read_text()
# The person, 2026-11-23, after Phase 6b: a small change the lead does itself; a
# large one goes to an implementor under skeptical supervision.
doing = agents_md.split("## Doing the work", 1)[-1].split("\n\n", 2)[1]
for needle in ("small change yourself", "large one", "supervise it skeptically", "Never dispatch to avoid editing"):
    check(needle in doing, f"AGENTS.md -> Doing the work: {needle!r}")
check("small change yourself" in build and "Never dispatch to avoid editing" in build,
      "agents/build.md opens with the same split")
check("by size" in ib, "implementor-brief says AGENTS.md decides by size")
check("heavy lifting" in ib and "supervis" in ib, "implementor-brief: the implementor investigates and fixes; the lead supervises")
brief = (ROOT / "skills" / "implementor-brief" / "SKILL.md").read_text()
check("delegate_task" in brief and "agents/implementor.md" in brief, "implementor-brief dispatches via delegate_task and names agents/implementor.md")
check("agents/review-deep.md" in (ROOT / "commands" / "verify.md").read_text().split("delegate_task", 1)[-1],
      "commands/verify.md sends review-deep through delegate_task")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
