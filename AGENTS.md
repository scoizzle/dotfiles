# Global instructions

Repository `AGENTS.md` files are additive. Their build/test command lines win.

## Default workflow

The default `build` agent runs this workflow for every request. Subagents follow
their own role prompt.

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
  contract, data, security, or CI. Do it; run the check.
- **T1:** one area, <=3 source files, <=400 lines, no public contract/data/
  security/CI, test oracle exists. Plan in <=10 lines with done-when and the red
  test; self-check the plan; implement; run the changed-area tests; delegate the
  `review-light` band; fix once.
- **T2:** anything else, or "design/architecture/migration/security/data/schema/
  enum/public API/be careful", or unsure. Write a plan with done-when; delegate the
  `plan-review-deep` band; fix plan findings (cap 2); implement with the
  `implement-deep` band; run checks; delegate the `review-deep` and `second-opinion` bands in
  parallel; triage; fix (cap 2); full suite. Pins and the three advisor
  moments are in Model routing.

### Evidence

- **Test-first:** write the red test, run it red, record the command and output.
- **One check owner:** the build agent/parent runs the changed-area tests and
  the full suite; a repo `AGENTS.md` supplies the command lines. Never use a
  review agent as a check runner. Reviewers never rebuild.
- **Reviewers** read the `review-bundle` directory and the recorded check
  output. `~/.config/opencode/bin/review-bundle` is not on PATH; call it by
  absolute path. Outside git, pass the changed file list.
- **Baseline:** before fixing reviewer findings, run
  `~/.config/opencode/bin/review-bundle <repo> --baseline` and keep
  `05-baseline.json`. After the fix, run it again and pass both bundle
  directories to the re-reviewer.
- **Triage:** fix every 🔴 and every 🟠 that has a repro or violates the
  done-when. An unproven 🟠 gets a probe by the build agent or is downgraded and
  reported; it is not fixed as confirmed.
- **Never** delete, skip, or weaken a test. If a test's expectation was wrong,
  say so and say why.
- The **second-opinion prompt** contains the bundle directory, the plan/done-when,
  and the recorded check output, never the `review-deep` report.

### Safety

- Reviewers are read-only; never give them shell or edit.
- Do not stage, commit, or push unless asked. `git push` is `ask` in
  `opencode.json`; force, delete, mirror, and `+refspec` pushes are denied. Never
  run an unattended session with `--auto`: it approves every `ask`.
- Keep diffs minimal and consistent with the surrounding code.
- Use `explore` for broad searches; do not read the whole repo in the main
  context.

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

## Model routing

Every delegated job runs on its band's pin, not the session's model. The pin
belongs to T3 (the `t3-code` tools), not to a harness.

| Band | Work | providerInstanceId | model | options |
| --- | --- | --- | --- | --- |
| explore, review-light | repo map, grep, T1 diff review | `opencode` | `opencode-go/mimo-v2.6-flash` | none |
| build, plan, general | the session itself, T0/T1 edits | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=high` |
| second-opinion | independent T2 second look | `opencode` | `opencode-go/deepseek-v4.1-flash` | `variant=high` |
| implement-deep | T2 implementation after plan-lock | `opencode` | `claude-agent/sonnet` | `variant=medium` |
| verifier | manual build, test and contract check | `opencode` | `xai/grok-4.7` | `variant=high` |
| plan-review-deep, review-deep | advisor: plan-lock, same error twice, T2 sign-off | `opencode` | `claude-agent/sonnet` | `variant=high` |

- Call `orchestrator_capabilities` once per thread before the first delegation,
  and again only after an error or a provider the user names. Pass the pin as
  `target: { providerInstanceId, model, options: [{ id, value }] }`.
- Delegate through T3 even when the target matches the session's provider, so
  one table holds in opencode, Claude Code and Grok Build. Use a native subagent
  only when the T3 tools are absent (explore, and reviewers as below); say in the
  reply that the pin did not apply.
- The advisor and implement bands are never silently downgraded. If T3 is
  absent, say so instead of substituting the session model.
- Reviewers (`review-light`, `review-deep`, `plan-review-deep`, `second-opinion`)
  run as T3 children with `isolation: "worktree"`, `role: "review"` and the
  review-bundle path in the task. T3 cannot make a child read-only, but a
  worktree child's edits never reach your checkout; confirm `git status` is
  unchanged afterwards. With no T3, use the harness's own read-only reviewer
  (`agents/*.md`, `~/.claude/agents`) and say the pin did not apply.
- `isolation: "worktree"` also for any child that needs its own checkout or will
  open a PR; `shared` only for research. `mode: "wait"` only when this turn needs
  the result (a gate does; a background job does not). `role` names the band's
  job: `research`, `review`, `implementation`, `test`, `design` or `general`.
- Replace a running child with `task_cancel`, then a new `delegate_task`; never
  poll `task_status`.
- The advisor pin is spent at three moments only: (1) T2 plan lock before the
  plan is fixed; (2) the same error or failing assertion twice in a row, passing
  both attempts; (3) T2 sign-off, with `second-opinion` in parallel. A T1 retry
  stays on the builder band.
- `agents/*.md` are the native fallback, not the routing source, and a pin must
  name an enabled instance in `policy/providers.json`. `grok-4.5` has no
  clean-case gate, so the verifier stays on `grok-4.7`.
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

Read-only agents (the four reviewers) use only the read-only Roslynk tools listed in
the `roslynk-rules` skill, never the ones that write.

`get_diagnostics` is a compile check, not a test run. Tests still go through the
repo's test command, and a repo `AGENTS.md` may name a build command that must
still be run.
