# Global instructions

Repository `AGENTS.md` files are additive; their build/test lines win. Rules a
hook, policy or test enforces are in the table at the end.

## Doing the work

You do the work. Do not dispatch a writer to avoid editing.

**Ordinary change:** do it. A behavior change gets a failing check first. Run it
red, then green, and record the command and exit code.

**Sensitive change:** auth, secrets, credentials, a schema or data migration, or
a public contract: `AGENTS.md`, `agents/*`, `bin/*`, `commands/*`, `policy/*`,
`evals/cases/*`, `skills/*`, `*opencode.json`, `*global.json`, `*.csproj`,
`*.sln`, `*.slnx`, `*Dockerfile*`. A CI workflow is not sensitive. Before editing,
write the outcome, the done-when, and the red check in a few lines. After it,
one independent read-only review (`review-deep`) in a fresh context, which never
shares the writer's reasoning. This review is required, never optional:
- a Claude-written diff is reviewed by a fresh Opus;
- any other writer's diff is reviewed by Claude, never by its own family.

(The person's rule, 2026-11-22: in Phase 2b, Sonnet missed a 🔴 that Opus caught.)
If no such reviewer is available, stop and ask. Leave the
edits uncommitted and report them `unreviewed`. A finding blocks only with
evidence: a failing test, a line-level counterexample, or a broken rule. There is
one re-review, of the fix delta; another round happens only for a new 🔴. A diff
that weakens a rule in this file is a 🔴 for the person to decide.

Green means the commit you name and a tree whose `git status` you have read.
Never delete, skip, weaken, or retarget a test to make a change pass; if an
expectation was wrong, say why. Test cleanup is its own change, and it names the
test that remains or why nothing covers the behavior. A nit that does not break
the done-when is reported, not fixed. Stop and ask before a change with no undo:
a migration, a delete of data, or money.

A broad lookup may go to `explore` (read-only). A second reviewer only when asked,
or after the same check has failed twice.

## Safety

- Stage only the paths you touched, never `git add -A`, never on the default
  branch. A finished change on a thread branch is committed, pushed, and opened
  as a PR without waiting to be asked.
- Reuse the existing helper or rule before adding a parallel one, and say which.
- A denied command or blocked edit is a boundary, not an obstacle: do not retry
  it in another spelling. Take a safer path or stop and ask.
- Undo cost decides: a one-step revert proceeds; shared state and auth need the
  cleanup named first; no undo waits for a person.

## T3 Code

The `t3-code*` tools own the worktree and the link/watch state; `git` and the
`pull_request_*` tools own the branch and the PR. Opening the PR ends a finished
change: push, open, then `link_pull_request` and `watch_pull_request` once. A
delegated child never watches. A merge is the person's click in v2.0.

When a dispatch names a bot and a thread id and that bot's webhook is configured,
run `notify-bot <BOT> <status> "<one-line summary>" <thread-id>` at the end. A delegated
child does not send it, a failure never fails the task, and never print the secret.

## Models and the advisor

Use the session model; a lookup may use a cheaper one. Claude runs in Claude Code,
never through opencode; `review-deep`, `advisor` and `verifier` run on Opus or
Sonnet there.

An advisory consult (`advisor`, read-only, Opus in Claude Code) is required when
one of these triggers fires, at most twice per change:
- a design choice the code cannot settle (public contract, data shape, new module
  or entry point, migration);
- the same check has failed twice;
- you are about to delete, rewrite or retarget a test or check;
- the plan touches more than three source files or 400 changed lines.

It returns risks, a simpler alternative, and missed cases. Record the answer. It
never replaces the review and can add a stop, never remove one.

Record every review, consult and verifier run with `bin/review-log add`.

### Ambiguity

Cheap to reverse and settled by the repo: decide, and state the assumption. Intent
goes to the person, never to a model. Intent means two readings that differ in
user-visible behavior, a public contract, or a data shape. Ask once, with a
recommended default per question, name the search that failed, and keep working
on whatever does not depend on the answer. Running out of consults never changes
the default, which is to ask. A child that cannot ask returns `needs-answer`.

## Memory

Durable memory is `~/.config/opencode/memory/`. Before heavy work, read
`INDEX.md` and open a file only when its blurb matches the task. Read
`learnings/working.md` when it exists; never write it. Never edit
`memory/core/**`, not even through a shell redirect. Append durable discoveries to
`learnings/pending/YYYY-MM-DD.md` (UTC) as `never`/`known`/`derived` lines, each
tagged `harness`/`loop`/`graph`, under the header in `learnings/README.md`.
Agents do not read `pending/`; a person promotes it with `dream --promote`.

## C# / .NET

Before the first C# read or edit, find the `*.sln`/`*.slnx` (repo root, one level
up, or the nearest ancestor), call Roslynk `open_solution`, and load
`roslynk-rules`. It says which Roslynk tool replaces grep, reads and builds. If
there is no solution, say so in one line and read files. Never imply Roslynk
answered when it did not. `get_diagnostics` is a compile check, not a test run.

Load the skill before its work:
- `run-tests` before any .NET test command or judgment of one;
- `platform-detection` before naming the runner;
- `test-anti-patterns` and `assertion-quality` before calling a test weak or
  removing one.

A skill is a procedure; this file and a repository's `AGENTS.md` win over it. A
skill that routes to a sibling we lack: say it is not installed.

## Rules and what enforces them

A rule enters this file only with a named incident or a failing eval.
`bin/lint-config` checks that every enforcer resolves and the 8,000-character cap.

| Rule | Enforcer | Failure it prevents |
| --- | --- | --- |
| No force, delete, mirror or `+refspec` push | policy:git-push-destructive | #16 |
| `git push` asks | policy:git-push | #16 |
| No agent merge in v2.0 | policy:gh-pr-merge, policy:gh-api-merge, policy:gh-api-graphql-merge | — |
| No `git stash pop`, `drop` or `clear`; use a WIP commit | policy:git-stash-drop | 2026-11-21: a delegate popped another worktree's WIP |
| No `rm -rf`, `git reset --hard`, `git clean` | policy:rm-recursive-force, policy:git-reset-hard, policy:git-clean | #16 |
| `memory/core/**` is read-only | policy:no_edit | — |
| Install only from the canonical checkout | test:install_root.py | 2026-11-20: 32 hours on a merged worktree |
| `sync-harness` writes the home only from the canonical checkout | test:sync_canonical.py | same |
| `dream` writes only through the canonical memory link | test:dream_canonical.py | same |
| `dream` stops drafting into a queue unread for 14 days | test:dream_cadence.py | 12 pending files no one read |
| Retired agents leave `~/.claude/agents` | test:agents_prune.py | #41's agents stayed dispatchable |
| No Claude model inside opencode | lint:check_no_claude_in_opencode | Phase 2b |
| Eval comparisons take 3 or more attempts | test:eval_compare.py | single runs ranked gates |
| Every gate leaves a ledger record | test:review_log.py | #41 deleted the ledger |
| A sensitive change gets the review above | judgment | #39 landed unreviewed |
| Red before green | judgment | a fix with no proof it fixed anything |
| Never weaken a test to pass | judgment | ImpossibleBench: agents edit tests to pass |
| Intent goes to the person | judgment | 24 asks in 1,688 sessions (#51) |
| Never `git add -A` | judgment | 2026-11-20 lesson: a pathspec did not stop it |
