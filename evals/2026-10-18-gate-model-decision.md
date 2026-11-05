# Reviewer model decision — 2026-10-18

> **Current pins (read this first).** This file is a dated log; Phases 3 and 4
> were reversed by Phase 5. The standing state is in `AGENTS.md` (Model routing)
> and the agent files. At the last re-pin (Phase 7):
>
> | Role | Pin |
> | --- | --- |
> | `explore`, `review-light` | `opencode-go/mimo-v2.6-flash` |
> | `build`, `plan`, `general`, `second-opinion`, `dream-drafter` | `opencode-go/deepseek-v4.1-flash` |
> | `implement-deep` | `claude-agent/sonnet#medium` |
> | `review-deep`, `plan-review-deep` | `claude-agent/sonnet#high` |
> | `verifier` | `xai/grok-4.7#high`; `xai/grok-4.5` is routable but has no clean-case gate |
>
> **Phase 6 corrects the money in Phases 3, 4 and 5.** Those dollar figures are
> `session_v2.cost`, which opencode computes from list price, not an invoice.
> Read them as "what these tokens would cost on a metered key".

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
build self-check; T2 plan review is Grok. Phase 4 moved `second-opinion` onto
Sonnet and Phase 5 moved it to DeepSeek; the Haiku model in the command below is
the Phase 2 pin.

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

## Phase 3 — verifier and second opinion (2026-10-31)

> The pins in this phase were reversed by Phase 5 on quota grounds. The gate,
> the clean fixture, and the scorer changes stand.

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

## Phase 4 — routing bands (2026-10-31)

> Phase 5 re-pins the advisor to the T3 Grok provider on `grok-4.5`, on the
> provisional variant evidence in Phase 3. The OpenCode YAML still names 4.7,
> because that catalog stops there.

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

> Phase 5 reverses the Sonnet pin below on quota grounds. The band rationale
> (procedural work is not an advisor moment) still holds.

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

## Phase 5 — quota-aware re-pin (2026-10-31, later)

Phase 3 and Phase 4 put `verifier` and `second-opinion` on
`claude-agent/sonnet#medium` because the Claude subscription reports $0 in
`opencode stats`. That optimised metered dollars, not quota. Claude quota is the
binding limit, and the verifier is the highest-volume step in the workflow: 86
sessions in the 14 days to 2026-10-31 (`session_v2`), about six a day. A step at
that rate must not sit on the quota-limited provider, however fast it is.

Gate: `concat-nonstring-operand` (seeded 🟠) and `clean-enum-backing-type`
(`must_pass`), the same two-direction rule as Phase 3, on the two cheap
OpenCode pins.

| Model | Seeded | Clean (`must_pass`) | Seconds (seeded / clean) |
| --- | --- | --- | --- |
| `opencode-go/deepseek-v4.1-flash#high` | 1/1 | **FAIL** — false 🔴 on stale docs | 139 / 349 |
| `opencode-go/mimo-v2.6-flash` | 1/1 | **TIMEOUT** at the 1200 s cap | 729 / 1200 |
| `claude-agent/sonnet#medium` (reference) | 1/1 | PASS | 29 / 45 |
| `xai/grok-4.7#high` (reference) | 1/1 | PASS | 828 / 603 |

Neither cheap pin clears both directions. DeepSeek has no recall loss: it found
the seeded 🟠, and its second-opinion run found the enum 🟠 in 46 s. But on the
clean change it escalated stale
historical documentation (`docs/probes/findings/…`, `docs/plans/…`) to 🔴. Those
paths are historical by the repository's own doc rules, so that is a blocking
false alarm, not a nit; the clean fixture exists to catch exactly this. MiMo did
not finish the clean case inside twenty minutes.

### Pins after Phase 5

| Role | Pin | Why |
| --- | --- | --- |
| `verifier` | `xai/grok-4.7#high` | Off Claude. The only gated option quiet on a clean change; metered, ~10 min per run. |
| `second-opinion` | `opencode-go/deepseek-v4.1-flash#high` | Different family from `review-deep`; 1/1 on `storage-enum-backing-type` in 46 s; off Claude. It shares a family with the default builder, which is acceptable because the pass exists to catch the first reviewer's blind spots, not the author's. |
| `plan-review-deep`, `review-deep` | T3 Grok on `grok-4.5` | Phase 3's variant check (provisional); OpenCode YAML keeps `xai/grok-4.7#high` because the catalog stops at 4.7. |
| `implement-deep` | `claude-agent/sonnet#medium` | The one remaining Claude role, about one T2 per day. |

The `0a8cc93` flip to Sonnet is reversed here. That commit stays in history
because the `must_pass` gate, the clean fixture, and the scorer changes came
with it; only the pin moves back.

### What would change this

- A cheap model that stays quiet on the clean case (DeepSeek came within one
  severity call), or a verifier rule that makes historical documents 🟡.
- Clean-case evidence for `grok-4.5` via T3, which would cut the verifier from
  ~10 minutes to ~7 without the metered xAI 4.7 pin.
- Native Claude Code through T3, which changes quota accounting but not the
  rule that the high-volume verifier stays off Claude.

Limits: one run per cell, one repository. The DeepSeek failure is a severity
judgement on documentation outside the diff; read the report before treating it
as a hard veto against the model everywhere.

## Phase 6 — cost provenance (2026-11-02)

Phases 3 and 4 re-pinned two roles to save money. Phase 5 moved them back on
quota grounds, and that reason stands. The money was never there.

`session_v2.cost` in `~/.local/share/opencode/opencode.db`, over the 60 days to
2026-11-02, is computed locally from the `models.json` price table; it is not a
vendor invoice. Two providers prove it:

| provider | sessions | recorded cost | why |
| --- | --- | --- | --- |
| `opencode-go` | 506 | $112.27 | a plan that is subscribed, still priced from the table |
| `claude-agent` | 14 | $0.00 | no `models.json` entry, so nothing to compute |

`$0` therefore means "unpriced", not "unmetered", and a positive number means
"priced", not "billed". The $438.73 split by role in Phase 3 is the list-price
value of the tokens each role consumed, which is a useful quantity and a
misleading label.

The xAI side settles it. The `xAI` credential is a device-flow OAuth login
(`type: oauth`, `method: device`) against `auth.x.ai/oauth2`, not an API key;
opencode's integration offers `Manually enter API Key` as the other method and
that one was not taken. `console.x.ai` for 2026-10-27 to 2026-11-02 reports
**0 requests, 0 tokens, $0.00**, while the same window holds:

| | Oct 27 – Nov 2 |
| --- | --- |
| xAI sessions | 68 |
| input tokens | 12.48M |
| cache reads | 163.6M |
| list price | $116.52 |

Traffic that does not appear as API requests is not on the metered path. The
earlier 126 sessions (Oct 18–26, $283.90 of list price) used the same grant, the
same token and the same `api.x.ai/v1` base URL, so they are on that path as well.
`grok-4.7` through the `opencode` instance is subscription-entitled.

### What this changes

- Phase 3 and Phase 4's dollar rationale is void. The `verifier` never cost
  $214.49 per fourteen days; in that week it ran 16 sessions and consumed 41.3M
  cache reads, about 2.6M per run. The other 52 sessions in the window were the
  advisor bands (24 `review-deep`, 21 `plan-review-deep`, 7 unattributed), which
  is the case for keeping the advisor off the highest-volume step.
- Phase 5's quota rule survives and is now the only cost-adjacent constraint: the
  high-volume step belongs on whichever subscription has headroom, not on
  whichever model carries the lower price row.
- The prices in this file keep one use. They are what these sessions would cost
  if the grant lapsed and opencode fell back to an API key.

### Pins after Phase 6

> Phase 7 supersedes the two advisor rows below.

The `grok` and `claudeAgent` T3 instances are disabled; both models are reachable
through the single `opencode` instance, which multiplexes the Go plan and the xAI
and Claude logins.

| Role | Pin | Why |
| --- | --- | --- |
| `implement-deep` | `opencode` + `claude-agent/sonnet` + `variant=medium` | Same model and effort as before, on the Claude login. |
| `verifier` | `opencode` + `xai/grok-4.7` + `variant=high` | Heaviest token consumer; put it on the xAI grant. |
| `plan-review-deep`, `review-deep` | `opencode` + `xai/grok-4.7` + `variant=high` | Unchanged model, same grant. |
| everything else | unchanged | already on `opencode`. |

The option id moves with the instance: `claudeAgent` took `effort`, `opencode`
takes `variant`. `opencode-go/grok-4.7` also exists and would draw the Go plan
instead of the xAI login. `grok-4.7-build-fast` remains reachable only through
the disabled `grok` driver.

`bin/lint-config` now reads `policy/providers.json`, a `verified` snapshot of
`orchestrator_capabilities`, and fails any routing row that names a disabled
instance. That is what catches this class of rot: the rows were green for a day
while four bands could not be delegated.

Limits: one account, one console window, one repository. The console showed a
single team; usage under another team on the same account was not checked. Grok
4.5 and 4.6 were re-verified as routable through `opencode` but were not run.

## Phase 7 — quota headroom re-pin (2026-11-04)

Phase 5's quota rule was the only reason the advisor stayed off Claude. The
user reports the Claude subscription is no longer near its limits, so the
advisor moves to the model that passed the clean-case gate fastest. Phase 6
measured this band at about three times the verifier's session rate, so the
change spends quota rather than sparing it; it rests on headroom, not volume.

| Role | Pin | Why |
| --- | --- | --- |
| `plan-review-deep`, `review-deep` | `opencode` + `claude-agent/sonnet` + `variant=high` | Headroom granted by the user; lowest latency on the recorded gate, but `#high` is ungated. |
| `verifier` | unchanged: `opencode` + `xai/grok-4.7` + `variant=high` | Keeps the xAI grant; not re-gated here. |
| `second-opinion` | unchanged: `opencode-go/deepseek-v4.1-flash#high` | Different family from a Claude `review-deep` on the routed path; the native fallback gap is noted below. |
| `implement-deep` | unchanged: `claude-agent/sonnet#medium` | Same model, lower effort; about one T2 a day. |

Caveats:

- The 29/45 s figure is `claude-agent/sonnet#medium` on the verifier gate.
  `#high` is a legal variant (re-verified 2026-11-04) but is an ungated effort
  bump, so advisor quality was not re-measured.
- Family diversity holds on the routed path only: the native fallback renders
  `review-deep`, `plan-review-deep` and `second-opinion` on the same Claude
  model (`policy/permissions.json`), so the second pass is not decorrelated
  there.
- The ~1.8x token inflation was a T3 accounting bug, not this repository's; the
  headroom claim rests on the user's report.
- `policy/providers.json` was re-verified against `orchestrator_capabilities` on
  2026-11-04; the allowlist is deliberately unchanged.

### What would change this

- Claude quota tightening again: move the advisor back to `xai/grok-4.7#high`
  under the Phase 5 rule.
- A measured advisor gate on `claude-agent/sonnet#high`; the recorded figure is
  `#medium` on the verifier gate.
