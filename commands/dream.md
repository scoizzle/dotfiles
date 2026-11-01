---
description: Point at the out-of-band dream pass. Do not rewrite memory mid-task.
---

Do not mine transcripts or rewrite `memory/` during the current task.

When the user asks for a curriculum update, or when the work is a weekend or nightly pass, run:

```sh
~/.config/opencode/bin/dream
```

A dry run prints the proposed append and writes nothing:

```sh
~/.config/opencode/bin/dream --dry-run
```

The script reads the opencode session store and the T3 `grok`/`claudeAgent` threads, then appends to `~/.config/opencode/memory/learnings/YYYY-MM-DD.md`. It does not write `memory/core/`. Flags, sources, cron, and the talk mapping are in `docs/memory-and-dreaming.md`.
