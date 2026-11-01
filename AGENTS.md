# Global instructions

Repository `AGENTS.md` files are additive. Their build/test command lines win.

## Default workflow

The default `build` agent runs this workflow for every request. Subagents follow
their own role prompt and do not re-run it.

Before the first edit or subagent call, state the tier on its own line:
`Tier: T0`, `Tier: T1`, or `Tier: T2`. A short read-only look at the repo is
allowed; never state a tentative tier. Then state the agents and the reason.
Never ask the user to choose a tier or model.

### Classify

- **T0:** no behaviour change, or one obvious mechanical edit; no public
  contract, data, security, or CI. Do it; run the check.
- **T1:** one area, <=3 source files, <=400 lines, no public contract/data/
  security/CI, test oracle exists. Plan in <=10 lines with done-when and the red
  test; self-check the plan; implement; run the changed-area tests; launch
  `review-light`; fix once.
- **T2:** anything else, or "design/architecture/migration/security/data/schema/
  enum/public API/be careful", or unsure. Write a plan with done-when; launch
  `plan-review-deep`; fix plan findings (cap 2); implement with
  `implement-deep`; run checks; launch `review-deep` and `second-opinion` in
  parallel; triage; fix (cap 2); full suite. Pins and the three advisor
  moments are in Model routing.

### Evidence

- **Test-first:** write the red test, run it red, record the command and output.
- **One check owner:** the build agent/parent runs the changed-area tests and
  the full suite. A repo `AGENTS.md` supplies the command lines. Do not use a
  review agent as a check runner; if a repo names one, run the commands
  directly and keep the review separate. Reviewers never rebuild.
- **Reviewers** read the `review-bundle` directory and the recorded check
  output. `~/.config/opencode/bin/review-bundle` is not on PATH; call it by
  absolute path. If the change is outside git, pass the changed file list
  instead.
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
- Do not stage, commit, or push unless asked.
- Keep diffs minimal and consistent with the surrounding code.
- Use `explore` for broad searches; do not read the whole repo in the main
  context. `explore` stays on its cheap pin (Model routing).

### Ledger

After the user answers the findings, run
`~/.config/opencode/bin/review-log` with tier, models, counts, acted/dismissed.
If the user has not answered, write the line as `pending`.

### Manual overrides

`/verify` and `/second-opinion` are manual escape hatches. `build`, `plan`,
`explore`, and `verifier` remain available; `verifier` is a manual shell-based
deep check, not the default review path.

## Model routing

Match cost to the job. The bands are the policy; the pins are what the gates
currently support and may move when a later gate says so. A band does not
require a Claude model name. This setup has no `--advisor` switch: the build
agent delegates to the named subagent.

Claude quota is the binding limit, not metered dollars. `claude-agent` reports
$0 in `opencode stats`, so a Sonnet row looks free while it spends the scarce
resource. Keep the high-volume steps (`verifier`, `explore`, `review-light`)
off Claude; reserve it for `implement-deep`, which runs about once a day.

| Band | Work | Pin |
| --- | --- | --- |
| Swarm | Repo map, grep, parallel read-only search | `explore`: `opencode-go/mimo-v2.6-flash` |
| Cheap review | T1 diff review | `review-light`: `opencode-go/mimo-v2.6-flash` |
| Builder | Default session and T0/T1 edits | `build`, `plan`, `general`: `opencode-go/deepseek-v4.1-flash#high` |
| Builder | T2 implementation after plan-lock | `implement-deep`: `claude-agent/sonnet#medium` |
| Procedural | Build, tests, coverage, contract grade | `verifier`: `xai/grok-4.7#high` |
| Opposite | Independent T2 second look | `second-opinion`: `opencode-go/deepseek-v4.1-flash#high` |
| Advisor | Deep judgment only | `plan-review-deep` and `review-deep`: T3 Grok provider on `grok-4.5` (provisional) |

`explore` does every repo map, grep, and parallel read-only search, including
while a builder or advisor session is open. Do not hand that work to
`plan-review-deep`, `review-deep`, or `verifier`.

**Where the advisor runs.** The Grok bots (Jarvis, Chieftan) are orchestrators
only; they do not do repository work. Worker models are T3 child sessions, and
the advisor pin runs through the T3 Grok provider on `grok-4.5`. The OpenCode
YAML keeps `xai/grok-4.7#high` because that catalog stops at 4.7; when a job
needs 4.5, run it through T3 rather than claiming an OpenCode pin the catalog
cannot serve. `grok-4.5` is provisional: it beat 4.7 on three cases in one
repository, one run per cell.

**opposite-lab.** The T3-side independent review of the same artifact, run on
the T3 Grok provider. It buys a different execution context, not a different
family; `second-opinion` is the family-independent pass and stays on
`opencode-go/deepseek-v4.1-flash#high`.

The advisor pin is spent at three moments only:

1. **Plan lock.** Before a T2 plan locks, launch `plan-review-deep`. A T1 plan
   stays a build self-check on the builder pin.
2. **Same error twice.** When the same error or the same failing assertion
   repeats on a second attempt during T2 implementation, stop retrying on the
   builder and on `explore`. Consult the advisor pin on that stuck point:
   `plan-review-deep` when the plan is what is stuck, `review-deep` when the
   change is. Pass the failure and the two attempts. A first failure is not
   this moment. A T1 retry stays on the builder; do not promote it.
3. **Sign-off.** Before calling a T2 change done, launch `review-deep`. Launch
   `second-opinion` in parallel on its mid-tier pin; that pass is not the
   advisor. T1 sign-off is `review-light`. `verifier` is the manual shell
   check, not an advisor moment and not the default gate.

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

Read-only agents (`review-light`, `review-deep`, `plan-review-deep`,
`second-opinion`) may use only the read-only Roslynk tools — never
`apply_code_fix`, `apply_code_action`, `apply_patch`, `rename_symbol`,
`rename_parameter`, `change_signature`, `extract_method` or `remove_unused_usings`.

`get_diagnostics` is a compile check, not a test run. Tests still go through the
repo's test command, and a repo `AGENTS.md` may name a build command that must
still be run.
