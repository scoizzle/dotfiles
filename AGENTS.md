# Global instructions

Repository `AGENTS.md` files are additive. Their build/test command lines win.

## Default workflow

You do the work. Do not dispatch a writer to avoid editing.

Before the first edit, name the kind of change:

- **Ordinary.** Do it. A behavior change gets a failing check first. Run it red, then green. Record the command and the exit code.
- **Sensitive.** Auth, secrets, credentials, a schema or data migration, or a public contract: `AGENTS.md`, `agents/*`, `bin/*`, `commands/*`, `policy/*`, `evals/cases/*`, `skills/*`, `*opencode.json`, `*global.json`, `*.csproj`, `*.sln`, `*.slnx`, `*Dockerfile*`, `memory/core/*`. A CI workflow is not sensitive. Write the outcome, the done-when, and the red check in a few lines before editing. After the change, one independent read-only review (`agents/review-deep.md`); for a sensitive change this review is required, never optional. It must come from a different family than the one that wrote the diff. If no model from a different family is available, stop and ask; skipping the review is not the fallback. A diff that touches these checks is reviewed against their base copies, and a rule it weakens is a 🔴 for a person to decide, not a finding the same reviewer may waive. Stop and ask before a change with no undo: a migration, a delete, or money.

Green means the commit you name and a tree whose `git status` you have read. Never delete, skip, weaken, or retarget a test to make a failing change pass. If a test's expectation was wrong, say so and say why. A nit that does not break the done-when is reported, not fixed.

Test cleanup is its own change: a duplicate of a test that already covers the same assertion (name the test that remains), or a test for behaviour that no longer exists (say why nothing covers it). Never bundle a removal with the change it would unblock, and never remove the last test that covers a behaviour. Bulk-deleting a duplicate suite is allowed when each removal names its survivor. A flaky test you cannot root-cause: stop, write the constraint to `memory/learnings/`, and let a person delete it.

Dispatch only when it earns the tokens:

- A broad lookup (a repo map, a multi-file grep) may go to the explore agent. It is read-only and returns findings and sources. Do not paste the repo into this context.
- One reviewer, required for a sensitive change, and otherwise only when the user asks or after the same check has failed twice. It does not edit and does not rebuild. A second reviewer is not the default.

If dispatch is unavailable, do the work yourself and say so. Do not block an ordinary edit on a missing dispatcher. For a sensitive change, unavailable dispatch is not a reason to skip the review or to review your own diff: stop and ask, leave the finished edits uncommitted, and report them as unreviewed. A child writer cannot ask, so it returns `unreviewed` to its parent.

## Safety

- A finished change on a thread branch is committed, pushed, and opened as a pull
  request without waiting to be asked. Stage only the paths the change touched,
  never `git add -A`, and never on the default branch. `git push` is ask. Force,
  delete, mirror, and `+refspec` pushes are denied, and a merge is a person's
  click.
- Keep diffs minimal and consistent with the surrounding code. Reuse the existing
  symbol, helper, or rule before adding a parallel one, and say which one you reused.
- The explore agent and the review agents are read-only.
- A one-click revert can proceed. Name cleanup before landing shared state or auth. Wait for a person when there is no undo.
- A denied command or a blocked edit is a boundary, not an obstacle. Do not retry it in another spelling, tool or script; take a safer path or stop and ask.

## T3 Code

When the `t3-code*` tools are present, they own the worktree and the link/watch
state. Commits, pushes, and the PR itself stay `git` and `gh pr create`; the
shell is the fallback for both.

- `t3_worktree_status` before work that assumes a branch, or before a handoff;
  `t3_worktree_list` to see refs and checkouts. `t3_worktree_handoff` goes last
  in the turn: it ends the live session, and it fails if this thread already has
  a worktree.
- Opening the PR is how a finished change ends: `git push`, then `gh pr create`.
  `link_pull_request` is the next call, then `watch_pull_request` once, then end
  the turn. Read state with `list_thread_pull_requests`. The watch survives each
  wake, must not be re-armed, and a wake is not a merge decision. Call
  `unwatch_pull_request` before handing the thread back. For a diff too large to
  read in one pass, `write_pull_request_guides`, then `read_pull_request_guide`
  when its run finishes.

A delegated child never watches. A merge is a person's click: `gh pr merge` is
denied here and T3 has no merge action, so do not route around either one.

When a dispatch names a bot and a thread id and that bot's webhook is configured, run
`notify-bot <BOT> <status> "<one-line summary>" <thread-id>` at the end (`~/.local/bin/notify-bot` if it is not on PATH); a delegated child does not send it, a notify failure never fails or extends the task, and never print or debug the secret.

## Model choice

Use the session model. A lookup may use a cheaper model when one is already configured. A sensitive review must use a different model family than the one that wrote the diff. Family means vendor: `claude-agent/*` is one family, `opencode-go/*` and `xai/*` are others. `review-deep` runs on Opus in Claude Code (its opencode copy has no Claude pin), so when the writer is also Claude, dispatch the review on a different-family model, in T3 Code by `delegate_task` with that target. Do not stop to ask about model fallbacks for anything else; the one exception is this review, which stops for a person rather than borrowing the writer's family.

An advisory consult is required when a trigger fires, and is capped at two per change. The advisor triggers are finite and named: before implementing a plan with a design choice the writer cannot settle from the code — a public contract, a data shape, a new module or entry point, or a migration; after the same check has failed twice; before deleting, rewriting, or retargeting a test or a check; and before implementing a plan that will touch more than three source files (including tests and config) or change more than 400 lines (added plus removed, per `git diff --stat`). The consult is read-only, runs on Opus in Claude Code (`agents/advisor.md`), and asks for the risks, a simpler alternative, and the cases the plan misses. Record the answer in the reply. It never replaces the sensitive review, and it is not a tier: an ordinary change that trips no trigger gets no consult.

### Ambiguity, and when to ask

Keep going when the choice is cheap to reverse and the repository settles it; state
the assumption in the reply that first uses it. Ask when the ambiguity is intent and
the repository does not settle it — and ask the person, not a model. Design that is
not intent stays with the Model choice trigger above.

An ambiguity is intent, not design, when two readings would produce different
user-visible behaviour, or a different public contract or a public data shape.
Intent goes to the person every time; when a design trigger is also intent, the
person decides and the required consult still runs but may only frame it.

Put the questions in one ask, each with a recommended default, and keep working on
whatever does not depend on an answer. A question names the search that failed, when
there was one: what was checked, and why it did not settle the point.

A consult never answers the question: its verdict can add a stop, never remove one,
`proceed` never answers a question about intent, and no consult may authorize a
choice with no undo — a migration, a delete, a public contract, money.

Running out of consults or advisors never changes the default, which is to ask. A run
that cannot ask stops before the dependent work. A child returns `needs-answer` to its
parent as a status beside `unreviewed`; the parent takes it to the person.

## Memory

Durable memory is `~/.config/opencode/memory/` (this repo's `memory/`, linked
by `install.cs`).

Before heavy work, read `~/.config/opencode/memory/INDEX.md`, the bookshelf: a
blurb per file. Load a memory file only when its blurb matches the task. Dated
files under `memory/learnings/` are local, so the index names the pattern; when
it matches (a task that could repeat an earlier failure, command, or path), read
the newest `learnings/YYYY-MM-DD.md` files.

Never edit `memory/core/**`: conventions and safety. `opencode.json` denies
`edit` there (edit, write, patch), but a shell command is matched as text, so
this rule is what forbids a redirection into core.

Durable discoveries are appended to `memory/learnings/pending/YYYY-MM-DD.md`
(UTC date) as short constraints (`never`, `known`, `derived`, with a `harness`,
`loop`, or `graph` tag) under the version header in
`memory/learnings/README.md`: who, when in UTC, session or context id, and
source.

`dream` stages its output in `memory/learnings/pending/`, which agents do not
read; a person promotes it with `~/.config/opencode/bin/dream --promote`. Read
`memory/learnings/working.md` first when it exists, and open any dated file its
`source:` line does not name; never write it. Do not rewrite memory mid-task as a
substitute for finishing the work; see `docs/memory-and-dreaming.md`.

## C# / .NET work

Roslynk is configured globally and assumed available. Before the first C# read or
edit, find the solution and open it:

```sh
git rev-parse --show-toplevel      # then look for *.sln / *.slnx at depth <= 2
```

Look in the toplevel, one level up, and in the nearest ancestor that holds one.
Call `open_solution` with the absolute path; every other tool needs its
`solutionId`. Load the `roslynk-rules` skill once per session before the first
C# edit.

Use Roslynk instead of the mechanical alternative:

| Instead of | Use |
| --- | --- |
| grep for a symbol by name | `search_symbols`, `find_definition` |
| reading a whole file to find a member | `get_members`, `get_symbol_body` |
| grep for callers or implementers | `find_references`, `get_callers`, `find_implementations` |
| `dotnet build` to check compile state | `get_diagnostics` |
| hand-editing a rename or signature change | `rename_symbol`, `change_signature` |

Read files only for context Roslynk cannot provide, and for non-C# files. If no
solution exists (file-based apps such as `install.cs`, `.csproj`-only trees) or
`open_solution` fails, say so in one line and use normal file reads. Never imply
Roslynk answered when it did not.

### Skills

Load the skill before the work it covers, not after:

- `run-tests` — before running, quoting, or judging a .NET test command,
  including filter syntax and how to read a failure.
- `platform-detection` — before naming the runner (VSTest, bridged MTP, native
  MTP). A `Microsoft.NET.Test.Sdk` reference, an existing `dotnet test` in CI, or
  a previous successful run is not evidence of the platform.
- `test-anti-patterns` and `assertion-quality` — before calling a test a
  duplicate, weak, or safe to remove, and when a change removes, weakens, or
  retargets a test. Editing test source without removing or weakening an
  assertion does not need them.

A skill is a procedure. This file and a repository's `AGENTS.md` win over it. If a
skill is not loaded in this session, read
`~/.config/opencode/skills/<name>/SKILL.md` (or `~/.claude/skills/<name>/SKILL.md`)
and apply it; if neither is reachable, say so and use the rule in this file. A
skill that routes to a sibling we do not have (`coverage-analysis`,
`test-gap-analysis`, `test-tagging`, `crap-score`) is a missing tool, not a
reason to invent one; say it is not installed.

Read-only agents (`explore` and the review agents) use only the read-only Roslynk tools listed in
the `roslynk-rules` skill, never the ones that write.

`get_diagnostics` is a compile check, not a test run. Tests still go through the
repo's test command, and a repo `AGENTS.md` may name a build command that must
still be run.
