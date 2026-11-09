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

The script reads the opencode session store and the T3 `grok`/`claudeAgent` threads, then stages lines in `~/.config/opencode/memory/learnings/pending/YYYY-MM-DD.md`. Agents do not read pending lines; a person reviews them with `dream --promote`. It does not write `memory/core/`. `dream --promote` also compacts the archive into `learnings/working.md` and still does not write `memory/core/`. The nightly job runs `~/.config/opencode/bin/memory-nightly`, which dreams and then publishes the staged lines to a `memory/dream` branch as a draft PR; promotion stays with `dream --promote`, and a promote needs a second `memory-nightly` run so the archive is published and the pending file drops off the draft before merge. Publishing never includes `README.md` or `.gitkeep`, publishes a dated file only as an append to upstream (otherwise skipping it with a warning), and a broken or missing `--dream` blocks it. CI allows `pending/` only while that PR is a draft; a machine-path refusal names its `file:line`, and `--drop-pending YYYY-MM-DD.md` or a hand edit clears it. Use one machine per branch (`--branch memory/dream-<host>` when needed); two machines on one branch overwrite each other. Flags, sources, cron, and the talk mapping are in `docs/memory-and-dreaming.md`.
