---
description: Verify the current uncommitted change with the manual verifier band
---

Verify the current uncommitted change.

Bundle: !`~/.config/opencode/bin/review-bundle .`

Contract / scope (what "done" means; may be empty): $ARGUMENTS

Delegate the `verifier` band (AGENTS.md, Model routing: `opencode`,
`claude-agent/sonnet`, `variant=high`) through T3 `delegate_task`, with
`isolation: "worktree"` and a brief whose `PROMPT:` line reads
`~/.config/opencode/agents/verifier.md`. The verifier band has no quota fallback
(`none`): if its pin is unavailable, report it blocked and do not substitute.
Pass the bundle directory, the contract above, and the check command and output.
Do not run the build or tests yourself; the verifier runs its own probes in a
disposable clone. If the bundle command failed because this is not a git
repository, say so and use the changed file list instead.

`/verify` and `/second-opinion` are user-invoked manual overrides, not part of the
default workflow.
