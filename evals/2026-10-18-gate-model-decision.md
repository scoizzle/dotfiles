# Reviewer model decision — 2026-10-18

Rule (D5): keep the current model only if it has no veto (does not miss an
expected 🔴 that another candidate caught), its recall is at least the
alternative's, and its median seconds per case is lower.

Golden set: 8 cases (5 original + 3 added this change: `array-element-access`,
`concat-nonstring-operand`, `for-zero-records-noop`). One repo.

| Model | Recall | Missed | Per-case seconds | Median |
| --- | --- | --- | --- | --- |
| `xai/grok-4.7#high` | 15/15 | — | 149 195 197 240 243 287 295 342 | 242 s |
| `opencode-go/mimo-v2.6-flash` | 11/13 (7 cases scored) | 🔴 `no-ddl-producer` (plan); 🟠 `enum-column-type` | 256 315 353 549 999 1067 | 451 s |

## Decision

**Keep `xai/grok-4.7#high`.** It has no veto, full recall, and is roughly twice
as fast at the median. MIMO is out on the veto: it missed the plan's 🔴 premise
finding that grok caught.

The 120 s median ceiling proposed in the plan is withdrawn. Both candidates are
well above it; the useful bar is "no slower than the alternative", and grok
clears it.

## Limits

- Eight cases, one repo, one language. The three added cases are un-fixed real
  fixes (the durable recipe), but their `require` patterns are a loose floor.
- `opencode-go/deepseek-v4-pro#max` (the third candidate) was not run. Grok wins
  on both recall and speed, so it would not change the decision.
- Recall is matched by file plus concept regexes, so a right-file, thin-reasoning
  report scores. Read the findings, not only the total.

## Phase 2 — light reviewers (2026-10-27)

The default workflow now uses `review-light` (MiMo 2.6 Flash) for T1 changes,
`review-deep` (Grok 4.7#high) for T2 changes, `plan-review-deep` (Grok) for T2
plans, and `second-opinion` (Claude Haiku 5.5#high) for T2. T1 plan review is a
build self-check; T2 plan review is Grok. Phase 4 moves `second-opinion` onto
Sonnet; the Haiku model in the command below is the Phase 2 pin.

Gate: a light reviewer must not miss a T1 case that the Grok baseline caught on
the same case. The enum case is T2 and is scored on `review-deep`, not
`review-light`. Run:

```sh
./run.sh --tier T1 -a review-light -m opencode-go/mimo-v2.6-flash
./run.sh --tier T2 -a review-deep -m xai/grok-4.7#high
./run.sh -a second-opinion -m opencode-go/claude-haiku-5-5#high -c storage-enum-backing-type
./run.sh -a plan-review-deep -m xai/grok-4.7#high -c plan-ide-storage-tab
```

If a light reviewer misses a case the Grok baseline caught, fail the change and
adjust the model or the classification. Do not record the miss as a note.

### Result — 2026-10-28

T1 cases: `concat-nonstring-operand`, `for-zero-records-noop`,
`mcp-nav-rendering`.

| Reviewer | Recall | Seconds |
| --- | --- | --- |
| `review-light` MiMo 2.6 Flash, diff-focused 12-step prompt | 4/4 | 300, 183, 406 |
| `review-deep` Grok 4.7#high baseline | 4/4 | 320, 264, 214 |

The T1 gate runs with the eval runner's `--standalone` isolation and a
900-second per-case cap. The gate passes. MiMo reported extra findings outside
`expected` (stale tests, goldens, an ADR reversal). They are listed for human
triage, not counted against recall. The earlier D5 veto was a plan premise and an
enum change; both are T2 in this workflow, so it does not apply to T1 change
review.

## Phase 4 — routing bands (2026-10-31)

Advisor spend is three moments, not a default model. `xai/grok-4.7#high` keeps
the advisor pin: the 2026-10-18 gate gave it no veto, full recall, and a lower
median than MiMo. The moments are:

1. **Plan lock** — `plan-review-deep`, before a T2 plan locks.
2. **Same error twice** — the same error or the same failing assertion on a
   second T2 attempt. The build agent consults the advisor pin on that stuck
   point and does not rerun the search on it.
3. **Sign-off** — `review-deep`, before a T2 change is called done.

Swarm work (repo map, grep, parallel read-only search) stays on `explore`
(`opencode-go/mimo-v2.6-flash`). T1 review stays on `review-light` (same pin).
The default builder stays `opencode-go/deepseek-v4.1-flash#high` on `build`,
`plan`, and `general`. T2 implementation stays `implement-deep` on
`claude-agent/sonnet#medium`. Roles stay on the provider the gates support.
This repo has no Claude Code `--advisor` flag; the moments above are the
policy the build agent follows.

### Procedural pins leave the advisor

`verifier` is procedural: collect evidence, run the build and the changed-area
tests, write the coverage block, grade the contract. It is not one of the three
advisor moments. `docs/per-step-model-selection` (`0a8cc93`, 2026-10-31)
recorded the gate below. This change takes that pin direction and leaves that
branch's fixture and scorer edits behind.

Metered spend in the 14 days to 2026-10-31 was $438.73, from `session_v2`.
`xai/grok-4.7#high` was $397.74 of it, and `verifier` was $214.49.
`claude-agent` reports $0 there (flat rate), so the figure is metered dollars
only.

| Role | Before | After |
| --- | --- | --- |
| `verifier` | `xai/grok-4.7#high` | `claude-agent/sonnet#medium` |
| `second-opinion` | `claude-agent/haiku#high` | `claude-agent/sonnet#medium` |

Recorded results from that branch, not re-run here:

| Case | Model | Result | Seconds |
| --- | --- | --- | --- |
| `concat-nonstring-operand` | `claude-agent/sonnet#medium` | 1/1 recall | 29 |
| `concat-nonstring-operand` | `xai/grok-4.7#high` | 1/1 recall | 828 |
| `clean-enum-backing-type` (`must_pass`, on that branch) | `claude-agent/sonnet#medium` | no 🔴/🟠 | 45 |
| `storage-enum-backing-type` (`second-opinion`) | `claude-agent/sonnet#medium` | 1/1 recall | 19 |

No veto on the seeded case: both models recovered the only expected finding, and
sonnet stayed at 🟡/🟢 on the clean run. The second-opinion move is the
decorrelation one. Haiku mostly agreed with `review-deep`. Sonnet stays a
different family from grok, on the mid-tier pin, so the parallel T2 pass is not
a fourth advisor moment.

### Limits

The recorded gate is two verifier cases and one second-opinion case, one
repository. The clean fixture is not in this tree. `claude-agent` cost is quota
and latency, not a dollar line in `opencode stats`. `review-deep` and
`plan-review-deep` stay on `xai/grok-4.7#high`.


## Phase 3 — verifier and second opinion (2026-10-31)

Metered spend in the 14 days to 2026-10-31 was $438.73, from `session_v2` in
`~/.local/share/opencode/opencode.db`. `claude-agent` and the `opencode` default
provider report $0 there because they are flat rate, so these are metered
dollars, not total cost.
`xai/grok-4.7#high` accounted for $397.74 of it (91%). Shares below are of the
$438.73 total: `verifier` $214.49 (49%), the `reviewer`/`review-deep` roles
$120.01 (27%), `plan-review-deep` $30.52 (7%), and one `build` session $32.72
(7%). The verifier is the most procedural role in the
workflow — collect evidence, run the build and the changed-area tests, write the
coverage block, grade against the contract — and it was consuming the largest
share of the one metered provider.

| Role | Before | After |
| --- | --- | --- |
| `verifier` | `xai/grok-4.7#high` | `claude-agent/sonnet#medium` (flat rate) |
| `second-opinion` | `claude-agent/haiku#high` | `claude-agent/sonnet#medium` |

The second-opinion swap is the decorrelation one: the step exists to catch what
`review-deep` (grok) missed, and the cheapest Claude mostly agreed instead.

### Gate — verifier, both directions

| Case | Model | Result | Seconds |
| --- | --- | --- | --- |
| `concat-nonstring-operand` (seeded 🟠) | `claude-agent/sonnet#medium` | 1/1 recall | 29 |
| `clean-enum-backing-type` (`must_pass`) | `claude-agent/sonnet#medium` | no 🔴/🟠 | 45 |
| `concat-nonstring-operand` (seeded 🟠) | `xai/grok-4.7#high` | 1/1 recall | 828 |

### Gate — second opinion

| Case | Model | Result | Seconds |
| --- | --- | --- | --- |
| `storage-enum-backing-type` | `claude-agent/sonnet#medium` | 1/1 recall | 19 |

No veto: both models recovered the only expected finding on the seeded case, and
sonnet produced only 🟡/🟢 on the clean one. The difference is time — 29 s
against 828 s on the same case — and provider. Sonnet also named a member-write
receiver regression it claimed the change reintroduces; that is outside
`expected`, was not independently verified, and is recorded here as its claim,
not as a finding of this gate.

The clean run's coverage block records `dotnet build` and three filters
(`SqlServerPackTests` 14/14, `SqlitePackTests` 9/9, `*Golden*` 26/26), so its
PASS is not a read-only verdict.

### The clean fixture needed a real oracle

`ad1db6aa` ("preserve scalar assignments when reordering") was the first clean
candidate and was withdrawn. In that run's disposable copy the verifier restored
`Poly/DomainModeling/Lowering/DomainToCSharpExporter.cs` from HEAD and ran
`dotnet run --project Poly.Tests/Poly.Tests.csproj -- --treenode-filter
"/*/*/DomainToCSharpExporterTests/*"` → total 143, failed 0. The added tests pass
without the fix, so they do not discriminate it. That is a true finding about the
merged change, not a false alarm, so the fixture was wrong, not the reviewer.

`clean-enum-backing-type` replaces it. Probe, run 2026-10-31: clone at
`f887d880`, restore `Poly/DomainModeling/Analysis/StorageAnalyzer.cs` from
`d26c61fa`, then `SqlServerPackTests` → total 14, failed 1 and `SqlitePackTests`
→ total 9, failed 1. With the fix present both pass, as the clean run records.

### Limits

Two verifier cases and one second-opinion case, one repository. `claude-agent`
reports $0 in `opencode stats`, so the saving here is quota and latency, not a
measured dollar figure. The clean fixture's ground truth is "no known blocking
defect", which is weaker than an un-fixed real fix's ground truth.

### Harness and variant check (2026-10-31)

Question: does Grok do better in its own CLI than in OpenCode, and is there a
Grok variant that is faster without losing recall?

Method: `evals/run-grok.sh` runs the same case, prompt, timeout, and scorer
through `grok -p` (Grok Build 1.0.70, per `grok --version`), with
`agents/verifier.md` appended as system rules. Model and effort are held constant where the comparison is about
the harness.

| Case | Harness | Model | Result | Seconds |
| --- | --- | --- | --- | --- |
| seeded concat | OpenCode | `grok-4.7#high` | 1/1 | 828 |
| seeded concat | Grok Build | `grok-4.7#high` | 1/1 | 866 |
| clean enum | OpenCode | `grok-4.7#high` | PASS | 603 |
| clean enum | Grok Build | `grok-4.7#high` | PASS | 679 |

The harness makes no difference: same recall in both directions, and Grok Build
is 5–13% slower. Grok's time is reasoning and exploration, not a broken tool —
the Build run made one build and three filtered test runs with no errors, and the
OpenCode run made 91 tool calls to the Build run's smaller set.

Variant results on the seeded case, all 1/1:

| Variant | Harness | Seconds | Cost |
| --- | --- | --- | --- |
| `grok-4.7#high` | OpenCode | 828 | not captured |
| `grok-4.7#medium` | OpenCode | 694 | $4.78, 115 tool calls |
| `grok-4.6#high` | Grok Build | 662 | grok.com subscription |
| `grok-4.7-build-fast` | Grok Build | 570 | grok.com subscription |
| `grok-4.5#high` | Grok Build | 395 | grok.com subscription |

Effort is not a cost lever. `#medium` saved 16% of wall-clock and made *more*
tool calls than `#high` (115 against 91), because lower effort explores more
before committing. `grok-4.7-build-fast` is the only variant that improves time
with the same evidence, so it went on to the recall-sensitive cases:

| Case | `grok-4.7-build-fast` | `grok-4.5#high` |
| --- | --- | --- |
| seeded concat | 570 s, 1/1 | 395 s, 1/1 |
| storage enum 🟠 | 175 s, 1/1 | 145 s, 1/1 |
| `plan-ide-storage-tab` | 216 s, 6/6 incl. 🔴 | 173 s, 6/6 incl. 🔴 |

Both survive when the streamed narration is removed and only the final report is
scored, so the speed was not bought by thin evidence. Each also records the
build and the failing changed-area tests in its coverage block.

The ranking on the seeded case is 4.5 (395 s), build-fast (570 s), 4.6 (662 s),
then 4.7 (828–866 s). The oldest model tested is the fastest at no observed
recall cost on these cases. That is surprising enough to treat as provisional:
it is one run per cell, the plan fixture was extended from a Grok run and may
favour the family, and server-side variance between runs was not measured.

Sonnet remains the reference at 29 s (seeded) and 45 s (clean) through OpenCode,
so even the fastest Grok variant is an order of magnitude slower on routine
verification. The Grok variants are for steps that genuinely need multi-model
recall and can afford minutes. None of 4.5, 4.6, or build-fast is in the OpenCode
catalog, so using any of them means routing that step through the Grok Build CLI.

Limits: one case per cell for the harness comparison, one case for `4.6`, and
three for `4.5` and `build-fast`; one repository, one machine. `grok.com` usage is not in `opencode stats`, so the
Build rows have no dollar figure. Tool-call and build/test counts above are read
from the saved transcripts, not recorded by the runner. Grok Build applies no
agent permission rule, so its write boundary is the prompt and the verifier's
instructions (the fixture source is reachable through the clone's remote);
`run.sh` enforces the same boundary with permissions. `grok-4.6` and
`xai/grok-build-0.1` were not run because the variants that were run already
answered both questions.
