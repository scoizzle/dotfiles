---
description: Ask the read-only reviewer to check the current change
---

Review the current uncommitted change.

Bundle: !`~/.config/opencode/bin/review-bundle .`

Contract / scope (what "done" means; may be empty): $ARGUMENTS

Send the bundle directory, the contract, and the recorded check command and output
to the `review-deep` reviewer (`agents/review-deep.md`). It is read-only: it does
not edit and does not rebuild. If the bundle command failed because this is not a
git repository, say so and use the changed file list instead.
