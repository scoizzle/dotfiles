# dotfiles

My agent config for Claude Code and opencode, run through T3 Code.

| Path | What |
| --- | --- |
| `AGENTS.md` | The instructions every agent loads. |
| `opencode.json` | The Roslynk MCP server for opencode. Models are chosen in each app's own settings. |
| `skills/` | Vendored skills, verbatim and pinned: see `skills/UPSTREAM.md`. |
| `install.sh` | Links the above into `~/.config/opencode` and, when Claude Code is installed, `~/.claude`. |

```sh
git clone <remote> ~/dotfiles
~/dotfiles/install.sh --check   # what would change
~/dotfiles/install.sh           # link it
```

Anything already at a destination, a link included, is moved to
`~/.config/dotfiles-backup-<stamp>/`, never deleted; only a dangling link into
this repo is removed. Only the canonical checkout (`$DOTFILES_DIR`, default
`~/dotfiles`) may install; `FORCE=1` overrides that on purpose.

Claude Code does not read `opencode.json`. For Roslynk there, once per machine:

```sh
claude mcp add --scope user roslynk -- ~/.dotnet/tools/roslynk stdio
```

Add something back only when you miss it, and say what happened that made you
miss it. The previous setup is in git history and the `v2-full-2026-11-24` tag.
