// Anthropic meters Claude Agent SDK traffic (entrypoint `sdk-ts` / `sdk-cli`)
// against the 5-hour window about 1.8x faster per token than the interactive
// CLI; the weekly limit is unaffected. T3 sets CLAUDE_CODE_ENTRYPOINT=t3-code
// for the Claude processes it spawns, but OpenCode spawns its own and sets no
// label, so its traffic falls into the sdk-* class.
//
// This plugin runs in the OpenCode server process, before any provider request,
// so the Claude Agent SDK inherits a non-sdk label. It only fills an unset or
// sdk-* value: a host that already labels its traffic (T3) keeps its own label.
//
// Scope: this OpenCode process and the Claude sessions it spawns. It does not
// touch an interactive `claude` run started outside this process tree.
const current = process.env.CLAUDE_CODE_ENTRYPOINT
if (!current || current.startsWith("sdk-")) {
  process.env.CLAUDE_CODE_ENTRYPOINT = "opencode"
}

export const ClaudeEntrypoint = async () => ({})
