---
description: Verify the current uncommitted change with the read-only reviewer for its tier
---

Review the current uncommitted change.

Bundle: !`~/.config/opencode/bin/review-bundle .`

Contract / scope (what "done" means; may be empty): $ARGUMENTS

If the change is T1, delegate the `review-light` band; if T2, the `review-deep`
band (`review-critical` on a critical T2) (AGENTS.md, Model routing).
Pass the bundle directory and the check command and output. Do not run the
build or tests yourself; the parent owns them. If the bundle command failed
because this is not a git repository, say so and use the changed file list
instead.
