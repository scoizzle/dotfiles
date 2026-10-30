---
description: Resolve a queue slice into a compact brief without loading queue docs into the main context
agent: explore
subagent: true
---

Resolve slice `$ARGUMENTS` from this repository's queue and return a brief of at most 40 lines. Do not edit anything.

1. Read the repository's `AGENTS.md` admission section to find the queue file, and read its build and test bullets for the commands. If it does not name a queue file, say so and stop.
2. Read the queue's CURRENT line. If it is missing, say so and stop. If it is `(none)`, say `(none)` and apply the repository's admission rule for that state (for example, only a suite named in its parked queue); do not guess a suite it does not name.
3. Read only these parts: the CURRENT line, the `Next` row for `$ARGUMENTS`, the `In flight` row for the same slice, and that slice's task file. Do not read unrelated rows, other task files, or long process documents.
4. The `Next` row's Depends/hold cell wins over the task file and over any local-agent notes when they disagree. Carry any narrowing or blocker it states into the brief.
5. Return exactly: slice and row number with CURRENT in one line; done-when as testable behaviours from the winning source; the repository's build and changed-area test commands; files likely touched; blockers (dependencies, draft PRs, open decisions); and the sources you read.

If the slice is not in `Next`, say so and list the nearest matching row. Do not guess.
