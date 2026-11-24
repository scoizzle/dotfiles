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

# Review of 9b4175f (Opus): drift checks, not only phrases.
STATUS = re.compile(r"`(done|blocked|unreviewed|needs-answer)`")
impl = (ROOT / "agents" / "implementor.md").read_text()
check(set(STATUS.findall(text)) == set(STATUS.findall(impl)) == {"done", "blocked", "unreviewed", "needs-answer"},
      "the skill and implementor.md name the same return statuses")
check(re.search(r"(?i)briefed.{0,220}(does not|never) open", impl.replace("\n", " ")) is not None,
      "implementor.md says a briefed implementor commits and returns, and does not open the PR")
check(re.search(r"(?i)lead pushes", text) is not None, "the brief has the lead push its base before dispatch")
# The eval reported (Phase 8, 2026-11-24) and the rule moved into AGENTS.md; the
# skill still says AGENTS.md, not the skill, decides whether to dispatch.
check(re.search(r"(?i)AGENTS\.md`?\s*→\s*Doing the work decides whether to dispatch", text.replace("\n", " ")) is not None,
      "the skill defers to AGENTS.md on whether to dispatch")
check(re.search(r"(?i)no `git stash`", text) is not None, "the brief forbids git stash, not merely names it")

# 2026-11-24: an implementor session loads agents/implementor.md instead of
# AGENTS.md (plugin context hook), so the file must carry every AGENTS.md rule an
# implementor needs (advisor). A rule missing here is a rule the implementor lost.
for needle, rule in (
    ("git add -A", "stage only touched paths, never git add -A"),
    ("default branch", "never on the default branch"),
    ("git stash", "no git stash; a WIP commit instead"),
    ("boundary", "a denied command is a boundary, not an obstacle"),
    ("no undo", "stop before a change with no undo"),
    ("weaken", "never weaken a test"),
    ("needs-answer", "intent goes back as needs-answer"),
    ("design choice", "the advisor triggers stop the work"),
    ("failed twice", "the advisor triggers stop the work"),
    ("flaky", "a flaky test stops the work"),
    ("memory/core", "never edit memory/core"),
    ("roslynk-rules", "load roslynk-rules before C#"),
    ("run-tests", "load run-tests before a .NET test command"),
    ("sensitive", "a sensitive change is reported for review"),
    ("network", "solve from the repository, never download the fix"),
    ("last test", "never remove the last test that covers a behaviour (review)"),
    ("git status", "green means a named commit and a git status you read"),
    ("not installed", "a skill routing to a missing sibling: say it is not installed"),
):
    check(needle in impl, f"implementor.md carries: {rule}")

# Every sensitive path in AGENTS.md is in implementor.md's list (review, 2026-11-24).
agents_md = (ROOT / "AGENTS.md").read_text()
listed = re.findall(r"`([^`]+)`", agents_md.split("**Sensitive change:**", 1)[1].split("A CI workflow", 1)[0])
for path in listed:
    check(path in impl, f"implementor.md lists the sensitive path {path}")
for word in ("auth", "secrets", "credentials", "migration"):
    check(word in impl, f"implementor.md lists sensitive {word}")

print(f"\n{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
