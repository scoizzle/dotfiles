---
description: Independent second review from a different model family (T2 changes)
---

Independently review the current uncommitted change.

Bundle: !`~/.config/opencode/bin/review-bundle .`

Contract / scope (may be empty): $ARGUMENTS

Launch `second-opinion` with the bundle directory, the plan/done-when, and the
recorded check command and output. Do not pass the `review-deep` report. Do not
run the build or tests yourself; the parent owns them. If the bundle command
failed because this is not a git repository, say so and use the changed file
list instead.
