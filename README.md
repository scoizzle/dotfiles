# dotfiles

My opencode configuration — agents, commands, helper scripts, evals and the
global `AGENTS.md` workflow — tracked so it can be reproduced on another machine.

Managed by `install.cs` (.NET 10 file-based app, executable via shebang).

## Workflow

`AGENTS.md` classifies each request as T0, T1, or T2 and names the review gate.
Which model runs which job is the **Model routing** table there: every delegated
job goes through T3 with the band's pinned target, so the pin does not depend on
which harness the session runs in. The expensive advisor pin is only for plan-lock,
a repeated error, and T2 sign-off.

Permissions come from one policy, `policy/permissions.json`, rendered for opencode,
Claude Code and Grok Build by `bin/sync-harness` and checked by `bin/lint-config` in
CI. After installing, run `~/.config/opencode/bin/sync-harness` to see what it would
add to `~/.claude/settings.json`, then `--apply`. Grok Build reads that same file:
the rules everywhere, and the `harness-guard` hook in folders it trusts.
One `AGENTS.md` is loaded by all three: `install.cs` also links it as
`~/.claude/CLAUDE.md` and `~/.grok/AGENTS.md`. The limits of each layer are in
[`docs/security-model.md`](docs/security-model.md).

## Orchestrator primary

In opencode, the top-level `build` agent is the orchestrator: it plans, scopes,
and dispatches each unit through T3 `delegate_task` with `isolation: "worktree"`
(checkpoint and integrate units run shared and commit locally), then accepts only a verified `PROOF`. `agents/build.md` is the source; the tracked
`.opencode/agents/build.md` symlink is the project override opencode loads. It does not edit or run mutating shell
itself. `implementor` is the direct-work agent (`opencode --agent implementor`);
delegated units follow the `ROLE: implementor unit | review unit | check unit | checkpoint unit | integrate unit`
branch in `agents/build.md`.

Run the orchestrator in `auto` or `full-access` so children can edit:
`approval-required` pauses each child at its first write or command, and the
orchestrator cannot approve it.
The no-hands rule is the agent prompt, not a T3 fence. Plan mode is a read-only
planning phase and cannot spawn a writable child; use it to explore, then switch
the thread to `build`.

## Install on a new machine

**From a bare box** (no git, no dotnet — just a shell and curl):

```sh
# private repo: one token, used to fetch the script and clone
export GH_TOKEN=<token with repo scope>
sh -c "$(curl -fsSL -H "Authorization: Bearer $GH_TOKEN" \
  https://raw.githubusercontent.com/scoizzle/dotfiles/main/bootstrap.sh)"
```

If the repo is public, drop the token and the header:

```sh
curl -fsSL https://raw.githubusercontent.com/scoizzle/dotfiles/main/bootstrap.sh | sh
```

`bootstrap.sh` installs `git` with the platform package manager, clones to
`~/dotfiles`, then hands to `setup.sh`. It is safe to pipe: it never uses `$0` and
never reads stdin. `--dry-run` and `--no-setup` exist for testing.

### Windows (WSL2)

Windows native is unsupported. `bootstrap-wsl.ps1` is the Windows cold start: it
installs/enables the named distro, caps WSL2 memory once in `%UserProfile%\.wslconfig`
(never overwritten), enables systemd and raises inotify watches in that distro, then
runs `bootstrap.sh` inside it so the clone is `$HOME/dotfiles`. `bootstrap.sh`
remains the Linux/macOS path.

```powershell
powershell -ExecutionPolicy Bypass -File .\bootstrap-wsl.ps1 [-DryRun] [-Distro Ubuntu]
```

Tokens reach the distro through the environment only. T3 belongs in the distro, not
on Windows or behind a `\\wsl$` path. A brand-new distro needs one interactive
`wsl -d Ubuntu` first, to create your Linux user; the script never bootstraps as
root. `wsl --shutdown` is needed once afterwards and is left to you; the script
ends by printing the login commands it does not run.

With the repo already cloned:

```sh
cd ~/dotfiles
./setup.sh             # dotnetup, SDK from global.json, pinned tools
./install.cs --check   # show what the installer would change
./install.cs           # apply
```

`install.cs` symlinks each managed path into `~/.config/opencode`. Symlinks mean
there is exactly one copy of every file — edit it in either location, it's the
same file, and `git status` in this repo shows the change immediately. Memory is
the one exception: it is provisioned as a git clone at
`~/.config/opencode/.memory`, with `~/.config/opencode/memory` symlinked into it.
See [Memory: what travels](#memory-what-travels).

Anything already sitting at a destination is **moved** to
`~/.config/opencode.bak-<timestamp>/`, never deleted. Re-running is idempotent.

`./install.cs --copy` copies instead of linking, for machines where symlinks are
a problem. That mode is one-way: edits made in `~/.config/opencode` will not come
back here. Memory is the same sparse clone and `memory` symlink in either mode.

## What this repo manages

The repo is the single source for three harnesses: opencode, Claude Code, and
Grok Build (which reads `~/.claude` through its Claude compatibility layer).

| path            | what it is                                        | reaches |
| --------------- | ------------------------------------------------- | ------- |
| `AGENTS.md`     | global workflow, routing table, memory and C# rules | all three: `~/.config/opencode/AGENTS.md`, `~/.claude/CLAUDE.md`, `~/.grok/AGENTS.md` |
| `opencode.json` | model, permissions, MCP servers, agent overrides (permissions are generated) | opencode |
| `agents/`       | agent prompts (opencode format), one primary and the rest subagents; the four read-only reviewers are also rendered for Claude Code and Grok | opencode; `~/.claude/agents` |
| `commands/`     | slash commands | opencode; `~/.claude/commands` |
| `skills/`       | `roslynk-rules`: local Roslynk policy for C# work   | opencode; `~/.claude/skills` |
| `plugins/`      | OpenCode plugins loaded at startup; `claude-entrypoint.js` labels OpenCode's Claude Agent SDK traffic so the 5-hour window is metered normally | opencode (`~/.config/opencode/plugins`) |
| `policy/`       | the permission policy, its test vectors, and the T3 provider snapshot the routing table is linted against | permissions reach all three via `bin/sync-harness`; the snapshot is read by `bin/lint-config` |
| `memory/`       | bookshelf, read-only core, learnings format; provisioned as a sparse clone at `~/.config/opencode/.memory`, symlinked as `~/.config/opencode/memory` | opencode path, read by absolute path from the others |
| `bin/`          | `review-bundle` (also `--classify`), `review-log`, `smoke-workflow`, `dream`, `lint-config`, `harness-guard`, `sync-harness` | by absolute path |
| `evals/`        | eval harness (`run.sh`, `score.py`, `cases/`)      | |

`install.cs` makes the links; `bin/sync-harness --apply` writes the parts that
must be merged into files you also edit: `~/.claude/settings.json` (rules and the
`harness-guard` hook, which Grok reads too in folders it trusts), the reviewers under `~/.claude/agents`,
and the Roslynk MCP registration for Claude Code. Grok's own `config.toml` is never
touched. Run `./install.cs` and then `~/.config/opencode/bin/sync-harness` (report)
and `--apply`; both are safe to repeat. Verify what Grok actually loads with
`grok inspect` in a trusted folder.

How the bookshelf and the out-of-band dream pass fit together is in
[`docs/memory-and-dreaming.md`](docs/memory-and-dreaming.md).

### Memory: what travels

`~/.config/opencode/.memory` is a git clone of this repository, sparse to
`memory/` plus `.gitignore`. `~/.config/opencode/memory` is a symlink to
`.memory/memory`, so every path a consumer already used — `memory/INDEX.md`,
`memory/core/`, `memory/learnings/` — keeps resolving. The clone is not the
checkout you edit.

`install.cs` provisions the clone, links `memory` into it, and
`./install.cs --check` verifies it without network: the `origin` URL matches this
repo, the sparse set contains `/memory/`, and the payload and the `memory` symlink
are in place. If `memory` is already a symlink, its raw target is recorded in
`memory.link-target` in the backup and the link is removed; the target is left
untouched. An existing `memory` directory is moved to
`~/.config/opencode.bak-<stamp>/memory/`, and `learnings/**` are copied into the
clone without overwriting, keeping a differing local file under
`learnings/.conflict/`. A `.memory` that is not a clone is moved to
`~/.config/opencode.bak-<stamp>/memory-src/`; its learnings stay there. An
interrupted migration resumes on the next run: the old tree stays in the backup
and the next run finishes the copy. Re-running is idempotent.

The three tiers decide what travels:

- `memory/core/` — curated workflow invariants, portable, edit-denied. It holds
  rules about how work is cut, not model IDs or harness quirks, which go stale on
  another machine.
- `memory/learnings/YYYY-MM-DD.md` — dated and tracked. `bin/memory-nightly`
  publishes the clone's learnings state to the `memory/dream` branch as a draft PR,
  so a clone elsewhere gets them after a person merges. A dated file is published
  only as an append to the upstream copy; otherwise the run skips it with a warning.
  Promote locally, run `memory-nightly` again to publish the archive and drop the
  promoted `pending/` file, then review and merge; merging the first publish leaves
  `pending/` on `main`, which CI rejects.
- `memory/learnings/pending/` and `working.md` — local. `pending/` is force-added
  only on the `memory/dream` branch, and CI exempts it only there while the PR is a
  draft, so an unmerged draft never reaches `main`; `working.md` is rebuilt in each
  working copy by `dream --promote`. The nightly never publishes `README.md` or
  `.gitkeep`, and `--drop-pending YYYY-MM-DD.md` removes a rejected pending file
  from the branch.

Someone who clones this repo gets `memory/INDEX.md`, `memory/core/`, and the dated
learnings that have been promoted and merged. The pending queue and `working.md`
live only on the staging branch and in a working copy. The clone tracks `origin`'s
default branch, not your local `HEAD`; the nightly pushes this machine's learnings
to that origin, so a fork without write access fails the push. Use one machine per
branch — `--branch memory/dream-<host>` when a machine needs its own — because two
machines on one branch overwrite each other's draft. A missing or broken `--dream`
blocks publishing, and a refused machine-path line names its `file:line` for
`--drop-pending` or a hand edit.

## What it deliberately does not manage

Left in `~/.config/opencode`, untracked, per machine:

- `service.json` — holds a generated password. Never commit this.
- `cli.json` — TUI state (theme, layout, verbosity). Written by opencode itself;
  add it to `entries` in `install.cs` with `--copy` if you want it to travel.
- `reviews.jsonl` — append-only log of review runs.
- `evals/canary-*/` — recorded model output from past eval runs.
- `memory/learnings/pending/` and `memory/learnings/working.md` — the review queue
  and the generated working set. Dated `memory/learnings/YYYY-MM-DD.md` files are
  tracked and do travel; `pending/` exists in git only on a `memory/dream` staging
  branch, and CI allows it only while that PR is a draft, and `working.md` is
  rebuilt by `dream --promote` on each machine.

Outside `~/.config/opencode`, also untracked on purpose:

- `~/.agents/skills/` — skill directories are owned by the tools that install them.
  The Aspire CLI regenerates its set with `aspire agent init`, and `setup.sh`
  restores Roslynk's from the tag pinned in `tools.json`. Tracking them here would
  only make them drift from the tool that owns them.
- `~/.claude/`, `~/.cursor/`, `~/.copilot/`, `~/.grok/` — harness state, some
  of it credential-bearing. `~/.claude` also holds the login the Claude Agent
  integration borrows, so it is never linked or copied. The only managed paths
  outside `~/.config/opencode` are `~/.claude/{CLAUDE.md,commands/*.md,skills/*,agents/*.md,settings.json}`
  and `~/.grok/AGENTS.md`; the rest of `~/.claude` (login, projects) and all of
  `~/.grok/config.toml` are never touched. Grok reads the rules and, in a trusted
  folder, the hook from `~/.claude/settings.json` (written by `bin/sync-harness`).

## Adding a file to the repo

1. Copy it in next to its future destination, e.g. `~/dotfiles/.zshrc`.
2. Add its name to the `entries` array at the top of `install.cs`.
3. `./install.cs --check` to confirm the plan, then `./install.cs`.

## Keeping tools current

```sh
./update.sh             # dotnetup, SDK, pinned roslynk, aspire, opencode, t3, rebuild
./update.sh --brew      # also refresh the packages declared in Brewfile
./update.sh --dry-run   # print the plan, change nothing
```

`update.sh` never rewrites a declared version:

- `global.json` is a **floor** and is left alone — `dotnetup update` runs without
  `--update-global-json`, because raising the floor breaks machines whose system SDK is
  older.
- `tools.json` pins are **exact**: roslynk is updated *to the pin*, never to latest.
  New pins arrive as PRs/issues from `.github/workflows/tools.yml`.

Run it from a plain terminal, not from inside opencode or T3 — it replaces the binaries
those processes are running.

## Claude subscription

opencode reaches Claude through its **Claude Agent** integration, which borrows
the local Claude Code login instead of storing an API key. That is the path for
a Claude Pro/Max subscription; the `anthropic` provider is still key-only
(`ANTHROPIC_API_KEY`, or `/connect` → **Anthropic**).

```sh
claude auth login     # once per machine; tokens stay in ~/.claude
```

Then in opencode run `/connect`, select **Claude Agent**, and choose a
`claude-agent/...` model with `/models`. `./install.cs --doctor` reports the CLI
and its login as advisory checks, and `./update.sh` upgrades the CLI when it is
installed.

## Platforms

Works on macOS and on Linux (Arch / [Omarchy](https://omarchy.org)). Same
commands everywhere; nothing is per-machine in the tracked files. Windows is
supported only through WSL2, via `bootstrap-wsl.ps1`.

```sh
./install.cs --doctor   # check prerequisites for this machine
```

`--doctor` verifies the .NET 10 SDK, `python3` (needed by `bin/` and `evals/`),
`git`, `opencode`, the `roslynk` tool, and that `~/.dotnet/tools` is on `PATH`.
It prints the exact fix for the platform it finds.

### First run on Omarchy / Arch

```sh
sudo pacman -S --needed dotnet-sdk python git
dotnet tool install -g roslynk
echo 'export PATH="$PATH:$HOME/.dotnet/tools"' >> ~/.zshrc   # or ~/.bashrc
```

If `pacman`'s `dotnet-sdk` is older than 10, use `dotnet-sdk-bin` from the AUR or
the official `dotnet-install.sh`. File-based apps (`install.cs`) need SDK 10+.

Then `git clone <remote> ~/dotfiles && cd ~/dotfiles && ./install.cs`.

### If `./install.cs` says "A compatible .NET SDK was not found"

`global.json`'s `sdk.version` is a **floor**, not a target: with
`"rollForward": "latestFeature"` it means "any 10.0.x from this feature band upward",
not "exactly this SDK". If the `dotnet` first on `PATH` is older than the floor, every
`dotnet` call in this directory fails — including `install.cs`, whose shebang resolves
`dotnet` from `PATH`.

That is why the floor stays at `10.0.100` rather than tracking the newest installed SDK,
and why `.github/dependabot.yml` has **no** `dotnet-sdk` entry: Dependabot treats the
value as a target and raises the floor, which breaks any machine whose system SDK lags.
SDK currency is `dotnetup update`'s job.

Fix on a machine that hits it: run `./setup.sh` (it puts the dotnetup-managed SDK on
`PATH`), then `./install.cs`.

### Why the config is portable

- `opencode.json` uses `{env:HOME}/.dotnet/tools/roslynk` for the Roslynk MCP
  server rather than a hardcoded path, so the same tracked file resolves
  correctly under `/Users/...` and `/home/...`. (`dotnet tool install -g` puts
  tools in `$HOME/.dotnet/tools` on both.) Verify with `opencode debug config`.
- Everything in `bin/` and `evals/` is Python, except `evals/run.sh` which only
  uses `bash`, `dirname`, and `python3` — no `sed -i ''`, `stat -f`, `pbcopy`, or
  other BSD-only idioms.
- `.gitattributes` forces LF. A CRLF shebang (`#!/usr/bin/env dotnet\r`) makes
  the scripts unrunnable on Linux.
- No filename differs only by case, which macOS tolerates and Linux does not.

## Repository protections

- `main` is protected: pull request required, four required CI checks (shell and
  installer, on Ubuntu and macOS), linear history, no force-push, no deletion.
- Secret scanning and push protection are enabled; Dependabot security updates are on.
- Dependabot tracks GitHub Actions; there is deliberately no `dotnet-sdk` entry
  (`global.json`'s version is a floor, not a target). Pinned global tools that
  Dependabot cannot see are checked weekly by `.github/workflows/tools.yml`.
- Security reports: see [`SECURITY.md`](SECURITY.md).

## Known machine-specific bits

- `evals/cases/*/case.json` point at `~/Projects/Poly/Poly` for their fixture
  repos. Adjust per machine if Poly lives elsewhere — these are eval fixtures,
  not part of the installed config. `run.sh` expands a leading `~/` or `$HOME/`.
