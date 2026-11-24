# Security policy

## What this repo is

Personal configuration: opencode agent prompts, a review workflow, an installer
(`install.cs`, `setup.sh`) and a bootstrap (`bootstrap.sh`).
It holds **no credentials**.

Machine-local state is deliberately untracked and gitignored: `service.json`
(a generated password), `cli.json` and `reviews.jsonl`. Those live only in
`~/.config/opencode`.

## Reporting

Use GitHub's **private vulnerability reporting** (Security → Advisories → Report)
for anything sensitive. Please do not open a public issue for it.

## Expected safety properties

- `bootstrap.sh` and `setup.sh` are POSIX `sh`, linted with `shellcheck` and
  syntax-checked with `dash -n` on every push.
- `bootstrap.sh` is safe to pipe: it never relies on `$0` and never reads stdin.
  A clone token is passed in the remote URL only for the clone, then the remote
  is reset to the token-free URL so it is not left in `.git/config`.
- `install.cs` never deletes data. Anything already at a destination is moved to
  `~/.config/opencode.bak-<stamp>/` before being replaced, and symlinks are
  created over it. It removes only links it made into this checkout, and the
  retired `harness-guard` hook in `~/.claude/settings.json` after a backup.
- `--check` on both `bootstrap.sh` and `install.cs` performs no writes.
- Agents run without command, read or edit rules (the person, 2026-11-24:
  "ENABLE the agents"). What remains enforced: opencode's `subagent` tool is
  denied (dispatch is T3), and `plugins/harness-guard.js` keeps a `role:
  reviewer` or `role: advisor` session read-only. `memory/core/` is protected
  by the Memory section of `AGENTS.md`, not by a rule.
- The `dream` skill stages lessons in `memory/learnings/pending/`; a promote,
  on the person's word, appends to `memory/learnings/YYYY-MM-DD.md` and rebuilds
  `working.md`. It never writes `memory/core/` (an instruction, not a rule).
- CI is required to pass before anything lands on `main`.

## Platform scope

macOS and Linux (glibc). Windows is unsupported; use WSL2.
