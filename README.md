# dotfiles

My opencode configuration — agents, commands, helper scripts, evals and the
global `AGENTS.md` workflow — tracked so it can be reproduced on another machine.

Managed by `install.cs` (.NET 10 file-based app, executable via shebang).

## Workflow

`AGENTS.md` is the contract every harness loads. The default agent does the work.
All dispatch goes through T3 Code's `delegate_task`; opencode's own `subagent`
tool is denied. A broad lookup may go to the explore role. One read-only review is for a
sensitive change (auth, secrets, a schema or data migration, or a public
contract), when you ask, or after the same check has failed twice. Ordinary
edits are not dispatched.

Permissions come from one policy, `policy/permissions.json`, rendered for opencode
by `bin/sync-harness` and checked by `bin/lint-config` in CI. opencode is the one harness; Grok Build and the Claude Code
sandbox profile were dropped in v2 (`docs/v2-plan.md`). The limits of each layer
are in [`docs/security-model.md`](docs/security-model.md).

## Default agent

In opencode, the top-level `build` agent edits. `agents/build.md` is the source;
the tracked `.opencode/agents/build.md` symlink is the project override opencode
loads. `implementor` (`opencode --agent implementor`) is the same job for a
direct `opencode run`: one task, no dispatch. The other agent files are the prompts a T3 brief
names ("Read and follow `agents/<role>.md`"), since a T3 child runs as `build`.

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
same file, and `git status` in this repo shows the change immediately.

Anything already sitting at a destination is **moved** to
`~/.config/opencode.bak-<timestamp>/`, never deleted. Re-running is idempotent.

The links point at the checkout whose `install.cs` ran, so applying is allowed
only from the canonical checkout: `$DOTFILES_DIR` (the same variable
`bootstrap.sh` clones to), default `~/dotfiles`. From any other checkout, a T3
thread's worktree or a scratch clone, it exits 3 and writes nothing, because
every harness would otherwise load its config from that branch until the next
install. `--check` still runs anywhere and warns. To try a branch on purpose,
pass `--from <that checkout>`. It must name the checkout that is running.
`~/dotfiles/install.cs` switches back.

`./install.cs --copy` copies instead of linking, for machines where symlinks are
a problem. That mode is one-way: edits made in `~/.config/opencode` will not come
back here.

## What this repo manages

The repo is the single source for opencode.

| path            | what it is                                        | reaches |
| --------------- | ------------------------------------------------- | ------- |
| `AGENTS.md`     | global workflow, safety, model choice, memory and C# rules | `~/.config/opencode/AGENTS.md` |
| `opencode.json` | model, permissions, MCP servers, agent overrides (permissions are generated) | opencode |
| `agents/`       | agent prompts (opencode format), one primary and the rest subagents; each names its model through a role (`models/roles.json`) | opencode |
| `commands/`     | slash commands | opencode |
| `skills/`       | `roslynk-rules`: local Roslynk policy for C# work; four vendored `dotnet/skills` test skills (see `skills/UPSTREAM.md`) | opencode |
| `plugins/`      | OpenCode plugins loaded at startup; `claude-entrypoint.js` labels OpenCode's Claude Agent SDK traffic so the 5-hour window is metered normally | opencode (`~/.config/opencode/plugins`) |
| `policy/`       | the permission policy and its test vectors | `bin/sync-harness` renders them into `opencode.json`; `bin/lint-config` checks them |
| `memory/`       | bookshelf, read-only core, learnings format         | opencode path, read by absolute path from the others |
| `bin/`          | `review-bundle`, `review-log`, `models`, `dream`, `lint-config`, `harness-guard`, `sync-harness`, `notify-bot` | by absolute path; `notify-bot` also links to `~/.local/bin` |
| `evals/`        | eval harness (`run.sh`, `score.py`, `cases/`)      | |

`install.cs` makes the links and writes each role's model file; `bin/sync-harness
--apply` re-renders `opencode.json` and the verifier block from the policy. Both
are safe to repeat. v2 no longer writes anything into `~/.claude` or `~/.grok`.

How the bookshelf and the out-of-band dream pass fit together is in
[`docs/memory-and-dreaming.md`](docs/memory-and-dreaming.md).

## Bot webhook callbacks

T3 threads and agent jobs can POST a completion callback to a Grok Bot webhook.
Each bot has a URL and a sender key on its routine panel.

```sh
./bin/setup-bot-webhooks --add JARVIS   # name a bot, then prompt for it
./bin/setup-bot-webhooks          # prompt again for the bots you have
./setup.sh --bots                 # opt in during a normal install
./bin/setup-bot-webhooks --check  # what is configured, no prompts
```

The URL prompt is visible; the authorization prompt is hidden. Paste either the
panel's full `Authorization` value (`Bearer …`) or just the key. Enter keeps the
existing value; blank on a first run skips that bot. Your bots are the names in
your own file, so a friend using this repo starts with none; `--add NAME` adds one
(A-Z, 0-9, `_`). `--non-interactive` reads `<NAME>_WEBHOOK_URL` and `_AUTH` from
the environment only for those names, never for any other webhook variable.

Values live outside git in `~/.config/bot-webhooks/env` (mode 0600, directory
0700). `bin/setup-bot-webhooks` writes one managed block into the shell rc files;
it adds `~/.local/bin` to `PATH` and sources the file (the values are exported to
child shells), and a re-run replaces that block instead of appending another. The
file is a `protected.paths` entry in the permission policy, so the agents' read and
shell rules deny it. The URL is treated as a secret too.

```sh
notify-bot JARVIS done "PR #123 merged" <thread-id>
notify-bot --test JARVIS
notify-bot --list                 # configured / not configured; no secrets
```

`install.cs` links the helper to `~/.local/bin/notify-bot`. `notify-bot` reads the
file itself, so it works even when the rc file was not sourced, and it never prints
a URL or header value. It pins the path to the account home from the password
database, not `$HOME`. A failed send exits 1; a bot that is not configured exits 2.
The `AGENTS.md` contract (loaded by all three harnesses) tells a T3 thread to send
the callback when a dispatch names the bot and thread id.

## What it deliberately does not manage

Left in `~/.config/opencode`, untracked, per machine:

- `service.json` — holds a generated password. Never commit this.
- `cli.json` — TUI state (theme, layout, verbosity). Written by opencode itself;
  add it to `entries` in `install.cs` with `--copy` if you want it to travel.
- `reviews/` — one JSON record per review, consult or verifier run, written by
  `bin/review-log`; `review-log summary` flags a gate with no record in 30 days.
- `reviews.jsonl` — the legacy single-file log (to 2026-11-14), read, never rewritten.
- `evals/canary-*/` — recorded model output from past eval runs.

`memory/learnings/*.md`, except `README.md` and `.gitkeep`, is gitignored; that
includes the generated `working.md`, which is local-only like the dated files. With
the default symlink, `bin/dream` writes those files into this checkout: they
are on disk here, and `git clone` does not carry them to another machine. A
`--copy` install keeps them only under `~/.config/opencode/memory/learnings/`.

Outside `~/.config/opencode`, also untracked on purpose:

- `~/.agents/skills/` — skill directories are owned by the tools that install them.
  The Aspire CLI regenerates its set with `aspire agent init`, and `setup.sh`
  restores Roslynk's from the tag pinned in `tools.json`. Tracking them here would
  only make them drift from the tool that owns them.
- `~/.claude/`, `~/.cursor/`, `~/.copilot/`, `~/.grok/` — harness state, some
  of it credential-bearing. `~/.claude` also holds the login the Claude Agent
  integration borrows, so it is never linked or copied. The only managed paths
  outside `~/.config/opencode` are `~/.local/bin/notify-bot`; v2 writes nothing
  into `~/.claude` or `~/.grok`, and links an earlier install left there stay
  ask-protected until you remove them.

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

## Models for your subscription

The repo names roles, never models: `lead`, `implementor`, `reviewer`,
`advisor`, `verifier`, `explore`, `drafter` (`models/roles.json`). A profile in
`models/profiles/` fills every role for one subscription bundle:

| Profile | For | Review |
| --- | --- | --- |
| `claude-go` (default) | a Claude Pro/Max login plus opencode Go | cross-family: Opus reviews DeepSeek |
| `go-only` | opencode Go only | fresh same-model DeepSeek review |
| `claude-only` | a Claude login only | fresh same-model Opus review |

Pick one, and override any role, in an untracked
`~/.config/opencode/models.local.json`:

```json
{"profile": "go-only", "roles": {"explore": "opencode-go/deepseek-v4.1-flash#high"}}
```

`./install.cs` writes one file per role under `~/.config/opencode/models/`,
which `opencode.json` reads through `{file:}`, and `./bin/models check` tells you
if this machine cannot reach a model. A single-family setup reviews with a fresh
same-model reviewer; add `"review": {"single_family": "stop"}` to be asked
instead. No setting can put the reviewer in the implementor's family while your
roles span more than one. Claude reaches opencode through its **Claude Agent**
integration, which borrows the local Claude Code login (`claude auth login`);
`plugins/claude-entrypoint.js` labels that traffic so the 5-hour window is
metered normally.

If you cloned somewhere other than `~/dotfiles`, set `DOTFILES_DIR` to the clone
before the first `./install.cs`.

### Experimental Code Mode (opt-in, not managed)

Claude Code has an experimental Code Mode behind
`CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1`. It is **interactive-terminal only**:
`claude -p` prints that it "isn't available ... only works in the interactive
terminal" and falls back to ordinary tools. T3's native `claudeAgent` sessions
are non-interactive, so treat Code Mode as unavailable there too (probe before
relying on it). It is deliberately **not** rendered into
`~/.claude/settings.json`: Code Mode runs tool calls through a `REPL` tool, which
`harness-guard`'s PreToolUse matcher and the `Read(...)`/`Edit(...)` rules do not
match, so enabling it would take those calls outside the guard and the file
denies. Opt in per session, in a plain terminal, when you accept that:

```sh
CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1 claude
```

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
