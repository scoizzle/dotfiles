// Enforces policy/permissions.json in every opencode session, T3 children
// included. A T3 child always runs as `build` (delegate_task has no agent
// selector; probe, 2026-11-22), so agent frontmatter cannot limit it. This
// plugin hooks opencode's permission evaluation instead:
//
// - shell and edit calls go through bin/harness-guard, which parses what the
//   text globs in opencode.json cannot (heredocs, `sh -c`, git global options,
//   decode-to-shell). A crash, a timeout or a missing guard denies. opencode
//   evaluates a shell permission per segment, with `cd` dropped (probe,
//   2026-11-22), so shell is checked whole in tool `execute.before`, which runs
//   first: a deny throws there, an ask is held for that call's evaluation.
// - a session's role is the first non-blank line of its first user message
//   after T3's header line and its `Act as the … sub-agent` line, when it reads
//   `role: <name>`. It gets that role's allowlist
//   from policy/permissions.json `roles`; any other action is denied. A T3 child
//   with no role line, or an unknown role, gets the read-only set. The role is
//   stored per session the first time it is seen and never relaxed, so a
//   compaction or a restart cannot drop it. In a role session an ask becomes a
//   deny: a child returns needs-answer rather than waiting on a prompt.
//
// It only tightens: allow can become ask or deny, ask can become deny, never
// the reverse. A configured deny never reaches it. Reads are left to the
// opencode rules, which already cover the protected paths. Code Mode `execute`
// is not evaluated itself (only the tools it calls), so its `fetch` is a gap.
//
// The default export is a plain { id, setup } so tests can import it without
// the host package; opencode 2 reads only those two fields.
import { spawn } from "node:child_process"
import { readFileSync, realpathSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = dirname(dirname(realpathSync(fileURLToPath(import.meta.url))))
const RANK = { allow: 0, ask: 1, deny: 2 }
const ROLE_LINE = /^role:\s*([a-z][a-z-]*)\s*$/i
const T3_HEADER = "[T3 Code: the agent in T3 thread"
// T3 adds this line after its header when delegate_task sets `role` (seen 2026-11-22).
const T3_PREAMBLE = /^Act as the [\w -]+ sub-agent for this task\.$/

function globToRegExp(glob) {
  return new RegExp("^" + glob.split("*").map((s) => s.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$")
}

function loadRoles(policyPath) {
  const spec = JSON.parse(readFileSync(policyPath, "utf8")).roles
  const expand = (list) => (list ?? []).flatMap((g) => (g.startsWith("@") ? spec[g.slice(1)] : [g]))
  const roles = {}
  for (const [name, role] of Object.entries(spec.roles)) {
    roles[name] = { allow: expand(role.allow).map(globToRegExp), deny: expand(role.deny).map(globToRegExp) }
  }
  return { roles, unknown: spec.unknown_role, childDefault: spec.child_default }
}

function tighten(event, effect, message) {
  if (RANK[effect] > RANK[event.effect]) {
    event.effect = effect
    event.message = message
  }
}

function runGuard(bin, payload, timeoutMs) {
  return new Promise((resolve) => {
    let out = ""
    let err = ""
    let done = false
    const finish = (result) => {
      if (!done) {
        done = true
        clearTimeout(timer)
        resolve(result)
      }
    }
    let child
    try {
      child = spawn(bin, [], { stdio: ["pipe", "pipe", "pipe"] })
    } catch (error) {
      return finish({ effect: "deny", message: `harness-guard could not start (${error.message}); denied. It needs python3; to run without it, remove ~/.config/opencode/plugins/harness-guard.js` })
    }
    const timer = setTimeout(() => {
      child.kill("SIGKILL")
      finish({ effect: "deny", message: `harness-guard timed out after ${timeoutMs} ms; denied` })
    }, timeoutMs)
    child.stdout.on("data", (d) => (out += d))
    child.stderr.on("data", (d) => (err += d))
    child.on("error", (error) => finish({ effect: "deny", message: `harness-guard could not start (${error.message}); denied. It needs python3; to run without it, remove ~/.config/opencode/plugins/harness-guard.js` }))
    child.on("close", (code) => {
      let reply = null
      try {
        reply = out.trim() ? JSON.parse(out.trim().split("\n").pop()).hookSpecificOutput : null
      } catch {
        return finish({ effect: "deny", message: `harness-guard printed something that is not its JSON reply; denied` })
      }
      const reason = reply?.permissionDecisionReason
      if (code === 2) return finish({ effect: "deny", message: reason || err.trim() || "harness-guard denied this call" })
      if (code !== 0) return finish({ effect: "deny", message: `harness-guard failed (exit ${code}: ${err.trim().slice(-200)}); denied` })
      if (reply?.permissionDecision === "deny") return finish({ effect: "deny", message: reason })
      if (reply?.permissionDecision === "ask") return finish({ effect: "ask", message: reason })
      finish(null)
    })
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(payload))
  })
}

function firstUserText(messages) {
  const first = (messages ?? []).find((m) => m?.type === "user" || m?.role === "user")
  if (!first) return ""
  if (typeof first.text === "string") return first.text
  return (first.parts ?? []).map((p) => (typeof p?.text === "string" ? p.text : "")).join("\n")
}

export default {
  id: "harness-guard",
  async setup(ctx) {
    const bin = process.env.HARNESS_GUARD_BIN || join(ROOT, "bin", "harness-guard")
    const policyPath = process.env.HARNESS_POLICY || join(ROOT, "policy", "permissions.json")
    const timeoutMs = Number(process.env.HARNESS_GUARD_TIMEOUT_MS) || 5000
    const { roles, unknown, childDefault } = loadRoles(policyPath)
    const sessions = new Map()

    const roleOf = (sessionID) => {
      if (!sessions.has(sessionID)) {
        const pending = (async () => {
          const stored = await ctx.storage.get(`role/${sessionID}`)
          if (typeof stored === "string") return stored
          const text = firstUserText(await ctx.session.context({ sessionID }))
          // The role is the first non-blank line after T3's header line (or of
          // the message, outside T3), so a role line quoted later cannot count.
          const at = text.indexOf(T3_HEADER)
          const body = at < 0 ? text : text.slice(text.indexOf("\n", at) + 1 || text.length)
          const line = body.split("\n").map((l) => l.trim()).find((l) => l !== "" && !T3_PREAMBLE.test(l)) ?? ""
          let role = ROLE_LINE.test(line) ? ROLE_LINE.exec(line)[1].toLowerCase() : ""
          if (!role && at >= 0) role = childDefault
          if (role && !roles[role]) role = unknown
          await ctx.storage.set(`role/${sessionID}`, role)
          return role
        })()
        sessions.set(sessionID, pending)
        pending.catch(() => sessions.delete(sessionID))
      }
      return sessions.get(sessionID)
    }

    const cwdOf = async (sessionID) => {
      const session = await ctx.session.get({ sessionID }).catch(() => null)
      return session?.directory ?? session?.location?.directory ?? ctx.location?.directory ?? process.cwd()
    }

    const pendingAsk = new Map()
    const seenShell = new Set()
    await ctx.tool.hook("execute.before", async (call) => {
      if (call.tool !== "shell" || typeof call.input?.command !== "string") return
      seenShell.add(call.id)
      const verdict = await runGuard(bin, { tool_name: "Bash", tool_input: { command: call.input.command }, cwd: await cwdOf(call.sessionID) }, timeoutMs)
      if (verdict?.effect === "deny") throw new Error(verdict.message)
      if (verdict?.effect === "ask") pendingAsk.set(call.id, verdict.message)
    })

    await ctx.permission.hook("evaluate", async (event) => {
      if (event.action === "shell" && event.source?.id && pendingAsk.has(event.source.id)) {
        tighten(event, "ask", pendingAsk.get(event.source.id))
        pendingAsk.delete(event.source.id)
      }
      let role
      try {
        role = await roleOf(event.sessionID)
      } catch (error) {
        if (!["read", "grep", "glob"].includes(event.action)) {
          tighten(event, "deny", `harness-guard could not read this session's role (${error.message}); denied`)
        }
        return
      }
      if (role) {
        const spec = roles[role]
        const allowed = spec.allow.some((r) => r.test(event.action)) && !spec.deny.some((r) => r.test(event.action))
        if (!allowed) {
          tighten(event, "deny", `role ${role}: ${event.action} is not allowed for this role. This is a boundary, not an obstacle: do not retry it in another form.`)
          return
        }
      }
      // A shell call execute.before never saw (another tool reaching shell)
      // still goes through the guard, per segment, as defense in depth.
      const unseenShell = event.action === "shell" && !seenShell.delete(event.source?.id)
      if (event.action === "edit" || unseenShell) {
        const cwd = await cwdOf(event.sessionID)
        for (const target of (event.resources ?? []).map(String)) {
          const payload =
            event.action === "shell"
              ? { tool_name: "Bash", tool_input: { command: target }, cwd }
              : { tool_name: "Edit", tool_input: { file_path: target }, cwd }
          const verdict = await runGuard(bin, payload, timeoutMs)
          if (verdict) tighten(event, verdict.effect, verdict.message)
          if (event.effect === "deny") break
        }
      }
      if (role && event.effect === "ask") {
        event.effect = "deny"
        event.message = `${event.message ?? "this call needs a person's approval"}. In a role session nobody answers a prompt: return needs-answer with the question instead.`
      }
    })
  },
}
