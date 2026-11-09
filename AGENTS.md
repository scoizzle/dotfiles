# Global instructions

Repository `AGENTS.md` files are additive. Their build/test command lines win.

## Default workflow

The default `build` agent is the orchestrator primary in opencode: it runs this
workflow by dispatching units, not by editing. `implementor` is the agent that
edits. Subagents follow their own role prompt.

Before the first edit or subagent call, state the tier on its own line:
`Tier: T0`, `Tier: T1`, or `Tier: T2`. A short read-only look at the repo is
allowed; never state a tentative tier. Then state the agents and the reason.
Never ask the user to choose a tier or model.

### Classify

Run `~/.config/opencode/bin/review-bundle <repo> --classify --paths <planned files>`
before the first edit, and again with no `--paths` before review. It prints a tier
floor and the reasons. You may raise the tier, never lower it; a T1 plan whose diff
later floors at T2 is re-run as T2.

- **T0:** no behaviour change, or one obvious mechanical edit; no public
  contract, data, security, or CI. Dispatch one deepseek unit; the unit runs the
  check.
- **T1:** one area, <=3 source files, <=400 lines, no public contract/data/
  security/CI, test oracle exists. Write a <=10-line brief with done-when and the
  red test; dispatch one deepseek unit; the unit runs the changed-area tests;
  dispatch the `review-light` band; fix once.
- **T2:** anything else, or "design/architecture/migration/security/data/schema/
  enum/public API/be careful", or unsure. Write a plan with done-when; dispatch the
  `plan-review-deep` band; fix plan findings (cap 2); dispatch the `implement-deep`
  band; dispatch a check unit for the checks; dispatch the `review-deep` and
  `second-opinion` bands in parallel with `ROLE: review unit`; triage; fix (cap 2);
  dispatch a check unit for the full suite. Pins and the three advisor moments are
  in Model routing.

### Evidence

- **Test-first:** write the red test, run it red, record the command and output.
- **One check owner:** the parent dispatches the changed-area tests and the full
  suite to a check unit (`ROLE: check unit`) and records the output in the PROOF;
  a repo `AGENTS.md` supplies the command lines. Never use a review agent as a
  check runner. Reviewers never rebuild.
- **Reviewers** are dispatched with `ROLE: review unit`; they read the
  `review-bundle` directory and the recorded check output.
  `~/.config/opencode/bin/review-bundle` is not on PATH; call it by absolute path.
  Outside git, pass the changed file list.
- **Baseline:** before fixing reviewer findings, run
  `~/.config/opencode/bin/review-bundle <repo> --baseline` and keep
  `05-baseline.json`. After the fix, run it again and pass both bundle
  directories to the re-reviewer.
- **Triage:** fix every 🔴 and every 🟠 that has a repro or violates the
  done-when. An unproven 🟠 gets a probe by a check unit (or the implementor) or is
  downgraded and reported; it is not fixed as confirmed.
- **Handback:** a reproducible bug in hand is work, not a note: write its red
  test before the stream ends. A fix inside T1's limits stays T1 and the stream
  continues; a larger one is T2 on its bands. Only a person's ruling defers,
  recorded where the work is, dated, naming the decision it addresses. A "not a
  patch" verdict names the estimated diff and the decision it violates.
- **Green is the branch head.** A recorded suite result names the commit it ran
  on and a tree whose `git status` you have read. A green run in a child tree, a
  copy, or over uninspected untracked files proves nothing.
- **Never** delete, skip, or weaken a test. If a test's expectation was wrong,
  say so and say why.
- The **second-opinion prompt** contains the bundle directory, the plan/done-when,
  and the recorded check output, never the `review-deep` report.

### Proof of work

Every **dispatched unit that changes or checks the tree** returns a `PROOF`
block, never a prose summary. A read-only search unit returns its findings and
sources; a review unit returns its findings and the bundle path; a check unit
(`verifier`) returns its Coverage block and the checks it ran.

- `commands:` every command run, verbatim, with its exit code.
- `diff:` `git diff --stat` and the key hunks, or the commit sha when the unit
  could commit.
- `checks:` the tail of the red and green test or build output, with the command
  that produced it, or `none` when the unit has no test oracle.
- `not done:` work the brief named that was skipped, and why.
- `risks:` what could still be wrong, and what would prove it.

A dispatch reply missing any line is rejected and re-dispatched with the gap
named; the orchestrator does not fill the gap itself. "All tests pass" without
the command and its output tail is not proof.

### Dispatch tiers

The orchestrator picks one implementation tier per unit and names it in the
scope:

| Tier | Pin | Use it for |
| --- | --- | --- |
| `deepseek` | `opencode-go/deepseek-v4.1-flash#high` | volume, T0/T1, a named test oracle |
| `sonnet` | `claude-agent/sonnet#medium` | T2 after plan lock, cross-cutting work, no cheap oracle |

### Safety

- Reviewers are read-only; never give them shell or edit.
- Do not stage, commit, or push unless asked (the orchestrator's checkpoint and integrate units may commit locally, never push, as part of a requested change). `git push` is `ask` in
  `opencode.json`; force, delete, mirror, and `+refspec` pushes are denied. Never
  run an unattended session with `--auto`: it approves every `ask`.
- Keep diffs minimal and consistent with the surrounding code.
- Route broad read-only lookups through `explore`: spawn the subagent when the
  agent has one, otherwise dispatch an explore unit on the explore band. The brief
  caps the return at findings + sources. An agent that can do neither reports the
  gap instead of scanning. Do not read the whole repo in the main context.

### Undo

Classify a ship-or-ask step by undo cost. A one-click revert (docs, tests, an
isolated change) can proceed. Work that needs cleanup (shared state, auth) gets
named before it lands. Work with no undo (migrations, deletes, money) waits for
a person.

On a fix round, return the failed unit and a fence around the files in scope.
The same failure twice is an escalation; the remaining fix budget stays unspent.

### Ledger

After the user answers the findings, run
`~/.config/opencode/bin/review-log` with tier, models, counts, acted/dismissed.
If the user has not answered, write the line as `pending`.

### Manual overrides

`/verify` and `/second-opinion` are manual escape hatches; `verifier` is a
manual shell-based deep check, not the default review path.

### Orchestrator primary

In opencode, the top-level `build` agent is the orchestrator (`agents/build.md`,
linked as `.opencode/agents/build.md`). Both the repo link and the installed
`~/.config/opencode/agents/build.md` resolve to that one file, so either load path
is the same prompt; `opencode debug agents` in the repo shows the orchestrator
`system` on `build`.
It plans, scopes, dispatches every unit through T3 `delegate_task` with
`isolation: "worktree"`, and accepts only a verified `PROOF`. It never edits files
or runs mutating shell itself. A delegated unit follows its `ROLE:` line:
implementor, review, check, checkpoint, or integrate (the last two run shared and
commit locally, never push). `implementor` is the agent for direct work in plain
opencode.

The no-hands rule is the agent prompt, not a T3 permission: T3 session rules
override agent deny rules. Run the orchestrator in `auto` or `full-access` so
units can edit; `approval-required` stalls them at the first write or command, and
the orchestrator cannot approve it.

`execute` is allowed in `agents/build.md` only because T3 `delegate_task` is
reached through it. The `EXECUTE ALLOWLIST: delegate_task` line is the contract,
and `bin/lint-config` fails if it drifts. The nested-tool surface inside `execute`
is not covered by the agent denies; the allowlist and the human gate are the
mitigation. Worker agents (including `implementor`) deny `execute`. The direct-edit
smoke test runs as `implementor`; the orchestrator path is exercised by the T3
trial, not by `opencode run`.

`plan` interaction mode is a read-only planning phase, not this role: a plan-mode
parent cannot spawn a writable child (`interaction_mode_escalation_denied`). Use
it to explore, then switch the thread to `build` to dispatch.

### Without T3

The T3 tools are the only dispatch channel, so a session without them degrades
instead of improvising:

- Writable units cannot run: the orchestrator does not edit, so the work is
  reported blocked. Do not use a native subagent for it; writer agents share the
  checkout.
- Read-only reviewers may fall back to the harness's own reviewer. The band's pin
  does not apply; record the run as degraded.
- Pinned bands: do not substitute the session model for a band's pin. A T2
  sign-off that needs the advisor and `second-opinion` does not complete without
  them; say so and stop.

## Model routing

Every delegated job runs on its band's pin, not the session's model. The pin
belongs to T3 (the `t3-code` tools), not to a harness.

| Band | Work | providerInstanceId | model | options |
| --- | --- | --- | --- | --- |
| explore | repo maps and multi-file grep | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=low` |
| review-light | T1 diff review | `opencode` | `claude-agent/haiku` | none |
| build (orchestrator) | plan, scope, dispatch, accept; no hands-on work | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=high` |
| implementor, plan, general | implement one unit; plan/general helpers | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=high` |
| second-opinion | independent T2 second look | `opencode` | `opencode-go/muse-spark-1.3-contributor` | `variant=high` |
| implement-deep | T2 implementation after plan-lock | `opencode` | `claude-agent/sonnet` | `variant=medium` |
| verifier | manual build, test and contract check | `opencode` | `claude-agent/sonnet` | `variant=high` |
| plan-review-deep, review-deep | advisor: plan-lock, same error twice, T2 sign-off | `opencode` | `claude-agent/sonnet` | `variant=high` |
| review-critical | security, auth, schema/data migration or public-contract T2 sign-off; review-deep's prompt on the Opus pin | `opencode` | `claude-agent/opus` | `variant=high` |

- Call `orchestrator_capabilities` once per thread before the first delegation,
  and again only after an error or a provider the user names. Pass the pin as
  `target: { providerInstanceId, model, options: [{ id, value }] }`.
- Delegate through T3 even when the target matches the session's provider, so
  one table holds in opencode, Claude Code and Grok Build. Use a native subagent
  only when the T3 tools are absent (explore, and reviewers as below); say in the
  reply that the pin did not apply.
- The advisor and implement bands are never silently downgraded. If T3 is
  absent, say so instead of substituting the session model.
- A change is critical when `review-bundle --classify` reports a sensitive-path
  reason and the change is security, data, or a public contract (not a CI-only
  change), or it touches auth or a schema/data migration. The orchestrator
  records the trigger in the dispatch.
- Reviewers (`review-light`, `review-deep`, `plan-review-deep`, `review-critical`,
  `second-opinion`) run as T3 children with `isolation: "worktree"`, `role: "review"` and the
  review-bundle path in the task. T3 cannot make a child read-only, but a
  worktree child's edits never reach your checkout; confirm `git status` is
  unchanged afterwards. With no T3, use the harness's own read-only reviewer
  (`agents/*.md`, `~/.claude/agents`) and say the pin did not apply.
  `review-critical` uses `review-deep`'s prompt on the Opus pin, so no
  `agents/review-critical.md` exists and, without T3, a critical review does not
  complete rather than silently downgrading.
- `isolation: "worktree"` also for any child that needs its own checkout or will
  open a PR; `shared` only for research. `mode: "wait"` only when this turn needs
  the result (a gate does; a background job does not). `role` names the band's
  job: `research`, `review`, `implementation`, `test`, `design` or `general`.
- Replace a running child with `task_cancel`, then a new `delegate_task`; never
  poll `task_status`.
- The advisor pin is spent at three moments only: (1) T2 plan lock before the
  plan is fixed; (2) the same error or failing assertion twice in a row, passing
  both attempts; (3) T2 sign-off, with `second-opinion` in parallel. A T1 retry
  stays on the builder band. At sign-off, cap dispatches: one `review-deep` and
  one `second-opinion` in parallel, then one re-review after a fix. On a critical
  T2, `review-critical` replaces `review-deep` at sign-off, so it stays two
  parallel dispatches (`review-critical` + `second-opinion`); the post-fix
  re-review uses the same pin. A third is a human escalation; do not cap
  reviewer steps, only dispatches.
- `agents/*.md` are the native fallback, not the routing source. Pins must name
  an enabled instance and an allowlisted model in `policy/providers.json`.
  `grok-4.7` is retired as of 2026-11-09 and no band pins it. Sonnet 5.5
  (`claude-agent/sonnet`) is the default review and verifier pin; Opus 5.5
  (`claude-agent/opus`) is the critical-review escalation. `grok-4.5` stays
  unlisted.
- Claude quota has headroom (2026-11-04): the advisor joins `implement-deep` on
  Claude.

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

Durable discoveries go to `memory/learnings/` as short constraints (`never`,
`known`, `derived`, with a `harness`, `loop`, or `graph` tag) under the version
header in `memory/learnings/README.md`: who, when in UTC, session or context
id, and source.

`dream` stages its output in `memory/learnings/pending/`, which agents do not
read. A person promotes it with `~/.config/opencode/bin/dream --promote`.
Read `memory/learnings/working.md` first when it exists, and open any dated file
its `source:` line does not name; never write it, since promote generates it.

Do not rewrite memory mid-task as a substitute for finishing the work.
Curriculum updates are the out-of-band dream pass,
`~/.config/opencode/bin/dream`. See `docs/memory-and-dreaming.md`.

## C# / .NET work

Roslynk is configured globally and is assumed available. This rule does not
depend on a repository naming it.

Before the first C# read or edit, find the solution and open it:

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

Read files only for context Roslynk cannot provide, and for non-C# files.

If no solution exists (file-based apps such as `install.cs`, `.csproj`-only
trees), say so in one line and use normal file reads. If `open_solution` fails,
say so in one line and fall back. Never imply Roslynk answered when it did not.

Read-only agents (the four reviewer agent files and `explore`) use only the read-only Roslynk tools listed in
the `roslynk-rules` skill, never the ones that write.

`get_diagnostics` is a compile check, not a test run. Tests still go through the
repo's test command, and a repo `AGENTS.md` may name a build command that must
still be run.
