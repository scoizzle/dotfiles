# plugins

OpenCode plugins, loaded at startup from `~/.config/opencode/plugins/` (linked by
`install.cs`). None are installed. `bin/lint-config` checks the OpenCode 2 shape
of any `*.js` added here: a default export with an id and a setup or effect.

`claude-entrypoint.js` lived here until v2. It relabelled the Claude Agent SDK
traffic that opencode spawned. Claude now runs in Claude Code, not opencode (see
Harness topology in `docs/v2-plan.md`), so that traffic and the plugin are gone.
