# Golden set

A yardstick for the review gates: fixtures whose true defects are known, plus a
runner and a scorer. Model, scope, prompt, and step-budget changes get scored
against the same cases instead of being argued about from a single diff.

Two artifacts are covered: a **change** (a diff, caught before it ships) and a
**plan** (a proposal, caught before it is executed).

## Run it

```sh
./run.sh                                      # every change case, agent by tier
./run.sh --tier T1 -a review-light -m opencode-go/mimo-v2.6-flash
./run.sh --tier T2 -a review-deep -m xai/grok-4.7#high
./run.sh -a plan-review-deep -m xai/grok-4.7#high -c plan-ide-storage-tab
./run.sh -a verifier -m claude-agent/sonnet#medium -c concat-nonstring-operand
```

`run.sh` prints a per-case line, then the model's cost and step delta for the run,
then the results directory. Grade it:

```sh
./score.py /private/var/folders/.../opencode/evals-run/20261017-034500
```

`score.py` exits non-zero when an expected finding was missed, so it can gate a
change. Compare two models by running each in turn and reading the `TOTAL` line.
`run.sh` exits non-zero when a case fails before or during review. Each case has
a 900-second cap; set `EVAL_CASE_TIMEOUT` for a slower case.

Each case clones its fixture repo at a base commit into a scratch directory under
`$EVAL_WORK_ROOT` (default: the opencode temp dir) and runs the agent there. A
change case applies its patch first; a plan case leaves the tree clean and passes
the plan in the prompt. It uses `git clone --shared`, which reads the source
repository's objects and writes nothing back — the fixture repo is never modified
and its worktrees are never touched.

## Layout

```text
cases/<case-id>/case.json      fixture definition
cases/<case-id>/change.patch   the diff, for a change case
cases/<case-id>/plan.md        the plan, for a plan case
run.sh                         run one model over the case set
score.py                       grade results against expectations
cost.py                        per-model cost/steps for one run (called by run.sh)
scoreboard.py                  standing view of the gates, from the session store
```

`case.json`:

| Field | Meaning |
| --- | --- |
| `id` | Case name; matches the directory. |
| `artifact` | `change` (default) or `plan`. |
| `tier` | Required: `T0`, `T1`, or `T2`. `--tier` selects change cases only; T1 uses `review-light`, T2 uses `review-deep`, and a plan case uses `plan-review-deep`. |
| `repo` | Fixture repository path. |
| `base` | Commit the artifact is presented against. |
| `patch` | Change cases: patch file, default `change.patch`. |
| `plan` | Plan cases: plan file, default `plan.md`. |
| `goal` | Plan cases: the goal the plan has to satisfy. |
| `claim` | Change cases: what the author says the change does, so a misleading claim is part of the fixture. |
| `expected[]` | One entry per true defect: `id`, `severity`, `files[]` (or a single `file`; omitted means patterns only), `require[]` (case-insensitive regexes that must all appear in the final report), `notes`. |
| `must_pass` | `true` marks a clean fixture: `expected` is empty and the run fails if the report contains a 🔴 or 🟠. 🟡 and 🟢 are allowed. The marker counts anywhere on a line outside a fenced code block, so bolding or numbering a finding cannot hide it; a line that negates the marker before it ("no 🔴 or 🟠 findings") does not count. |

## Cases

| Case | Artifact | Source | Defects |
| --- | --- | --- | --- |
| `wip-slice-c8-tc2` | change | a real uncommitted change | 🔴 CI restore broken by a MAUI project added to the solution; 🟠 report-tab highlight bound to the wrong field |
| `storage-enum-backing-type` | change | inverse of `f887d880` | 🟠 an enum column emits the enum's own name instead of the pack's integer mapping |
| `createin-previous-stage` | change | inverse of `17d6f212` | 🟠 `previousStage` loses nullability; the emitted C# no longer compiles |
| `mcp-nav-rendering` | change | inverse of `e2ca854a` | 🟠 a navigation dumps the whole instance; 🟠 a stage-less entity reports `currentStage` null |
| `array-element-access` | change | inverse of `254e4fe3` | 🟠 a scalar array's element type resolves to `object`, so the array is `object[]` while the index routes cast to `long[]` and access throws |
| `concat-nonstring-operand` | change | inverse of `9838889a` | 🟠 concatenation with a non-string operand does not convert or box at the slot kind |
| `for-zero-records-noop` | change | inverse of `0c321d5e` | 🟠 a `for` over zero records lowers to a failure instead of a no-op |
| `plan-ide-storage-tab` | plan | hand-authored, then extended from a real run; every defect verified against `b09ffddd` | 🔴 the plan's premise is false — nothing in the repo emits SQL DDL; 🟠 a versioned `PackageReference` under CPM; 🟠 `dotnet test` instead of the repo's runner; 🟠 adding the MAUI head to the only solution file; 🟠 the new component's namespace is never imported; 🟠 the mode dependency is omitted |
| `clean-enum-backing-type` | change | a real merged fix (`f887d880`) replayed at its parent | none — `must_pass`; any 🔴 or 🟠 is a false alarm |

Tier assignment: `concat-nonstring-operand`, `for-zero-records-noop`, and
`mcp-nav-rendering` are T1; the rest are T2. The enum case is deliberately T2,
so `review-light` is never scored on it.

## Verifier gate

The verifier is scored in both directions, because a verifier that never finds a
defect and one that finds a defect everywhere both cost the same:

```sh
./run.sh -a verifier -m claude-agent/sonnet#medium -c concat-nonstring-operand
./run.sh -a verifier -m claude-agent/sonnet#medium -c clean-enum-backing-type
```

The first is the seeded-🟠 change `review-light` already uses. The verifier has
shell, so it is expected to run the repository's build and changed-area tests; a
red test is the finding. The second is a real merged fix whose tests fail if the
production change is reverted: `must_pass` makes any 🔴 or 🟠 a failure. The pair
is what matters — the first catches a rubber stamp, the second catches invented
findings, and a model that scores well on only one is not deployable.

A clean fixture is only usable if its oracle is real. Before adding one, restore
the production files to the base commit and run the changed-area tests: if they
stay green, the change's own tests do not discriminate and the fixture is not
clean, it is unproven. That check withdrew `ad1db6aa` as a candidate: the
verifier found, correctly, that its added tests pass with the fix reverted.

With `-a verifier`, `run.sh` leaves the diff out of the prompt. A pasted diff
lets the verifier skip the build and the tests, which is the behaviour this gate
measures.

## Three ways to add a case

**Un-fix a real fix.** Most durable: a real defect with a real fix as its answer.

```sh
git -C <repo> diff <fix> <fix>^ -- <production path> > cases/<id>/change.patch
```

Set `base` to `<fix>` and invert the claim so the description matches the change
as presented. Limit the patch to production files: keeping the fix's tests would
put the answer in the tree.

**Freeze a real uncommitted change** before it is committed:

```sh
git -C <repo> diff -- <paths> > cases/<id>/change.patch
```

Set `base` to the current `HEAD`.

**Write a plan whose defects are checkable.** Every expected finding must be
verifiably true against the base commit — a fixture that is wrong about the repo
is worse than no fixture. Before committing one, confirm each defect holds:

```sh
git clone --shared --no-checkout -q <repo> /tmp/check
git -C /tmp/check checkout -q <base>
grep -n <the rule the plan violates> /tmp/check/<file>
```

## Standing view: scoreboard.py

```sh
./scoreboard.py --days 14
./scoreboard.py --all          # lifetime, which doubles as the pre-gate baseline
```

Reads `session_v2` read-only and reports per-agent runs, cost, and share; reviewer
runs per day, latency p50/p95, and cost as a share of spend; and a gate-coverage
proxy.

The two metrics that matter most — **yield** (did the review say anything worth
acting on) and **dismissal** (how often you waved a finding off) — are not in the
session store. Reviewer transcripts are not persisted for `opencode run`
sessions, so they are logged at the source. The review gate appends one line per
review to `~/.config/opencode/reviews.jsonl`, and `scoreboard.py` reads it as its
own section. The line is written once the user has answered the findings, because
`acted` and `dismissed` are known only then:

```json
{"ts":"...","artifact":"change","model":"...","red":1,"amber":2,"yellow":3,"green":0,"acted":2,"dismissed":0}
```

Two caveats on the numbers it does produce:

- Gate coverage is a proxy — reviewer launches over `build` sessions in the window.
  It reads `0%` whenever reviews were launched manually rather than by the gate,
  which is correct but not a failure.
- Do not read `time_updated - time_created` for primary agents as latency. `build`
  averages hours because sessions idle and resume. It is only meaningful for
  short-lived subagents such as the reviewer.

## What this measures, and what it does not

**Measures recall**: did the reviewer surface the defect the artifact introduced.
That is the property the team depends on. A `must_pass` case measures the other
direction — did it stay quiet on a clean change — but only for the verifier gate
in practice, because a clean change gives it nothing to find and a reviewer has
no way to earn credit.

**Does not measure precision.** A finding about a file the diff never touched may
be a legitimate cross-boundary catch rather than noise, so unmatched findings are
listed for a human to read, not counted against the model.

Other honest limits:

- Eight cases, one repo, one language. A model that wins here is not proven.
- Recall is matched by file plus concept regexes, so a reviewer that names the
  right file and the right concept scores even when its reasoning is thin. Read
  the findings before trusting a score.
- The `require[]` patterns are tuned to accept reasonable phrasings. They are a
  floor on credit, not a measure of quality.
- One plan case is a smoke test of plan review, not a measurement of it.
- **A hand-authored plan fixture is incomplete by construction**, more so than a change
  fixture. A change fixture's ground truth is a real fix that already exists; a plan
  fixture's ground truth is only what its author knew. `plan-ide-storage-tab` was
  written with three planted defects and a real run found six; the four extra were
  verified against the base commit and then added. So a plan score reads as a floor
  twice over: the reviewer may find true defects that `expected` does not contain,
  and adding them afterwards is fitting the fixture to one model's output. Prefer
  un-fixing a real fix, and read plan findings rather than trusting the total.
- Cost is attributed by diffing day-scoped stats around the run, so it is only
  accurate when nothing else uses the same model at the same time.
