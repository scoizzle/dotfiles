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
bundle without `07-checks` gives the reviewer a claim instead of a run. `--check`
refuses anything `harness-guard` would deny or ask about, because it cannot prompt.

Contract / scope (what "done" means; may be empty): $ARGUMENTS

Send the bundle directory, the contract, and the recorded check command and output
to the `review-deep` reviewer (`agents/review-deep.md`). It is read-only: it does
not edit and does not rebuild. Pick the reviewer by the writer's family, never
by which harness is running this command:
- A non-Claude writer (opencode's default is `opencode-go/*`) is reviewed by
  Claude. Run `claude -p --agent review-deep` with the bundle, or in T3 use
  `delegate_task` with `providerInstanceId: claudeAgent`. opencode's own
  `review-deep` copy runs on the writer's family and must not be used here.
- A Claude writer is reviewed by a fresh Opus `review-deep` in Claude Code.

If neither is reachable, stop, leave the change uncommitted, and report it
`unreviewed`. If the bundle command failed because this is not a
git repository, say so and use the changed file list instead.

When the bundle has `04-show-*`, it holds the base copies of `AGENTS.md` and
`agents/review-deep.md`. If the diff touches either, or `bin/review-bundle`,
`commands/verify.md`, `policy/*`, `evals/cases/*`, or `skills/*`, tell the
reviewer to treat the base copies as the governing rules, compare the new wording
against them, and report a check this diff weakens or removes as 🔴 for a person
to decide — not as a finding it may waive. For the gate paths with no `04-show-*`
copy, the diff's removed lines are the base. The review is evidence for that
decision, not the decision.
