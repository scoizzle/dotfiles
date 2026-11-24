# Memory

Bookshelf. Read this file before heavy work. Open a file below only when its blurb matches the task.

## Core

Agents do not edit these files.

- `core/conventions.md` — Where tiers, evidence, and C# / Roslynk live, in a few lines. The full workflow stays in `AGENTS.md`.
- `core/safety.md` — What stays off limits, and undo cost for ship-versus-ask. Reinforces Safety in `AGENTS.md`.

## Learnings

An agent appends a lesson to `learnings/pending/YYYY-MM-DD.md`; only a promote the person asks for (the `dream` skill) writes the dated files. Lessons are constraints, not transcripts.

- `learnings/README.md` — Version header (who, when UTC, session or context id, source) and the `never` / `known` / `derived` lines, each tagged `harness`, `loop`, or `graph`.
- `learnings/pending/YYYY-MM-DD.md` — Staged by the `dream` skill, or appended by an agent recording a lesson in-session, not yet reviewed. Agents do not read these, except in a promote the person asks for (the `dream` skill).
- `learnings/working.md` — Rebuilt by the `dream` skill's promote from the dated files: duplicates collapsed, each line citing its sources. Read this first when it exists; open any dated file it does not name in its `source:` line. Agents do not write it.
- `learnings/YYYY-MM-DD.md` — The archive, written only by a promote the person asked for. Local constraint lines from earlier sessions. Read the newest of these when the task could repeat a past failure, a bad command, or a wrong path.
