# pstack, pinned

[poteto's pstack](https://github.com/cursor/plugins/tree/main/pstack) is a skill
pack of 58 skills. This repo installs **19 of them** — the ones it actually reaches
for — from a pinned commit, with a per-role model rule. This directory is the
repo's half of it: the pin, the subset, the model rule, and the reason the install
is a fetch.

## What is pinned, and where

`tools.json` → `skills.pstack` holds the version and the `cursor/plugins` commit.
`bin/sync-pstack` installs that commit into `~/.agents/pstack/<version>/` and links
each skill into `~/.agents/skills/` and `~/.claude/skills/`.

| | |
| --- | --- |
| version | `0.15.46` |
| commit | `0b46ec399d55f2829e88822998f53b84944837d3` |
| upstream path | `pstack/` in `github.com/cursor/plugins` |

```sh
./bin/sync-pstack              # report drift (exit 1 if any); changes nothing
./bin/sync-pstack --apply      # fetch the pin, link the skills, render the rules
./setup.sh                     # also does this, after install.cs and the pinned tools
./update.sh                    # also does this, and re-fetches only when the pin moved
```

`--apply` is safe to repeat: when the installed tree already matches the pin it
repairs links and never touches the network. A skill directory this tool did not
create is reported as a collision and left alone. It also places the two home rule
links, which `install.cs` places too — either command leaves them in place, and a
real file sitting on one of those paths is refused rather than overwritten
(`install.cs` moves it to a backup first, which is why `setup.sh` and `update.sh`
run this step *after* `install.cs`). A link into an older pstack tree is removed,
and so is that tree once nothing points at it — but only what this tool wrote: every
tree it fetches is stamped with `.dotfiles-pstack`, and a checkout you put under
`~/.agents/pstack/`, and the links you made into it, are kept with a note.
`--check` converges.

## What is installed

`pstack/skills.txt` is the list. The whole tree is fetched either way, so adding a
skill back is a line there and `bin/sync-pstack --apply`; `--check` reports a link
for a name that is not listed, and fails on a name the pinned tree does not have.

| | |
| --- | --- |
| panels and review | `arena`, `interrogate`, `blast-radius` |
| code explainers | `how`, `why` |
| prose and precision | `sharpen`, `unslop`, `in-your-own-words` |
| repo hygiene | `correct` (turn a repeated agent mistake into architecture, a type, or a lint whose error names the fix) |
| measurement | `benchmark-checklist` |
| lenses | `principle-boundary-discipline`, `-encode-lessons-in-structure`, `-explain-the-number`, `-fix-root-causes`, `-guard-the-context-window`, `-make-operations-idempotent`, `-prove-it-works`, `-sequence-verifiable-units`, `-subtract-before-you-add` |

Deliberately **not** installed:

- `poteto-mode` and the skills it orchestrates (`swarm`, `tdd`, `poteto-help`,
  `reflect`). This harness has its own workflow and did not adopt pstack's dispatch
  model; a mode whose playbooks call missing skills is worse than no mode. One
  consequence: `arena` points at `poteto-mode`'s Subagents section for reasoning
  levels, so that one sentence loses its target — arena's own defaults still apply.
- `recall`, `ketchup`, `ketchup-video`, `bro` — they read Cursor's history.
- the `create-`/`maintain-verification-skill` generators and `statechart` — they
  build project-local verification, which targets an app repo, not this one.
- `typescript-best-practices` — wrong stack.
- `setup-pstack` — it would write `~/.cursor/rules/pstack-models.mdc`, the file this
  repo owns. Not installing it means no skill can quietly replace the rule.

## Why a fetch, and not the plugin installers

All four harnesses can install plugins, and pstack is published as one. Only one
of them can pin it:

| harness | plugin command | pins to a commit? | skills land in |
| --- | --- | --- | --- |
| Grok Build | `grok plugin install cursor/plugins@<sha>#pstack` | **yes** (`@ref#subdir`) | `~/.grok/plugins` |
| Claude Code | `claude plugin marketplace add cursor/plugins` + `install pstack@cursor-plugins` | no: `.claude-plugin/marketplace.json` carries no version or ref, so it is whatever the catalog held | `~/.claude/plugins` |
| Cursor | `/add-plugin pstack` | no CLI at all; GUI only | `~/.cursor/plugins/cache` |
| opencode | `opencode plugin add <package>` | its registry holds JS hook packages (`@opencode-ai/plugin`); pstack is not one, and plugins carry no skills | n/a |

Using each harness's installer would leave two or three trees at different
versions, which is the drift the pin exists to prevent. One fetched tree also
keeps pstack's own relative links (`../<skill>/SKILL.md`, and `../../docs/guide`
in `poteto-help`) working: the skills are symlinks into the whole tree, so those
paths resolve against the tree, not against a flattened copy.

Cursor and opencode both auto-discover `~/.agents/skills/`; Claude Code reads
`~/.claude/skills/`. Grok Build reads `~/.claude/skills/` through its Claude
compatibility layer, so it gets the same set for free.

If the Cursor marketplace plugin is also installed, Cursor sees two copies — at the
same commit or not, which one wins is undefined. `bin/sync-pstack` reports any
installed copy as drift; remove the plugin in Cursor (Settings → Plugins) so only
the pinned copy remains.

## The model rule

pstack's `/setup-pstack` writes `~/.cursor/rules/pstack-models.mdc` from what it
detects in the session. Here that file is owned by `pstack/models.json` and
rendered three ways, because each harness names models differently:

| file | read by | value shape |
| --- | --- | --- |
| `pstack/cursor/pstack-models.mdc` | Cursor (`~/.cursor/rules/`) | Cursor slugs, which are pstack's defaults |
| `pstack/claude/pstack-models.md` | Claude Code (`~/.claude/rules/`) | `opus xhigh`, `fable high`, `inherit-parent` |
| `pstack/opencode/pstack-models.md` | opencode, through `instructions` in `opencode.json` | `provider/model#variant`, or `inherit-parent` |

Edit `models.json`, then `./bin/sync-pstack --apply`. `tests/pstack.py` fails when
a render drifts, and `bin/sync-pstack --check` fails when the pinned `setup-pstack`
names a role the JSON does not have (or the reverse).

`models.json` also carries a `routes` table: every opencode route a role may name,
with the effort variants that route accepts. `--check` compares the routes a role
actually uses to `opencode models` when opencode is on PATH, so a route that
disappears or a misspelled provider is reported instead of being dispatched and
rejected; a declared route no role uses is a note, never drift. The effort variants
are hand-maintained — `opencode models` prints bare routes — and
`tests/pstack.py` validates every role value against the table.

### What maps to what

| pstack role | Cursor | Claude Code | opencode |
| --- | --- | --- | --- |
| `feature, refactoring`, `bug-fix`, `perf-issue`, `hillclimb` | `claude-opus-5-5-xhigh-fast` | `opus xhigh` | `opencode-go/deepseek-v4.1-flash#high` |
| `judgment and prose` | `claude-opus-5-5-xhigh-fast` | `opus xhigh` | `claude-agent/opus#xhigh` |
| `swarm workers` | `claude-opus-5-5-xhigh-fast` | `opus xhigh` | `opencode-go/deepseek-v4.1-flash#high` |
| `arena runners`, `interrogate reviewers` | `claude-fable-5-2-high`, `claude-opus-5-5-high-fast`, `gemini-4-neon-xhigh` | `fable high`, `opus high`, `inherit-parent` | `claude-agent/fable#high`, `claude-agent/opus#high`, `opencode/gemini-4-neon#xhigh` |
| `arena cross-judge pool` | `claude-opus-5-5-high-fast`, `gemini-4-neon-xhigh` | `opus high`, `inherit-parent` | `claude-agent/opus#high`, `opencode/gemini-4-neon#xhigh` |

The role table keeps upstream's full step-5 shape (nine labels). With
`poteto-mode` not installed, only the three panel rows are read today; the code and
judgment rows stay so a pin bump stays comparable and adding the mode back is one
line in `skills.txt`.

Three deliberate deviations from pstack's 0.15.46 defaults, all recorded in
`models.json`:

- **Code delegates and swarm workers run on the repo writer, not Opus.** Upstream
  defaults every role to Opus 5.5. The evals gate decision in
  [`evals/2026-10-18-gate-model-decision.md`](../evals/2026-10-18-gate-model-decision.md)
  keeps volume work on `opencode-go/deepseek-v4.1-flash` and spends Opus on
  review, and a swarm is ten workers on the same Claude subscription window the
  Claude Agent integration borrows.
- **`inherit-parent` where the model is not available.** Gemini 4 Neon has no
  Claude Code equivalent, so that seat runs on the session model instead of a
  slug the `Agent` tool would reject.
- **`-fast` is dropped.** It is a Cursor serving mode; opencode's only axis is
  effort.

## Known gaps

- Most pstack skills set `disable-model-invocation: true`, a Cursor/Claude gate
  meaning "only the user invokes this". opencode ignores the field, so all the
  skills are model-invocable there. `AGENTS.md` still wins over a skill, and
  `policy/permissions.json` → `opencode.skill_deny` is the lever if a skill should
  be off entirely.
- The skills read their model rule from the literal `~/.cursor/rules/pstack-models.mdc`,
  which opencode denies reading (`policy/permissions.json` → `read_deny_extra`). The
  opencode render says so and carries the values, but a skill that never looks in
  its context falls back to its own default — Opus 5.5 xhigh, which is not an
  opencode slug. `models.json` is the value of record; if a pstack run reports a
  rejected slug, this is why.
- `pstack/agents/` (`poteto-agent`, `comment-sicko`) and `pstack/automations/`
  (`benny`) are fetched but not installed: they are Cursor-format subagents and
  Cursor automations, and this repo renders its own agents. A pstack step that
  names those agents falls back to the session model.
- On Windows, Cursor reads `%USERPROFILE%\.cursor`, not WSL's `~/.agents/skills`,
  so the Cursor half of this does nothing there. Windows is supported only through
  WSL2 anyway.

## Updating the pin

A pin bump is a reviewed change, like `tools.json`'s roslynk entry:

1. Pick the commit in `cursor/plugins` that carries the new `pstack/plugin.json`
   version (`gh api 'repos/cursor/plugins/commits?path=pstack/plugin.json'`).
2. Update `skills.pstack` in `tools.json`.
3. `./bin/sync-pstack --apply`, then `./bin/sync-pstack`: a renamed role shows up
   as drift against `models.json`, and a new skill shows up in `~/.agents/skills`.
4. Run `python3 tests/pstack.py`.
