# dotfiles

My agent config for Claude Code, opencode and Grok, run through T3 Code. It
lives at `~/.agents`, the one place skills and the global `AGENTS.md` are
edited; each tool gets links only where it doesn't read `~/.agents` itself.

| Tool | Skills | `AGENTS.md` |
| --- | --- | --- |
| Claude Code | linked into `~/.claude/skills` | linked as `~/.claude/CLAUDE.md` |
| opencode | linked into `~/.config/opencode/skills` | linked as `~/.config/opencode/AGENTS.md` |
| Grok | reads `~/.agents/skills` | reads `~/.claude/CLAUDE.md` |

| Path | What |
| --- | --- |
| `AGENTS.md` | The instructions every agent loads. |
| `opencode.json` | The Roslynk MCP server for opencode. Models are chosen in each app's own settings. |
| `skills/` | Vendored skills, verbatim and pinned: see `skills/UPSTREAM.md`. |
| `install.sh` | Makes the links in the table above; `~/.claude` only when Claude Code is installed. |

```sh
git clone <remote> ~/.agents
~/.agents/install.sh --check   # what would change
~/.agents/install.sh           # link it
```

Anything already at a destination, a link included, is moved to
`~/.config/dotfiles-backup-<stamp>/`, never deleted; only a dangling link into
this repo is removed. Only the canonical checkout (`$DOTFILES_DIR`, default
`~/.agents`) may install; `FORCE=1` overrides that on purpose.

Claude Code does not read `opencode.json`. For Roslynk there, once per machine:

```sh
claude mcp add --scope user roslynk -- ~/.dotnet/tools/roslynk stdio
```

Add something back only when you miss it, and say what happened that made you
miss it. The previous setup is in git history and the `v2-full-2026-11-24` tag.
