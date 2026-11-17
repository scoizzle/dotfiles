---
description: Ask the read-only reviewer to check the current change
---

Review the current uncommitted change.

Bundle: !`~/.config/opencode/bin/review-bundle . --show AGENTS.md --show agents/review-deep.md`

Contract / scope (what "done" means; may be empty): $ARGUMENTS

Send the bundle directory, the contract, and the recorded check command and output
to the `review-deep` reviewer (`agents/review-deep.md`). It is read-only: it does
not edit and does not rebuild. If the bundle command failed because this is not a
git repository, say so and use the changed file list instead.

When the bundle has `04-show-*`, it holds the base copies of `AGENTS.md` and
`agents/review-deep.md`. If the diff touches either, or `bin/review-bundle`,
`commands/verify.md`, `policy/*`, `evals/cases/*`, or `skills/*`, tell the
reviewer to treat the base copies as the governing rules, compare the new wording
against them, and report a check this diff weakens or removes as 🔴 for a person
to decide — not as a finding it may waive. For the gate paths with no `04-show-*`
copy, the diff's removed lines are the base. The review is evidence for that
decision, not the decision.
