#!/usr/bin/env python3
"""The lead briefs an implementor with skills/implementor-brief, and it carries
what an implementor cannot work out for itself.

From docs/v2-plan.md (Roles) and poteto's "say the goal, not the ceremony":
a brief has the goal, a done check that can pass or fail, the proof wanted, what
the lead already knows, and the real constraints; plus the files in scope, a
base to branch from, and at most three issues. Each requirement traces to a
lesson: delegate worktrees are cut from the parent's commit (2026-11-21), and
DeepSeek delegates past ~3 issues hit their step limit and leave work
uncommitted (2026-11-21). The implementor returns its head SHA and the red and
green commands with exit codes, never stashes, and stops with needs-answer
rather than guessing intent.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "implementor-brief" / "SKILL.md"
FAILURES = []


def check(ok: bool, label: str) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        FAILURES.append(label)


text = SKILL.read_text() if SKILL.exists() else ""
check(bool(text), "skills/implementor-brief/SKILL.md exists")
lower = text.lower()
for part in ("goal", "done check", "proof", "already know", "constraints"):
    check(part in lower, f"the brief names its {part!r} part")
check("git fetch origin" in text and "checkout -b" in text, "the brief starts the branch from a fetched base")
check(re.search(r"at most (three|3) issues", lower) is not None, "the brief caps a task at three issues")
check("head sha" in lower and "exit code" in lower, "the implementor returns its head SHA and exit codes")
check("needs-answer" in text, "an intent question comes back as needs-answer")
check("git stash" in text, "the brief forbids git stash")
check("implementor-brief" in (ROOT / "agents" / "build.md").read_text(), "the lead's agent file points at the skill")
check("implementor-brief" in (ROOT / "agents" / "implementor.md").read_text(), "the implementor's agent file knows the brief's shape")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
