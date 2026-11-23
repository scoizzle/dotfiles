# Global instructions

Repository `AGENTS.md` files are additive; their build/test lines win. Enforced
rules are in the table at the end.

## Doing the work

You do the work. Do not dispatch a writer to avoid editing.

**Ordinary change:** do it. A behavior change gets a failing check first: run it
red, then green, and record the command and exit code.

**Sensitive change:** auth, secrets, credentials, a schema or data migration, or
a public contract: `AGENTS.md`, `agents/*`, `bin/*`, `commands/*`, `policy/*`,
`evals/cases/*`, `skills/*`, `*opencode.json`, `*global.json`, `*.csproj`,
`*.sln`, `*.slnx`, `*Dockerfile*`. A CI workflow is not sensitive. Before editing,
write the outcome, done-when and red check in a few lines. After it,
one independent read-only review (`review-deep`, the `reviewer` role) in a fresh
context, never sharing the writer's reasoning. It is required,
and never the writer's family when roles span families; a Claude-written diff
gets a fresh Opus (2026-11-22: Sonnet missed a 🔴). With one family it is a fresh
same-model review, unless `models.resolved.json` says `review_mode: stop`.

No such reviewer: stop and ask, leave the edits
uncommitted, and report them `unreviewed`. A finding blocks only with
evidence: a failing test, a line-level counterexample, or a broken rule. There is
one re-review, of the fix delta; another round only for a new 🔴 or 🟠. A diff
that weakens a rule in this file or on a sensitive path is a 🔴 for the person,
not a finding the reviewer may waive.

Green means the commit you name and a tree whose `git status` you have read.
Never delete, skip, weaken, or retarget a test to make a change pass; if an
expectation was wrong, say why. Test cleanup is its own change, never bundled with the
change it unblocks; it names the surviving test or why nothing covers the
behavior, and never removes a behavior's last test. A flaky test you cannot
root-cause: stop, note it in `memory/learnings/`, and let a person delete it. A nit that does not break
the done-when is reported, not fixed. Stop and ask before a change with no undo:
a migration, a delete, or money.

A second reviewer only when asked or after the same check failed twice.

## Safety

- Stage only the paths you touched, never `git add -A`, never on the default
  branch. A finished change on a thread branch is committed, pushed, and opened
  as a PR without waiting to be asked.
- Keep diffs minimal; reuse an existing helper or rule before adding a parallel
  one, and say which.
- A denied command or blocked edit is a boundary, not an obstacle: never retry
  it in another spelling, tool or script; take a safer path or stop and ask.
- A one-step revert proceeds; shared state and auth name their cleanup first.

## T3 Code

All dispatch is T3 `delegate_task` (`subagent` is denied; without T3 a sensitive
change stops and asks), set up per the `t3-dispatch` skill. Every brief starts
`role: <role>`, which `plugins/harness-guard.js` enforces.

`t3-code*` tools own the worktree and link/watch state, `git` and `gh pr create`
(or `pull_request_*`) the PR. A finished change: push, open, `link_pull_request`, one
`watch_pull_request` (never re-armed; a wake is not a merge),
`unwatch_pull_request` before handback. `t3_worktree_handoff` goes last (it ends
the session). Children never watch.

A dispatch naming a bot, thread id and configured webhook ends with
`notify-bot <BOT> <status> "<one-line summary>" <thread-id>`; not from a child,
a failure never fails the task, never print the secret.

## Models and the advisor

Roles (`models/roles.json`, a profile, `models.local.json`) resolve to models
in `models.resolved.json`. Use your role's model;
a lookup may use `explore`; advisor triggers are the only escalation.

A read-only `advisor` consult is required when a trigger fires, at most twice
per change:
- a design choice the code cannot settle (public contract, data shape, new module
  or entry point, migration);
- the same check has failed twice;
- you are about to delete, rewrite or retarget a test or check.

Record its answer (risks, a simpler alternative, missed cases). It
never replaces the review, can add a stop but never remove one, never answers
intent (`proceed` included), and never authorizes a choice with no undo.

Record every review, consult and verifier run with `bin/review-log add`.

### Ambiguity

Cheap to reverse and settled by the repo: decide and state the assumption.
Intent (two readings differing in user-visible behavior, a public contract or a
data shape) goes to the person, never to a model. Ask once, a
recommended default per question, naming the search that failed; keep working on
what does not depend on the answer. Design that is also intent goes to the
person; a consult may only frame it. Running out of consults never changes the
default: ask. A run that cannot ask stops before the dependent work; a child
returns `needs-answer`.

## Memory

`~/.config/opencode/memory/`: before heavy work read `INDEX.md`, then only the
files whose blurb matches, and `learnings/working.md` (never write it). Never edit
`memory/core/**`, even by shell redirect. Append discoveries to
`learnings/pending/YYYY-MM-DD.md` (UTC), formatted per `learnings/README.md`;
agents never read `pending/`; a person promotes it (`dream --promote`).

## C# / .NET

Load `roslynk-rules` before the first C# read or edit: it opens the solution and
names the Roslynk tool for each grep, read or build. Never
imply Roslynk answered when it did not.

Load the skill before its work:
- `run-tests` before any .NET test command or judgment of one;
- `platform-detection` before naming the runner;
- `test-anti-patterns` and `assertion-quality` before calling a test weak, or
  removing, weakening or retargeting one.

A skill is a procedure; this file and a repository's `AGENTS.md` win over it. A
skill that routes to a sibling we lack: say it is not installed.

## Rules and what enforces them

A rule enters this file only with a named incident or a failing eval.
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
| A sensitive change gets the review above | judgment | #39 landed unreviewed |
| Red before green | judgment | unproven fixes |
| Never weaken a test to pass | judgment | ImpossibleBench: agents edit tests |
| Intent goes to the person | judgment | 24 asks in 1,688 sessions (#51) |
| Never `git add -A` | judgment | 2026-11-20 lesson: a pathspec did not stop it |
| All dispatch via T3 | test:dispatch_t3.py | T3 children run as `build` |
| Role and shell limits in every session | test:guard_plugin.py | heredoc writes passed the globs |
