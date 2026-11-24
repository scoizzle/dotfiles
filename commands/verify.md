---
description: Ask the read-only reviewer to check the current change
---

Review the current uncommitted change.

Bundle: !`~/.config/opencode/bin/review-bundle . --show AGENTS.md --show agents/review-deep.md`

The bundle's `06-test-changes-NN.txt` is what the diff did to tests: removed
declarations and assertions, added skips, deleted and moved test files. It is a
heuristic, not a proof: its `none` line names the paths it looked at and the focus
markers it does not check. When the
change ran a check, run the bundle yourself with `--check '<cmd>'` (same `--show`
flags) so `07-checks-NN.txt` holds that command, its exit code, and its output. A
bundle without `07-checks` gives the reviewer a claim instead of a run.

Contract / scope (what "done" means; may be empty): $ARGUMENTS

Send the bundle directory (by its absolute path), the contract, and the recorded
check command and output through T3 `delegate_task` to the reviewer, with a brief
whose first line is `role: reviewer`, then "Read and follow ~/.config/opencode/agents/review-deep.md" (the installed copy), `isolation:
"worktree"` and `interactionMode: "plan"` (`agents/build.md`). It is read-only: it
does not edit and does not rebuild. The reviewer is the `reviewer` role (`~/.config/opencode/models.resolved.json`).
`bin/models` keeps it out of the implementor's family while the roles span more
than one; when every role is one family it is a fresh same-model review, and a
`review_mode` of `stop` means stop and ask the person. A diff the lead wrote
itself in a Claude family gets a fresh Opus `review-deep`.

If T3 or the reviewer is not reachable, stop, leave the change uncommitted, and report it
`unreviewed`. If the bundle command failed because this is not a
git repository, say so and use the changed file list instead.

When the bundle has `04-show-*`, it holds the base copies of `AGENTS.md` and
`agents/review-deep.md`. If the diff touches either, or `agents/*`, `bin/*`,
`commands/*`, `policy/*`, or `skills/*`, tell the
reviewer to treat the base copies as the governing rules, compare the new wording
against them, and report a check this diff weakens or removes as 🔴 for a person
to decide — not as a finding it may waive. For the gate paths with no `04-show-*`
copy, the diff's removed lines are the base. The review is evidence for that
decision, not the decision.
