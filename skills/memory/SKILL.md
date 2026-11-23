---
name: memory
description: Use before heavy work (to read what earlier sessions learned) and when you have a durable lesson to record. Where the bookshelf lives, what to read, and how to append a lesson for a person to promote.
license: MIT
compatibility: opencode
---

# Memory

Durable memory is `~/.config/opencode/memory/`.

## Read, before heavy work

- `INDEX.md` first: a blurb per file. Load a file only when its blurb matches the
  task.
- `learnings/working.md`, the promoted lessons. Read it; never write it.
- Never read `learnings/pending/`: those lines are not yet reviewed.

## Record a lesson

Append to `learnings/pending/YYYY-MM-DD.md` (UTC date), under the version header
in `learnings/README.md`: who, when in UTC, the session or context id, and the
source. One constraint per line, prefixed `never`, `known` or `derived`, with a
`harness`, `loop` or `graph` tag. A person promotes it with `dream --promote`.

## Never

- Edit `memory/core/**`, even by shell redirect (policy `no_edit`).
- Rewrite memory mid-task as a substitute for finishing the work.
