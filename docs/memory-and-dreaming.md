# Memory and dreaming

Durable memory for this opencode setup, plus an out-of-band pass that turns recent sessions into constraints. The review gates in `AGENTS.md` stay as they are.

## Talk mapping

Lamis Mukta’s “Learning while you Sleep: Beyond Memory to Dreaming” is the source for this layout. The pieces that landed here:

- **Bookshelf.** `memory/INDEX.md` has a one- or two-sentence blurb per file. Agents read the index first and open a file only when the blurb matches the task.
- **Tiers of permission.** `memory/core/` is read-only for agents (conventions and safety). `memory/learnings/` is append-only durable memory. Session transcripts stay in the opencode session store; they are not copied into git.
- **Versioned writes.** Each learnings append starts with who, when (UTC), a session or context id, and a source. `memory/learnings/README.md` is the format.
- **Optimistic concurrency.** `bin/dream` hashes the day’s learnings file before drafting and refuses the append if the file changes twice before the write.
- **Dreaming.** Lessons are written off to the side, after the task, so the task itself is not also a memory edit.

Lessons are constraints, not transcripts. A line is `never:` (dead approach), `known:` (durable fact), or `derived:` (a rule that should change how the next piece of work is cut). The bracket tag says which layer owns it: `harness`, `loop`, or `graph`.

## Where this sits on the ladder

Harness notes often stack the work in levels: memory, then loops and gates, then a learning pass that feeds the next cut. This change is Level 2 memory and Level 7 learning. Loops and gates already live in `AGENTS.md` (tiers, review, the fix cap).

A failure paid for inside a session is written down as a constraint. The next session can load it from the bookshelf, so the same class of failure does not cost a second full pass.

## Layout

| path | role |
| --- | --- |
| `memory/INDEX.md` | bookshelf |
| `memory/core/` | read-only conventions and safety |
| `memory/learnings/README.md` | append format |
| `memory/learnings/YYYY-MM-DD.md` | local lessons, gitignored |
| `~/.config/opencode/bin/dream` | the out-of-band pass |
| `commands/dream.md` | `/dream`, which points at that script |

`./install.cs` symlinks `memory/` to `~/.config/opencode/memory/`. Dated learnings are gitignored, so they sit in the checkout you dreamed in and do not travel with git. A `--copy` install keeps them only under `~/.config/opencode/memory/learnings/`.

`opencode.json` denies `edit` on `memory/core/` (edit, write, and patch). Shell text is matched as a command, not as a path, so `AGENTS.md` is what forbids a redirection into core.

## Run dream

From a machine that has run `./install.cs`:

```sh
~/.config/opencode/bin/dream
~/.config/opencode/bin/dream --dry-run
~/.config/opencode/bin/dream --since 48h
~/.config/opencode/bin/dream --since 2026-10-30
~/.config/opencode/bin/dream --sessions 10
```

`--since` defaults to `24h` (`Nh`, `Nd`, `Nm`, or an ISO date interpreted as UTC). `--sessions` caps how many sessions in that window are read (default 50). `--db` overrides the store. `--dry-run` prints the proposed append and does not write.

The session store is the one `evals/scoreboard.py` opens: `~/.local/share/opencode/opencode.db`, table `session_v2`, messages in `session_message`. A missing store prints that path and appends nothing. It is an empty machine, not a crash.

When there is something to learn, dream drafts with the local `opencode` login. The invocation is:

```sh
opencode run --standalone --format json --auto <prompt>
```

The prompt is fixed in `bin/dream`. It asks for markdown constraint lines in the learnings format and tells the model not to edit files. The script does not read API keys. If `opencode` is not on `PATH`, dream exits with a short hint and writes nothing. Run it from cron only after `opencode` is installed and logged in on that machine.

A nightly crontab entry, using the installed path:

```cron
15 3 * * * $HOME/.config/opencode/bin/dream
```

`/dream` is the in-session reminder to use that command later. It is not a step inside T0, T1, or T2 work.
