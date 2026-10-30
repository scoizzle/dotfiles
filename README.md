# dotfiles

My opencode configuration — agents, commands, helper scripts, evals and the
global `AGENTS.md` workflow — tracked so it can be reproduced on another machine.

Managed by `install.cs` (.NET 10 file-based app, executable via shebang).

## Install on a new machine

```sh
git clone <remote> ~/dotfiles
cd ~/dotfiles
./install.cs --check   # show what would change, changes nothing
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

## Adding a file to the repo

1. Copy it in next to its future destination, e.g. `~/dotfiles/.zshrc`.
2. Add its name to the `entries` array at the top of `install.cs`.
3. `./install.cs --check` to confirm the plan, then `./install.cs`.

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

## Known machine-specific bits

- `evals/cases/*/case.json` point at `/Users/scoizzle/Projects/Poly/Poly` for
  their fixture repos. Adjust per machine if Poly lives elsewhere — these are
  eval fixtures, not part of the installed config.
