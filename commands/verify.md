---
description: Ask the read-only reviewer to check the current change
---

Review the current uncommitted change.

Write the review folder as `skills/t3-dispatch` says (status, diff, untracked
files, the test files the diff touched, the base copies of `AGENTS.md` and
`agents/review-deep.md`, and each check you ran with its exit code). A folder
without `check.txt` gives the reviewer a claim instead of a run.

Contract / scope (what "done" means; may be empty): $ARGUMENTS

Send the folder (by its absolute path) and the contract through T3 `delegate_task` to the reviewer, with a brief
whose first line is `role: reviewer`, then "Read and follow ~/.config/opencode/agents/review-deep.md" (the installed copy), `isolation:
"worktree"` and `interactionMode: "plan"` (`agents/build.md`). It is read-only: it
does not edit and does not rebuild. The reviewer is the `reviewer` role (`~/.config/opencode/models.resolved.json`).
`bin/models` keeps it out of the implementor's family while the roles span more
than one; when every role is one family it is a fresh same-model review, and a
`review_mode` of `stop` means stop and ask the person. A diff the lead wrote
itself in a Claude family gets a fresh Opus `review-deep`.

If T3 or the reviewer is not reachable, stop, leave the change uncommitted, and report it
`unreviewed`. If this is not a git repository, say so and send the changed
files instead.

The `*.base.md` files are the base copies of `AGENTS.md` and
`agents/review-deep.md`. If the diff touches either, or `agents/*`, `bin/*`,
`commands/*`, `policy/*`, or `skills/*`, tell the
reviewer to treat the base copies as the governing rules, compare the new wording
against them, and report a check this diff weakens or removes as 🔴 for a person
to decide — not as a finding it may waive. For the gate paths with no base copy,
the diff's removed lines are the base. The review is evidence for that
decision, not the decision.
