---
name: consult-advisor
description: Required when a trigger fires - a design choice the code cannot settle (public contract, data shape, new module or entry point, migration), the same check failed twice, or you are about to delete, rewrite or retarget a test or check. How to run the read-only advisor consult and what it may and may not decide.
license: MIT
compatibility: opencode
---

# Consult the advisor

`AGENTS.md` makes the consult **required** when one of the three triggers in this
skill's description fires. It is the only model escalation.

## Run it

- Dispatch the `advisor` role per `t3-dispatch`: `role: advisor`, then "Read and
  follow ~/.config/opencode/agents/advisor.md", `isolation: "worktree"`,
  `interactionMode: "plan"`, on the advisor role's model.
- At most **two consults per change**.
- Give it the plan, the facts you already have, and the specific questions; ask
  for the risks, a simpler alternative, and the cases the plan misses.

## What it may and may not do

- It never replaces the required review of a sensitive change.
- It can add a stop, never remove one.
- It never answers intent: a question about what the person wants goes to the
  person, and an advisor `proceed` does not settle it. A design choice that is
  also intent goes to the person; the consult may only frame it.
- It never authorizes a choice with no undo (a migration, a delete, money).
- Running out of consults never changes the default, which is to ask.

## After it answers

- Record its answer in your reply: the risks, the simpler alternative, the
  missed cases, and what you acted on.
- Log it with `bin/review-log add --kind consult`.
