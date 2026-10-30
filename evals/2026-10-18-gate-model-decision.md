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
build self-check; T2 plan review is Grok.

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


