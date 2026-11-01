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
| `memory/learnings/pending/YYYY-MM-DD.md` | staged by dream, unreviewed, not read by agents |
| `memory/learnings/YYYY-MM-DD.md` | promoted lessons, gitignored |
| `~/.config/opencode/bin/dream` | the out-of-band pass |
| `commands/dream.md` | `/dream`, which points at that script |

`./install.cs` symlinks `memory/` to `~/.config/opencode/memory/`. Dated learnings are gitignored, so they sit in the checkout you dreamed in and do not travel with git. A `--copy` install keeps them only under `~/.config/opencode/memory/learnings/`.

`opencode.json` denies `edit` on `memory/core/` (edit, write, and patch). Shell text is matched as a command, not as a path, so `AGENTS.md` is what forbids a redirection into core.

## Sources

T3 launches work that never appears in the opencode store: its native `grok` and `claudeAgent` threads. `bin/dream` reads two stores.

| source | covers |
| --- | --- |
| `opencode.db` | every OpenCode session, including T3 `opencode` threads |
| T3 `statev2.sqlite`, `provider in (grok, claudeAgent)` | the threads no other store records |

The modes are `auto` (default), `t3`, and `opencode`. `auto` reads `opencode.db` plus the T3 `grok` and `claudeAgent` threads, and skips a T3 `opencode` thread only when its native session is already in that read of `opencode.db`. The binding is `payload_json.nativeThreadRef.nativeId` on the T3 thread. Turn items are joined on `provider_thread_id`, not `thread_id`, because two provider rows can share one orchestration thread. `--source t3` reads only the T3 projection, all providers; `--source opencode` is the previous behavior.

The T3 tables are `orchestration_v2_projection_*`: internal, derived, and subject to migration. Dream probes their shape and falls back to opencode-only in `auto`; in `t3` mode a missing or unrecognised store is an error. `statev2.sqlite` is live, so the read is read-only with a busy timeout.

Each run prints a coverage line to stderr:

```text
dream: sources opencode=12 t3=3 (grok=2 claudeAgent=1) t3-opencode-skipped=4 unbound-opencode=0
```

`unbound-opencode` counts opencode sessions in the window with no T3 thread. When T3 is the only launcher it should stay at zero; that is the signal to switch the cron job to `--source t3`. Both stores are per machine, so a linked environment needs its own run.

## Run dream

From a machine that has run `./install.cs`:

```sh
~/.config/opencode/bin/dream
~/.config/opencode/bin/dream --dry-run
~/.config/opencode/bin/dream --since 48h
~/.config/opencode/bin/dream --since 2026-10-30
~/.config/opencode/bin/dream --sessions 10
~/.config/opencode/bin/dream --source t3
```

`--since` defaults to `24h` (`Nh`, `Nd`, `Nm`, or an ISO date interpreted as UTC). `--sessions` caps how many sessions in that window are read (default 50). `--db` overrides the opencode store, `--t3-db` the T3 store, and `--source` picks the modes above. `--dry-run` prints the proposed append and does not write.

The session store is the one `evals/scoreboard.py` opens: `~/.local/share/opencode/opencode.db`, table `session_v2`, messages in `session_message`. The T3 store defaults to `~/.t3/userdata/statev2.sqlite`. A missing store prints that path and appends nothing. It is an empty machine, not a crash.

When there is something to learn, dream drafts with the local `opencode` login. The invocation is:

```sh
opencode run --standalone --format json --agent dream-drafter -m opencode-go/deepseek-v4.1-flash <prompt>
```

`dream-drafter` denies every tool and there is no `--auto`, because the digest quotes tool output and error text that a third party may have written. Before the prompt leaves the machine the digest is redacted for credential shapes and framed as untrusted data; every returned line is length-limited and checked for URLs, fetch-and-run, and injection phrasing. See `docs/security-model.md`.

### Staging and promotion

Dream never writes the files agents read. It stages the block in `memory/learnings/pending/YYYY-MM-DD.md`:

```sh
~/.config/opencode/bin/dream --promote --dry-run   # show what is pending
~/.config/opencode/bin/dream --promote             # show, ask, then append to learnings/YYYY-MM-DD.md
```

`--promote` re-validates every line (so an edited pending file cannot smuggle one in), asks on a terminal, and refuses without `--yes` when there is no terminal. A cron job therefore leaves a review queue, not new instructions.

The model is pinned so a change to the top-level `opencode.json` model cannot move this nightly job onto Claude quota. `--model` or `DREAM_MODEL` overrides it. The prompt is fixed in `bin/dream`. It asks for markdown constraint lines in the learnings format and tells the model not to edit files. The script does not read API keys. If `opencode` is not on `PATH`, dream exits with a short hint and writes nothing. Run it from cron only after `opencode` is installed and logged in on that machine.

A nightly crontab entry, using the installed path:

```cron
15 3 * * * $HOME/.config/opencode/bin/dream
```

## Schedule it in T3

T3 has its own scheduler, and that is what this machine uses instead of cron. The job is a T3 scheduled task in the `dotfiles` project: title `Daily dream pass (memory)`, `03:15` local every day, one new thread per run, with a prompt that runs `~/.config/opencode/bin/dream`, reports the coverage line and where the lines were staged, and stops if `opencode` is missing rather than hand-writing memory. Dream stages in `memory/learnings/pending/`, so the run ends with a review queue: a person runs `dream --promote` before agents see any of it.

It lives in T3's userdata, not in git, so it does not travel with this repo and a linked environment needs its own copy. List it from a session in that project, or open the Scheduled tab in T3.

Pick one scheduler per machine. Cron plus a T3 job means two appends into the same dated pending file, and dream's optimistic-concurrency check will start refusing writes. If T3's scheduler is off for a while, the daily window is `--since 24h`, so the next run only sees the last day; pass `--since` to backfill.

`/dream` is the in-session reminder to use that command later. It is not a step inside T0, T1, or T2 work.
