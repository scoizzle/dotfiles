// Enforces policy/permissions.json `roles` in every opencode session, T3
// children included. A T3 child always runs as `build` (delegate_task has no
// agent selector; probe, 2026-11-22), so agent frontmatter cannot limit it. This
// plugin hooks opencode's permission evaluation instead.
//
// A session's role is the first non-blank line of its first user message after
// T3's header line and its `Act as the … sub-agent` line, when it reads
// `role: <name>`. It gets that role's allowlist; any other action is denied. No
// role line: no limit (the person, 2026-11-24: "ENABLE the agents"). An unknown
// role gets the read-only set. The role is stored per session the first time it
// is seen and never relaxed, so a compaction or a restart cannot drop it. In a
// role session an ask becomes a deny: a child returns needs-answer rather than
// waiting on a prompt. Code Mode `execute` is never evaluated as a permission,
// so the role gates it in tool `execute.before`. An implementor session also
// loads a slim prompt (the context hook).
//
// It only tightens: allow can become ask or deny, ask can become deny, never
// the reverse. A configured deny never reaches it.
//
// The default export is a plain { id, setup } so tests can import it without
// the host package; opencode 2 reads only those two fields.
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
    roles[name] = {
      allow: expand(role.allow).map(globToRegExp),
      deny: expand(role.deny).map(globToRegExp),
      context: role.context ?? null,
    }
  }
  return { roles, unknown: spec.unknown_role }
}

function tighten(event, effect, message) {
  if (RANK[effect] > RANK[event.effect]) {
    event.effect = effect
    event.message = message
  }
}

// Slim an implementor's system prompt (2026-11-24): swap the agent prompt, drop
// whole instruction sources, and drop the global AGENTS.md block. Each removal is
// an exact substring, so a layout this does not recognise is left as it is.
function slimSystem(system, context, root) {
  if (!Array.isArray(system) || system.length === 0) return 0
  let dropped = 0
  if (context.prompt && typeof system[0]?.text === "string") {
    const body = readFileSync(join(root, context.prompt), "utf8").split("\n---\n").slice(1).join("\n---\n").trim()
    if (body) {
      dropped += system[0].text.length - body.length
      system[0].text = body
    }
  }
  const globalPath = realpathSync(join(root, "AGENTS.md"))
  for (const part of system) {
    if (typeof part?.text !== "string") continue
    for (const source of part.metadata?.experimental?.instructions ?? []) {
      if (typeof source?.text !== "string") continue
      let cut = []
      if ((context.drop_sources ?? []).includes(source.key)) cut.push(source.text)
      if (context.drop_global_agents && source.key === "core/instructions") {
        const header = `Instructions from: ${globalPath}\n`
        const at = source.text.indexOf(header)
        if (at >= 0) {
          const next = source.text.indexOf("Instructions from: ", at + header.length)
          cut.push(source.text.slice(at, next < 0 ? source.text.length : next))
        }
      }
      for (const text of cut) {
        if (text && part.text.includes(text)) {
          part.text = part.text.replace(text, "")
          dropped += text.length
        }
      }
    }
  }
  return dropped
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
    const policyPath = process.env.HARNESS_POLICY || join(ROOT, "policy", "permissions.json")
    const { roles, unknown } = loadRoles(policyPath)
    const sessions = new Map()
    // A bounded map evicts its oldest entry.
    const remember = (map, key, value) => {
      if (map.size >= 4096) map.delete(map.keys().next().value)
      map.set(key, value)
    }

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
          if (role && !roles[role]) role = unknown
          await ctx.storage.set(`role/${sessionID}`, role)
          return role
        })()
        remember(sessions, sessionID, pending)
        pending.catch(() => sessions.delete(sessionID))
      }
      return sessions.get(sessionID)
    }

    const roleFor = async (sessionID) => {
      const role = await roleOf(sessionID)
      return role && !roles[role] ? unknown : role
    }
    const allows = (role, action) => {
      const spec = roles[role]
      return spec.allow.some((r) => r.test(action)) && !spec.deny.some((r) => r.test(action))
    }
    const refusal = (role, action) =>
      `role ${role}: ${action} is not allowed for this role. This is a boundary, not an obstacle: do not retry it in another form.`

    // An implementor session loads a slim prompt (policy roles.implementor.context);
    // the lead, a reviewer and a role-less child keep the full prompt.
    await ctx.session.hook("context", async (event) => {
      let role
      try {
        role = await roleFor(event.sessionID)
      } catch {
        return
      }
      const context = role ? roles[role]?.context : null
      if (!context) return
      try {
        const dropped = slimSystem(event.system, context, ROOT)
        if (dropped > 0) await ctx.storage.set(`slim/${event.sessionID}`, dropped)
      } catch {
        // A slimming failure leaves the full prompt: it costs tokens, never a rule.
      }
    })

    await ctx.tool.hook("execute.before", async (call) => {
      // Code Mode `execute` is never evaluated as a permission (probe,
      // 2026-11-23), so a role's allowlist gates it here: its fetch would
      // otherwise reach the network from a read-only role.
      if (call.tool !== "execute") return
      let role
      try {
        role = await roleFor(call.sessionID)
      } catch (error) {
        throw new Error(`harness-guard could not read this session's role (${error.message}); denied`)
      }
      if (role && !allows(role, "execute")) throw new Error(refusal(role, "execute"))
    })

    await ctx.permission.hook("evaluate", async (event) => {
      let role
      try {
        role = await roleFor(event.sessionID)
      } catch (error) {
        if (!["read", "grep", "glob"].includes(event.action)) {
          tighten(event, "deny", `harness-guard could not read this session's role (${error.message}); denied`)
        }
        return
      }
      if (!role) return
      if (!allows(role, event.action)) {
        tighten(event, "deny", refusal(role, event.action))
        return
      }
      if (event.effect === "ask") {
        event.effect = "deny"
        event.message = `${event.message ?? "this call needs a person's approval"}. In a role session nobody answers a prompt: return needs-answer with the question instead.`
      }
    })
  },
}
