# Lessons

One row per rule in `AGENTS.md`: why it exists, and what enforces it. A rule
with no enforcer is trust, not a guarantee.

| Rule | Why (evidence) | Enforced by |
| --- | --- | --- |
| Full Access only for T3 threads | Agents run with the filesystem and git credentials of the user; the broad mode belongs only inside T3 Code threads where the work is scoped to a worktree | none yet |
| Home-layout moves need my yes | 2026-11-20: a feature worktree's install held for 32 hours; #62 made install refuse to move a real directory (exit 4) | install.sh guard + installer CI job |
| Only the canonical checkout installs | Same 2026-11-20 incident: links point at the checkout that ran install | install.sh (exit 3 unless `FORCE=1`) + installer CI job |
| At most 3 Go children and 2 Claude threads at once | Fan-out burns the shared Go allowance (weekly limit is 50% of monthly) and slows the machine; #62 first capped at 4 | `bin/agent-headroom` (pace check); the count itself: none yet |
| Weekly Go use must not outrun the elapsed week by more than 10 points | Go weekly limit resets Monday 00:00 UTC and is 50% of the monthly allowance | `bin/agent-headroom` + `test/agent-headroom.sh` in CI |
| No adversarial multi-model review except auth, secrets, migrations and public contracts | Multi-model panels multiply cost; `AGENTS.md` already reserves fresh-context cross-family review for those areas | none yet |
| No V4 Pro, Grok 4.7 or Kimi K3 on Go | Per-model monthly limits are small for these (e.g. about 98 requests per 5 hours on Kimi K3 vs 43,300 on DeepSeek V4.1 Flash, per Go docs estimates) | opencode.json pins Flash as default model |
| No `/swarm`, `/arena` or `/interrogate` without my say-so | They fan out many model calls | none yet |
