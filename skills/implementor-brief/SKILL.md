---
name: implementor-brief
description: How the lead writes a task for an implementor (the `implementor` role, usually a cheaper model in its own worktree) and what the implementor must return. Use before dispatching implementation with delegate_task, or when you are an implementor reading a brief.
license: MIT
compatibility: opencode
---

# Implementor brief

When you dispatch, the implementor does the heavy lifting: the investigation and the fix. The lead
is a skeptical supervisor: it spends its tokens checking the result (see
`t3-dispatch` → After it returns), not doing the diagnosis for the implementor.
The brief still carries every decision already made, never pointers to where
one might be found, because a cheap implementor cannot recover one the brief
left out (an approach already settled, such as "reuse helper X", is a
decision); but it states the goal and the check, not the lead's theory of the
fix.

Until the Phase 6 writer eval reports (`docs/v2-plan.md`), `AGENTS.md` → Doing
the work decides whether to dispatch at all; this skill only says how.

## The brief, in this order

1. **Goal.** What is wrong or wanted, in one or two sentences. Not the how: leave
   the implementor room to find a better path.
2. **Done check.** A command or artifact that can pass or fail ("`python3
   tests/x.py` exits 0"). "Make it better" is not a check.
3. **Proof wanted.** What to show: the red and green output, a before-and-after
   number, the stored value.
4. **What you already know.** The failing test, the log line, the file and
   function, the decision already made and why. Give the decision, not your
   theory of the cause.
5. **Constraints.** The real ones: "repro first", "no behaviour change outside
   X", "do not touch tests under Y".

Then the mechanics, always:

- **Files in scope**, as repo-relative paths. Anything outside them is reported,
  not edited.
- **Base.** A delegate worktree is cut from the parent's current commit, not the
  default branch (2026-11-21). The lead pushes `<base>` before dispatch, and the
  brief starts with `git fetch origin && git checkout -b <branch> origin/<base>`.
- **Dispatch** is one T3 `delegate_task` (`AGENTS.md` → T3 Code) with
  `isolation: "worktree"`, `role: "implementation"`, and the implementor role's
  model from `models.resolved.json`. The child runs as `build`, so the brief's
  first line is `role: implementor` and its second "Read and follow
  ~/.config/opencode/agents/implementor.md". `plugins/harness-guard.js` enforces
  the role: no T3 tools, web or questions, and an ask (a push) becomes a deny.
- **At most three issues per task.** Past about three, a DeepSeek implementor
  hits its step limit and leaves work uncommitted (2026-11-21). Split the rest.
- **No `git stash`.** The stash is shared by every worktree; commit work in
  progress on the task branch instead.
- **At most two test-running implementors at once** on one machine (2026-11-21:
  twelve concurrent suites exhausted RAM).

## What the implementor returns

It commits on its task branch and stops: it does not push or open the PR, the
lead does, after review.

- The **head SHA** of its branch, and the files it touched.
- The **red and green commands**, each with its **exit code**.
- One of: `done`; `blocked` with the reason; `unreviewed` for a sensitive change
  it may not land; or `needs-answer` with each question and a recommended
  default, when the task hits an intent ambiguity. It never guesses intent.

## What the lead does with it

Rerun the done check at the returned SHA and read `git status` before calling
anything green. A summary is not evidence. Then review by role, as `AGENTS.md`
says, and land it.
