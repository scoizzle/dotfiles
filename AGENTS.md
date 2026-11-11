# Global instructions

Repository `AGENTS.md` files are additive. Their build/test command lines win.

## Default workflow

The default `build` agent is the orchestrator primary in opencode: it dispatches
units, not edits. `implementor` is the agent that edits.

Before the first edit or subagent call, state the tier on its own line:
`Tier: T0`, `Tier: T1`, or `Tier: T2`. A short read-only look (an explore unit) is
allowed first; never state a tentative tier. Then state the agents and the reason.
Never ask the user to choose a tier or model.

### Classify

Classify confirms; it does not gate dispatch. State the tier from the planned
paths and the rules below. The first editing unit runs
`~/.config/opencode/bin/review-bundle <repo> --classify --paths <FILES>` before its
first edit and stops without editing only when the floor is T2 and the stated tier
is T0 or T1 (a T1 floor allows T0 or T1); the orchestrator then re-runs at T2,
restarting from plan lock. Before review, the integrate unit classifies the
integrated range (`--base <preSha>`) and returns the floor and reasons. If that
floor is above the stated tier, continue at the floor from its review step (a T2
gets `plan-review-deep` on the integrated diff, then the sign-off bands). You may
raise the tier, never lower it.
`deepseek` is the implementor row and `sonnet` the implement-deep row of Model
routing. Tier is risk, not implementer: a T2 is implemented on `deepseek` by
default, and `implement-deep` (sonnet) is used only on the three triggers in the
T2 bullet below.

- **T0:** no behaviour change, or one obvious mechanical edit; no public
  contract, data, security, or CI. Sequence: implementor -> integrate.
  T0: no review dispatch. An audit request is an explore unit, or T1
  `review-light` when a verdict on a diff is wanted.
- **T1:** one area, <=3 source files, <=400 lines, no public contract/data/
  security/CI, test oracle exists. Write a <=10-line brief with done-when and the
  red test. Sequence: implementor -> integrate -> `review-light` -> fix once
  (implementor -> integrate) -> close-out.
- **T2:** anything else, or "design/architecture/migration/security/data/schema/
  enum/public API/be careful", or unsure. Write a plan with done-when. Sequence:
  plan -> `plan-review-deep` (fix cap 2) -> implementor (`deepseek`) -> integrate ->
  `review-deep` (or `review-critical`) + `second-opinion` in parallel -> triage ->
  fix (cap 2, also on `deepseek`) -> integrate -> one re-review dispatch on the
  `review-deep` (`review-critical`) pin with both bundles, also checking the
  acted-on `second-opinion` findings -> close-out. Pins and the three advisor
  moments are in Model routing.
  `implement-deep` (sonnet) replaces the `deepseek` implementor only on these
  triggers, each quoted in the dispatch's TIER clause:
  (a) the last `plan-review-deep` round's verdict ends with
  `implementer: implement-deep — <code>: <plan step id>`, with `<code>` one of
  `coupled-invariants`, `no-oracle`, `security-logic`; a missing or malformed
  line means `deepseek`;
  (b) ladder: a `deepseek` unit returned FAIL on a done-when item or a red suite
  with PROOF (not a classify stop, scope-gap report or blocked unit); the retry of
  that item goes to `implement-deep`, quoting the failing PROOF line; the same
  item failing again is advisor moment 2, then the human;
  (c) critical T2, decided at plan lock: a `deepseek` check unit runs
  `review-bundle <repo> --classify --paths <planned FILES>` and criticality comes
  from its reason lines (definition in Model routing); the integrate unit's
  reclassify may only raise it.
- **Close-out:** the stream ends with the tree record. If the last unit is a shared
  one, its PROOF is the close-out and its brief includes the `review-log` run.
  Otherwise one check unit runs `git -C <session checkout path> status --short`
  (the brief names the path; a check unit's own worktree is not the checkout) to
  confirm every read-only unit left it unchanged. Whenever any review ran, the
  close-out runs `review-log` (`pending` if the user has not answered). A dirty
  close-out fails the stream: report the paths, never checkpoint them. Checkpoint
  and integrate units record `git status --short` before acting.

### Evidence

- **Test-first:** write the red test, run it red, record the command and output.
- **One check owner per tree:** the parent names the checks (a repo `AGENTS.md`
  supplies the command lines); the unit that produced the tree runs them. The
  editing unit runs the changed-area tests red then green in its worktree; the
  integrate unit runs the full suite at the integrated head, and its PROOF is the
  branch-head record. A separate check unit (`ROLE: check unit`) runs only to
  probe an unproven finding, for the close-out, or when the user asks. Never use a
  review agent as a check runner. Reviewers never rebuild.
- **Reviewers** are dispatched with `ROLE: review unit`; they read the
  `review-bundle` directory and the recorded check output. `review-bundle` is not
  on PATH; call `~/.config/opencode/bin/review-bundle` by absolute path. Outside
  git, pass the changed file list.
- **Baseline:** the integrate unit takes `review-bundle --baseline --base <preSha>`
  and keeps `05-baseline.json`; after the fix it runs again and both bundle
  directories go to the re-reviewer.
- **Triage:** fix every 🔴 and every 🟠 that has a repro or violates the
  done-when. An unproven 🟠 gets a probe by a check unit (or the implementor) or is
  downgraded and reported; it is not fixed as confirmed.
- **Handback:** a reproducible bug in hand is work, not a note: write its red
  test before the stream ends. A fix inside T1's limits stays T1; a larger one is
  T2. Only a person's ruling defers, recorded and dated, naming the decision it
  addresses. A "not a patch" verdict names the estimated diff and the decision.
- **Green is the branch head.** A recorded suite result names the commit it ran
  on and a tree whose `git status` you have read. A green run in a child tree, a
  copy, or over uninspected untracked files proves nothing.
- **Never** delete, skip, or weaken a test. If a test's expectation was wrong,
  say so and say why.
- The **second-opinion prompt** contains the bundle directory, the plan/done-when,
  and the recorded check output, never the `review-deep` report.

### Proof of work

Every unit that changes or checks the tree returns a `PROOF` block, never a prose
summary. A read-only search unit returns findings and sources; a review unit
returns findings and the bundle path; a check unit returns its Coverage block and
the checks it ran.

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

### Safety

- Reviewers are read-only: never put an edit or a mutating command in their brief;
  plan mode does not remove shell.
- Do not stage, commit, or push unless asked (checkpoint and integrate units may
  commit locally, never push). `git push` is `ask` in `opencode.json`; force,
  delete, mirror, and `+refspec` pushes are denied. Never run an unattended
  session with `--auto`: it approves every `ask`.
- Keep diffs minimal and consistent with the surrounding code.
- Route broad read-only lookups through `explore`: the subagent when the agent
  has one, otherwise an explore unit. The brief caps the return at findings +
  sources. An agent that can do neither reports the gap instead of scanning. Do not
  read the whole repo in the main context.

### Undo

A one-click revert (docs, tests, an isolated change) can proceed. Work that needs
cleanup (shared state, auth) gets named before it lands. Work with no undo
(migrations, deletes, money) waits for a person. On a fix round, return the failed
unit and a fence around the files in scope. The same failure twice is an
escalation; the remaining fix budget stays unspent.

### Pull requests

- Never poll for PR state: no `gh pr checks --watch`, no `gh pr view` in a loop, no
  `sleep` between checks.
- In T3 Code, link each PR you create, take over, or are asked to push as your next
  call (`link_pull_request`), and every layer of a stack in one call
  (`link_pull_requests`). Skip PRs you only read or review.
- Call `watch_pull_request` when asked to monitor or babysit a PR, or when work you
  were asked for, such as a merge, still waits on checks or reviews. It wakes the
  thread on failed checks, passed required checks, new comments or reviews, or a
  conflict. End the turn after the call.
- A wake is not a merge decision: check readiness yourself. The watch survives each
  wake, so a wake is not a reason to call it again, and before handback call
  `unwatch_pull_request` on any PR you watched. A delegated child never watches,
  even when a brief says to babysit.
- Without T3, one `gh pr view` or `gh pr checks` is fine; a wait still does not
  belong in a shell loop, so report the PR and stop.

### Ledger

After the user answers the findings, run `~/.config/opencode/bin/review-log` with
tier, models, counts, acted/dismissed; `pending` if not yet answered.

### Manual overrides

`/verify` and `/second-opinion` are manual escape hatches; `verifier` is a manual
shell-based deep check, not the default review path.

### Orchestrator primary

In opencode, the top-level `build` agent is the orchestrator; `agents/build.md`
is its one prompt (roles, dispatch template, checkpoint/integrate, acceptance). It
never edits; every unit goes through T3 `delegate_task`. Units: implementor,
plan, review, explore, check, checkpoint, integrate (the last two run shared, commit
locally, never push). `implementor` is the agent for direct work in plain opencode.
The no-hands rule is the prompt, not a T3 permission: run the orchestrator in
`auto` or `full-access`. `execute` is allowed only to reach `delegate_task`;
`bin/lint-config` enforces the `EXECUTE ALLOWLIST` line. The nested-tool surface
inside `execute` is not covered by the agent denies; the allowlist and the human
gate are the mitigation. The direct-edit smoke test runs as `implementor`; the T3
trial covers the orchestrator path. `opencode debug agents` in the repo shows the
orchestrator `system` on `build`.

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
  them; say so and stop. A degraded `second-opinion` is advisory and does not
  satisfy T2 sign-off.
- A pinned band that is unavailable or fails on quota (`usage_limit`) is blocked
  the same way: report it, do not substitute. Only the user picks a fallback.

## Model routing

Every delegated job runs on its band's pin, not the session's model. The pin
belongs to T3 (the `t3-code` tools), not to a harness.

| Band | Work | providerInstanceId | model | options |
| --- | --- | --- | --- | --- |
| explore | repo maps and multi-file grep | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=low` |
| review-light | T1 diff review | `opencode` | `claude-agent/haiku` | none |
| build (orchestrator) | plan, scope, dispatch, accept; no hands-on work | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=high` |
| implementor, plan, general | implement one unit (T0, T1 and T2 by default); plan units and general helpers | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=high` |
| second-opinion | independent T2 second look | `opencode` | `opencode-go/muse-spark-1.3-contributor` | `variant=high` |
| implement-deep | T2 implementation only on the three triggers in Classify (plan-review-deep line, failed-item retry, critical T2) | `opencode` | `claude-agent/sonnet` | `variant=medium` |
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
- Fixed bands: check, checkpoint, integrate, explore and plan units always run on
  their routing-row pins; there is no argued deviation. Every `delegate_task`
  passes an explicit `target` equal to the routing row for that role or band.
- Concurrency: before each `delegate_task`, count your own dispatches on
  `claude-agent` pins that have not yet notified completion; at most 2 at a time.
  Read-only fan-out goes to explore. The sign-off pair (`review-deep` on sonnet
  plus `second-opinion` on muse) complies. Never poll.
- A change is critical when `review-bundle --classify` reports a sensitive-path
  reason and the change is security, data, or a public contract (not a CI-only
  change), or it touches auth or a schema/data migration. The orchestrator
  records the trigger in the dispatch.
- Read-only units (reviewers `review-light`, `review-deep`, `plan-review-deep`,
  `review-critical`, `second-opinion`, and explore) run as T3 children with
  `isolation: "worktree"`, `interactionMode: "plan"`, and `role: "review"` (explore:
  `"research"`). Check, implementor, checkpoint and integrate units stay in default
  mode, since tests write build output. Plan mode is a harness instruction, not a
  tool fence (probe 2026-11-10: the child obeyed it over a brief asking for a
  write, and shell still ran), so the stream's close-out still checks the tree.
  T3 children never load `agents/<band>.md`; the brief tells them to read it (the
  `PROMPT:` line in `agents/build.md`). With no T3, use the harness's own read-only
  reviewer (`agents/*.md`, `~/.claude/agents`) and say the pin did not apply.
  `review-critical` uses `review-deep`'s prompt on the Opus pin, so no
  `agents/review-critical.md` exists and, without T3, a critical review does not
  complete rather than silently downgrading.
- `isolation: "worktree"` for every unit except checkpoint and integrate, which run
  `shared`; research included. `mode: "wait"` only when this turn needs
  the result (a gate does; a background job does not). `role` names the band's
  job: `research`, `review`, `implementation`, `test`, `design` or `general`.
- Replace a running child with `task_cancel`, then a new `delegate_task`; never
  poll `task_status`.
- The advisor pin is spent at three moments only: (1) T2 plan lock before the
  plan is fixed; (2) the same error or failing assertion twice in a row, passing
  both attempts; (3) T2 sign-off, with `second-opinion` in parallel. A T1 retry
  stays on the builder band. At sign-off: one `review-deep` (`review-critical` on
  a critical T2) and one `second-opinion` in parallel, then still one re-review
  dispatch after a fix, on the `review-deep` (`review-critical`) pin, which also
  checks the acted-on `second-opinion` findings. A third is a human escalation;
  cap dispatches, not reviewer steps.
- `agents/*.md` are the native fallback, not the routing source. Pins must name
  an enabled instance and an allowlisted model in `policy/providers.json`.
  `grok-4.7` is retired as of 2026-11-09 and no band pins it; `grok-4.5` stays
  unlisted. Sonnet 5.5 is the default T2 review pin; Opus 5.5 is the
  critical-review escalation. The verifier is manual only (`/verify`).
- Native fallback map (`policy/permissions.json` `readonly_agents.models`, checked
  by `bin/lint-config`): `review-light`=`haiku`, `review-deep`=`sonnet`,
  `plan-review-deep`=`sonnet`, `second-opinion`=`sonnet`, `explore`=`haiku`.
  `second-opinion` on sonnet and `explore` on haiku are degraded fallbacks: the
  pin did not apply. A degraded `second-opinion` is advisory and does not satisfy
  T2 sign-off (see Without T3).

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

Read-only agents (the four reviewer agent files and `explore`) use only the read-only Roslynk tools listed in
the `roslynk-rules` skill, never the ones that write.

`get_diagnostics` is a compile check, not a test run. Tests still go through the
repo's test command, and a repo `AGENTS.md` may name a build command that must
still be run.
