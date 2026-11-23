# Rules and what enforces them

Moved out of `AGENTS.md` (the person, 2026-11-23): the model does not need the
table to follow the rules. Policy rows are enforced by `plugins/harness-guard.js`
and the opencode rules, whose denials explain themselves; test rows by CI; and
judgment rows repeat `AGENTS.md`'s own prose. Lint reads it here.

## Rules and what enforces them

A rule enters `AGENTS.md` and this table only with a named incident or a failing eval.
`bin/lint-config` checks every enforcer resolves, and the 8,000-character cap.

| Rule | Enforcer | Failure it prevents |
| --- | --- | --- |
| No force, delete, mirror or `+refspec` push | policy:git-push-destructive | #16 |
| `git push` asks | policy:git-push | #16 |
| No agent merge in v2.0 | policy:gh-pr-merge, policy:gh-api-merge, policy:gh-api-graphql-merge | — |
| No `git stash pop`, `drop`, `clear`; use a WIP commit | policy:git-stash-drop | a delegate popped another worktree's WIP |
| No `rm -rf`, `reset --hard`, `git clean` | policy:rm-recursive-force, policy:git-reset-hard, policy:git-clean | #16 |
| `memory/core/**` is read-only | policy:no_edit | — |
| Install only from the canonical checkout | test:install_root.py | 32 hours on a merged worktree |
| `dream` writes only through the canonical memory link | test:dream_canonical.py | same |
| `dream` stops drafting into a queue unread for 14 days | test:dream_cadence.py | 12 pending files no one read |
| Eval comparisons take 3 or more attempts | test:eval_compare.py | single runs ranked gates |
| Every gate leaves a record, one file each | judgment, test:review_log.py | #41 deleted the ledger |
| Cross-family review when roles span families | test:models.py | friends' profiles |
| A sensitive change gets the review in `AGENTS.md` | judgment | #39 landed unreviewed |
| Red before green | judgment | unproven fixes |
| Never weaken a test to pass | judgment | ImpossibleBench: agents edit tests |
| Intent goes to the person | judgment | 24 asks in 1,688 sessions (#51) |
| Never `git add -A` | judgment | 2026-11-20 lesson: a pathspec did not stop it |
| All dispatch via T3 | test:dispatch_t3.py | T3 children run as `build` |
| Role and shell limits in every session | test:guard_plugin.py | heredoc writes passed the globs |
