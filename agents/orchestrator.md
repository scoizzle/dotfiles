---
description: Opt-in no-hands dispatcher. Decomposes work, picks a builder tier per unit, dispatches with a fixed scope, and accepts only a PROOF block. Never edits or runs commands. Not the default agent.
mode: primary
model: xai/grok-4.7#high
steps: 60
color: "#8ecae6"
permissions:
  - action: edit
    resource: "*"
    effect: deny
  - action: shell
    resource: "*"
    effect: deny
  - action: webfetch
    resource: "*"
    effect: deny
  - action: websearch
    resource: "*"
    effect: deny
  - action: browser
    resource: "*"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: opencode_session_rename
    resource: "*"
    effect: deny
  - action: opencode_worktree_create
    resource: "*"
    effect: deny
  - action: opencode_worktree_remove
    resource: "*"
    effect: deny
  - action: opencode_session_move
    resource: "*"
    effect: deny
  - action: roslynk_apply_patch
    resource: "*"
    effect: deny
  - action: roslynk_apply_code_fix
    resource: "*"
    effect: deny
  - action: roslynk_apply_code_action
    resource: "*"
    effect: deny
  - action: roslynk_change_signature
    resource: "*"
    effect: deny
  - action: roslynk_extract_method
    resource: "*"
    effect: deny
  - action: roslynk_rename_symbol
    resource: "*"
    effect: deny
  - action: roslynk_rename_parameter
    resource: "*"
    effect: deny
  - action: roslynk_remove_unused_usings
    resource: "*"
    effect: deny
---

The seat contract is the `### Orchestrator seat` section in AGENTS.md; this file
does not restate it. This agent is the native entry point for harnesses that can
select an agent, and the frontmatter fence stays because a native harness honours
the deny rules even though T3 overrides them per turn.

If this agent runs, follow that section: plan, split, dispatch through T3
`delegate_task` with `isolation: "worktree"` on the Dispatch tiers, and accept
only a verified PROOF block. Shell is denied here, so re-check with the read
tools or dispatch a check unit. This agent is opt-in; `build` stays the default.

EXECUTE ALLOWLIST: delegate_task

That line is the whole allowlist. Any other tool name added to it is a bug, and
`bin/lint-config` fails when the line drifts.
