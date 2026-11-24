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
docs/rules.md --show agents/review-deep.md`, and tell the reviewer those base copies govern; a
reviewer may read outside its worktree), or run the
reviewer in your checkout with `isolation: "shared"`. Shared is safe because the
plugin enforces the reviewer's read-only role, but then copy the bundle inside
the checkout and never stage it.

## After it returns: supervise, skeptically

The implementor's summary is a claim. Before anything counts:

- Rerun the done check at its returned SHA and read `git status`.
- Read `git diff` against the base, not the summary. Look for edits to tests or
  the oracle, a fix that special-cases the check, a symptom fixed instead of its
  cause, and behaviour the check does not cover that the change breaks.
- A finding you can fix in a line or two, fix yourself. Anything larger, send
  back: one REJECT with the findings and their
  evidence, as a new `delegate_task` to the same role. A second failure on the
  same check is an advisor trigger, then the person.
- Record every review and consult with `bin/review-log add` (a blocked run is
  recorded too).
- A finding blocks only with evidence: a failing test, a line-level
  counterexample, or a broken rule.
- There is one re-review, of the fix delta; another round only for a new 🔴 or 🟠.
- A diff that weakens a rule in `AGENTS.md`, `docs/rules.md` or on a sensitive
  path is a 🔴 for the person, not a finding the reviewer may waive.

## Known behaviour (2026-11-23)

- In a full-access T3 thread an opencode ask still reaches the person as an
  approval request (the person approved a `git push` in the Poly thread); in a
  role session the plugin turns it into a deny instead.
- opencode keeps a loaded plugin's code until its server restarts: after a change
  to `plugins/harness-guard.js`, T3 children run the old code (the policy file is
  re-read) until **T3's own** opencode server (`opencode serve --port=<n>`)
  restarts: `opencode service restart` left it running on old code
  (2026-11-23). Restarting T3 loads the new code (confirmed 2026-11-23: a
  `role: reviewer` probe's Code Mode call was then denied); rerun that probe
  after any plugin change. A fresh `opencode run
  --standalone` loads the new code, so test a plugin change there.
