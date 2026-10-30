# Security policy

## What this repo is

Personal configuration: opencode agent prompts, a review workflow, an installer
(`install.cs`, `setup.sh`), a bootstrap (`bootstrap.sh`), and an eval harness.
It holds **no credentials**.

Machine-local state is deliberately untracked and gitignored: `service.json`
(a generated password), `cli.json`, `reviews.jsonl`, and generated eval output
under `evals/canary-*/`. Those live only in `~/.config/opencode`.

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
  created over it.
- `--check` on both `bootstrap.sh` and `install.cs` performs no writes.
- CI is required to pass before anything lands on `main`.

## Platform scope

macOS and Linux (glibc). Windows is unsupported; use WSL2.
