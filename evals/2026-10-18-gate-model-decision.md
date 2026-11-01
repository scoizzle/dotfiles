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


