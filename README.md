# dotfiles

My opencode configuration — agents, commands, helper scripts, evals and the
global `AGENTS.md` workflow — tracked so it can be reproduced on another machine.

Managed by `install.cs` (.NET 10 file-based app, executable via shebang).

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

With the repo already cloned:

```sh
cd ~/dotfiles
./setup.sh             # dotnetup, SDK from global.json, pinned tools
./install.cs --check   # show what the installer would change
./install.cs           # apply
```

`install.cs` symlinks each managed path into `~/.config/opencode`. Symlinks mean
there is exactly one copy of every file — edit it in either location, it's the
same file, and `git status` in this repo shows the change immediately.

Anything already sitting at a destination is **moved** to
`~/.config/opencode.bak-<timestamp>/`, never deleted. Re-running is idempotent.

`./install.cs --copy` copies instead of linking, for machines where symlinks are
a problem. That mode is one-way: edits made in `~/.config/opencode` will not come
back here.

## What this repo manages

| path            | what it is                                        |
| --------------- | ------------------------------------------------- |
| `AGENTS.md`     | global workflow (tiers, review gates, ledger)      |
| `opencode.json` | model, permissions, MCP servers, agent overrides   |
| `agents/`       | subagent prompts                                   |
| `commands/`     | slash commands                                     |
| `skills/`       | `roslynk-rules`: local Roslynk policy for C# work   |
| `bin/`          | `review-bundle`, `review-log`, `smoke-workflow`     |
| `evals/`        | eval harness (`run.sh`, `score.py`, `cases/`)      |

## What it deliberately does not manage

Left in `~/.config/opencode`, untracked, per machine:

- `service.json` — holds a generated password. Never commit this.
- `cli.json` — TUI state (theme, layout, verbosity). Written by opencode itself;
  add it to `entries` in `install.cs` with `--copy` if you want it to travel.
- `reviews.jsonl` — append-only log of review runs.
- `evals/canary-*/` — recorded model output from past eval runs.

Outside `~/.config/opencode`, also untracked on purpose:

- `~/.agents/skills/` — skill directories are owned by the tools that install them.
  The Aspire CLI regenerates its set with `aspire agent init`, and `setup.sh`
  restores Roslynk's from the tag pinned in `tools.json`. Tracking them here would
  only make them drift from the tool that owns them.
- `~/.claude/skills/`, `~/.cursor/`, `~/.copilot/`, `~/.grok/` — harness state, some
  of it credential-bearing.

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

## Platforms

Works on macOS and on Linux (Arch / [Omarchy](https://omarchy.org)). Same
commands everywhere; nothing is per-machine in the tracked files.

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
- Dependabot tracks `global.json` (`dotnet-sdk`) and GitHub Actions. Pinned global
  tools that Dependabot cannot see are checked weekly by `.github/workflows/tools.yml`.
- Security reports: see [`SECURITY.md`](SECURITY.md).

## Known machine-specific bits

- `evals/cases/*/case.json` point at `~/Projects/Poly/Poly` for their fixture
  repos. Adjust per machine if Poly lives elsewhere — these are eval fixtures,
  not part of the installed config. `run.sh` expands a leading `~/` or `$HOME/`.
