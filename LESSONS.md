# Lessons

One row per rule in `AGENTS.md`: why it exists, and what enforces it. A rule
with no enforcer is trust, not a guarantee.

| Rule | Why (evidence) | Enforced by |
| --- | --- | --- |
| At most 3 Go children and 2 Claude threads at once | Fan-out burns the shared Go allowance (weekly limit is 50% of monthly) and slows the machine; #62 first capped at 4 | `bin/agent-headroom` (pace check); the count itself: none yet |
| Heavy T3 work launches on the Mac | 2026-11-25: T3 Code runs only on the Mac and the WSL2 desktop is not linked, so a child pointed at WSL2 cannot launch and would improvise | none yet |
| Weekly Go use must not outrun the elapsed week by more than 10 points | Go weekly limit resets Monday 00:00 UTC and is 50% of the monthly allowance | `bin/agent-headroom` + `test/agent-headroom.sh` in CI |
| No adversarial multi-model review except auth, secrets, migrations and public contracts | Multi-model panels multiply cost; `AGENTS.md` already reserves fresh-context cross-family review for those areas | none yet |
| No V4 Pro, Grok 4.7 or Kimi K3 on Go | Per-model monthly limits are small for these (e.g. about 98 requests per 5 hours on Kimi K3 vs 43,300 on DeepSeek V4.1 Flash, per Go docs estimates) | opencode.json pins Flash as default model |
| No `/swarm`, `/arena` or `/interrogate` without my say-so | They fan out many model calls | none yet |
| A manager thread settles its PR before it ends | #63 ended with a check still pending; #62 stopped watching once green and an unresolved review conversation then blocked merge; PR #58 had dropped the earlier watch rule | `bin/pr-settle` + `test/pr-settle.sh` in CI; the watch itself: trust (T3 `watch_pull_request`) |
