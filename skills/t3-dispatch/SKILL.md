---
name: t3-dispatch
description: How the lead dispatches a reviewer, advisor, explore, verifier or implementor through T3 delegate_task, the only dispatch path (opencode's subagent tool is denied). Load before any delegate_task.
license: MIT
compatibility: opencode
---

# T3 dispatch

All dispatch is T3 `delegate_task`. A T3 child always runs as `build` (or
`plan` in plan mode): `delegate_task` cannot pick an agent, so the brief and
`plugins/harness-guard.js` make it a role.

## The target

`{providerInstanceId: "opencode", model, options: [{id: "variant", value}]}`,
split from the role's `model#variant` in
`~/.config/opencode/models.resolved.json` (reviewer, advisor, explore, verifier,
implementor). When `review_mode` is `stop`, a sensitive change stops and asks
instead of dispatching a reviewer.

## The brief

1. First line: `role: <role>`. The plugin reads it (T3 puts its own header and
   an `Act as the … sub-agent` line above; both are skipped) and allows only
   that role's tools from `policy/permissions.json` `roles`. A T3 child with no
   role line gets the read-only set; an ask becomes a deny, and the child
   returns `needs-answer`.
2. Second line: "Read and follow ~/.config/opencode/agents/<role>.md": the
   installed copy from the canonical checkout, never the copy in the checkout
   under review, so a diff cannot weaken the role that reviews it.
3. Then the task, with absolute paths. A child has no parent history.

## Settings by role

| Role | isolation | interactionMode |
| --- | --- | --- |
| reviewer, advisor, explore | `isolation: "worktree"` | `interactionMode: "plan"` |
| verifier | `isolation: "worktree"` | default: it runs tests, so it is not sent in plan mode |
| implementor | `isolation: "worktree"` | default; the brief follows `implementor-brief` |

A worktree child starts from the parent's last commit; uncommitted edits stay
out. To review an **uncommitted** change, either send the review bundle's
absolute path (`bin/review-bundle . --base <sha> --show AGENTS.md --show
agents/review-deep.md`, and tell the reviewer those base copies govern; a
reviewer may read outside its worktree), or run the
reviewer in your checkout with `isolation: "shared"`. Shared is safe because the
plugin enforces the reviewer's read-only role, but then copy the bundle inside
the checkout and never stage it.

## After it returns

- Rerun an implementor's done check at its returned SHA and read `git status`.
- Record every review and consult with `bin/review-log add` (a blocked run is
  recorded too).
- One re-review, of the fix delta; another round only for a new 🔴 or 🟠.

## Known behaviour (2026-11-23)

- In a full-access T3 thread an opencode ask still reaches the person as an
  approval request (the person approved a `git push` in the Poly thread); in a
  role session the plugin turns it into a deny instead.
- opencode keeps a loaded plugin's code until its server restarts: after a change
  to `plugins/harness-guard.js`, T3 children run the old code (the policy file is
  re-read) until `opencode service restart`. A fresh `opencode run --standalone`
  loads the new code, so test a plugin change there.
