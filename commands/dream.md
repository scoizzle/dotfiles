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

The script reads the opencode session store and the T3 `grok`/`claudeAgent` threads, then stages lines in `~/.config/opencode/memory/learnings/pending/YYYY-MM-DD.md`. Agents do not read pending lines; a person reviews them with `dream --promote`. It does not write `memory/core/`. `dream --promote` also compacts the archive into `learnings/working.md` and still does not write `memory/core/`. The nightly job runs `~/.config/opencode/bin/memory-nightly`, which dreams and then publishes the staged lines to the `memory/dream` branch as a draft PR; promotion stays with `dream --promote`, and a promote needs a second `memory-nightly` run so the archive is published and the pending file drops off the draft before merge. Flags, sources, cron, and the talk mapping are in `docs/memory-and-dreaming.md`.
