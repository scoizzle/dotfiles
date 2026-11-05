# Security model

What this setup enforces, what it only discourages, and what would make it a real
boundary. Written against `opencode.json`, `agents/`, and `bin/dream`.

## Threat model

The agents read text they do not control: web pages, repository files, tool
output, error messages, and earlier session transcripts. Any of it can carry
instructions (prompt injection). The harm to prevent is that text becoming an
action (push, delete, read a credential) or becoming persistent (a line in memory
that every later session trusts).

## What is enforced

| Control | Where | Strength |
| --- | --- | --- |
| Reviewers and the dream drafter have no `edit`, `shell`, `subagent`, or `webfetch` | `agents/*.md` | Tool-level. Not reachable by text. |
| `memory/core/` is edit-denied for every agent | `opencode.json` | Tool-level for the edit tools. |
| `git push` is `ask`; force, delete, mirror, and `+refspec` pushes are `deny` in any argument position | `opencode.json` | Pattern match on the command line. |
| `dream` drafts with `dream-drafter` (no tools) and without `--auto` | `bin/dream`, `agents/dream-drafter.md` | Tool-level. |
| The digest is redacted, framed as untrusted, and every returned line is validated | `bin/dream` | Heuristic. Drops, does not repair. |
| Drafted lessons are staged in `memory/learnings/pending/` and reach agents only through `dream --promote`, which needs a person | `bin/dream` | Human gate. |

`bin/lint-config` runs in CI and evaluates concrete commands and paths against each
agent's effective rules. It exists because a rule order bug is invisible by reading:
the `verifier`'s `shell *: allow` used to erase every global shell deny.

## One policy, three harnesses

`policy/permissions.json` is the single source. `policy/vectors.json` holds the
expected decision for each sample command and path. `bin/lint-config` runs those
vectors through every engine in CI, so the three cannot disagree unnoticed.

| Harness | Rules | Hook (`harness-guard`) | Source of truth for the harness |
| --- | --- | --- | --- |
| opencode | `opencode.json` `permissions` and the `verifier` block, rendered by `bin/sync-harness` | none; text globs only | `opencode.json` |
| Claude Code | `permissions.deny/ask` from `~/.claude/settings.json` | `PreToolUse` hook from `~/.claude/settings.json` | `~/.claude/settings.json` |
| Grok Build | the same `permissions.deny/ask`, read from `~/.claude/settings.json` (verified with `grok inspect`: `permissions.loaded` counted them, even in an untrusted folder) | the same `PreToolUse` hook, **only in a trusted folder** (verified with `grok inspect`: `hooks: []` untrusted; after `trusted_folders.toml` marks the folder, the hook appears with `vendor: claude`, `compatibilityStatus: enabled`) | `~/.claude/settings.json` |

`~/.grok/config.toml` is never touched; it holds an MCP bearer token. Grok's
trust gate matters in practice: only folders listed in `~/.grok/trusted_folders.toml`
run global hooks, and each T3 worktree is a separate checkout. In an untrusted
folder Grok still enforces the rules, and `ask` still forces a prompt in
always-approve mode, but the hook (and so its parsing) is skipped. Trusting a
folder is a person's decision (`/hooks-trust`, or `grok --trust`).

Optional hardening: `/Library/Application Support/ClaudeCode/managed-settings.json`
is root-owned, read by both harnesses (`grok inspect` reports the path), applies in
every folder, and cannot be overridden by user or project settings.
`bin/sync-harness --scope managed` prints the rules for it and the `sudo` command a
person runs; it writes nothing and never uses sudo. It carries rules, not the hook.

Grok's sandbox is CLI-only (`--sandbox workspace|read-only|strict`, profiles in
`~/.grok/sandbox.toml`); no config key makes it the default.

`harness-guard` parses the command (quoting, `&&`/`;`/pipes, `$(...)`, `sh -c`,
`env`/`command` wrappers, `git -C x push`, clustered flags like `-fu`, heredoc
bodies), which text globs cannot. It denies with exit 2 and a reason, asks with a
JSON `ask`, and never prints `allow`. Both harnesses fail open when a hook
crashes, so the guard denies on any error and on truncated input.

Apply it with `~/.config/opencode/bin/sync-harness` (report drift) and
`--apply` (write; the settings file is backed up first, existing rules and hooks
are kept, and retired rules are not removed automatically).

Limits specific to this layer:

- A hook missing from disk fails open in Claude Code and Grok. The native deny
  rules are the fallback, and `bin/lint-config` checks they cover the denied
  commands that globs can express.
- Decode-to-shell (`base64 -d x | sh`, `xxd -r`, `openssl enc -d`, also inside
  `sh -c`) is denied and `curl | sh` asks, by `harness-guard` only. opencode and
  Grok in an untrusted folder do not get that parsing. `find -delete` and
  `xargs rm -rf` are covered by both globs and the hook. Nothing understands
  `python -c`, decoding done by other tools, or paths built at run time. A
  script supplied as a literal is analysed when it comes from `echo`/`printf`, a
  heredoc, or a here-string; any other producer (`cat file | sh`, a script
  written by an earlier command) is not, because the guard cannot know what it
  emits.
- The guard hook is a convenience layer in a file the user owns
  (`~/.claude/settings.json`) and can edit out. Enforcement needs the root-owned
  file above, which carries rules, not the hook.
- Instructions are shared: `install.cs` links `~/.claude/CLAUDE.md` and
  `~/.grok/AGENTS.md` to `AGENTS.md`. Grok Build does not cap the file
  (verified 2026-11-05).

## What is only discouraged

Shell command denies are **text patterns, not a boundary**. `rm -rf` has dozens of
spellings, `python -c` does the same job, and a base64 payload decoded by another tool
matches nothing. The patterns in `opencode.json` raise the cost of an accident and
of a lazy injection. They do not stop a determined one. `memory/core/safety.md`
says the same.

Likewise the `verifier` has an unsandboxed shell. "Does not edit the repository"
is an instruction it follows, backed by the disposable-clone procedure in its
prompt, not a permission that holds.

`--auto` approves every `ask`. A session started with it can push. Do not start
unattended sessions with `--auto`.

## Known limits of the checks

- `lint-config` assumes last-match-wins rule order, which the schema does not
  state. If opencode changes that, the lint passes against the wrong model.
  Confirm it once against a real denied command after an opencode upgrade.
- The redaction patterns cover common credential shapes, not every secret.
- The line validator is a denylist of payload shapes; a well-phrased false lesson
  passes it. The human gate is the control that holds.

## To make it a real boundary

Best practice across the frontier labs is the same three moves:

1. **Sandbox the executor.** Run agents with shell in a container or VM with no
   host credentials mounted, a read-only home, an allowlisted network, and a
   writable bind mount of the working tree only. Denylists then become a second
   layer, not the only one.
2. **Give credentials per task, not per machine.** A short-lived, repo-scoped
   token injected for one run beats `~/.config/gh` being readable and denied.
3. **Keep a human on irreversible and persistent actions.** Pushes, deletes, and
   writes to memory that later sessions trust stay `ask` or staged.

None of these needs a code change here; they are how the sessions are launched.
