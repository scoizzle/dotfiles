# dotfiles

My agent config for Claude Code and opencode, run through T3 Code.

| Path | What |
| --- | --- |
| `AGENTS.md` | The instructions every agent loads. |
| `LESSONS.md` | Rules that cost something to learn, with the evidence and what enforces them. |
| `opencode.json` | The Roslynk MCP server for opencode, plus its default and small models. |
| `claude-settings.json` | The Claude Code model and subagent settings, linked to `~/.claude/settings.json`. |
| `skills/` | Vendored skills, verbatim and pinned: see `skills/UPSTREAM.md`. |
| `bin/agent-headroom` | Pace check to run before fan-out; a non-zero exit means run fewer agents. |
| `install.sh` | Links the above into `~/.config/opencode` and, when Claude Code is installed, `~/.claude`. |

```sh
git clone <remote> ~/dotfiles
~/dotfiles/install.sh --check   # what would change
~/dotfiles/install.sh           # link it
```

Rerun `install.sh` on each machine (Mac and WSL2) after pulling; it makes
`~/.claude/settings.json` a link to `claude-settings.json`, so move personal
settings into that file first.

Anything already at a destination, a link included, is moved to
`~/.config/dotfiles-backup-<stamp>/`, never deleted; only a dangling link into
this repo is removed (an existing `~/.claude/settings.json` is backed up and
replaced by the link). A real directory is the one exception: it is refused,
never moved, and install exits 4 (also under `FORCE=1` or `--check`). Only the
canonical checkout (`$DOTFILES_DIR`, default `~/dotfiles`) may install;
`FORCE=1` overrides that on purpose.

Claude Code does not read `opencode.json`. For Roslynk there, once per machine:

```sh
claude mcp add --scope user roslynk -- ~/.dotnet/tools/roslynk stdio
```

Add something back only when you miss it, and say what happened that made you
miss it. The previous setup is in git history and the `v2-full-2026-11-24` tag.
