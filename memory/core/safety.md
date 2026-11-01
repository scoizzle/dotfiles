# Safety

Reinforces Safety in `~/.config/opencode/AGENTS.md`. Agents read this file. They do not edit it.

Do not force-push, `git reset --hard`, `git clean`, `rm -rf`, or `sudo`. Do not read `service.json`, `~/.ssh`, `~/.aws`, or `~/.config/gh`.

Ship-or-ask follows undo cost. Docs, tests, and an isolated change revert in one step. Shared state and auth need cleanup, so name that before writing. Migrations, deletes, and anything that moves money have no undo: a person decides.

On a fix round, return the failed unit and the files in scope. The same failure twice is an escalation.

`memory/core/` stays read-only. `opencode.json` denies `edit` on that tree, which covers the edit, write, and patch tools.
