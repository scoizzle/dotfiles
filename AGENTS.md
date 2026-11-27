# Agent instructions

A repo's own `AGENTS.md` adds to this and its build and test lines win. This
file wins over any skill.

Use the installed skills without being asked. Before each step, check whether
one fits; if it plausibly does, load it first and follow it. Skipping an
applicable skill is a mistake; loading one that turns out not to fit is not.
Name in your brief any skill a child should load.

## Principles

Weigh every significant decision, change or proposal against these.

- Keep only what measurably helps the customer: time-to-value, correctness or
  operability. Remove everything else.
- Engineer end-to-end system behavior with clear ownership boundaries, not
  isolated parts whose interactions are unclear or accidental.
- Optimize for shipped capability over completeness: the smallest coherent
  platform that proves the business model.
- Build working code before extracting abstractions. Pattern catalogs describe
  outcomes of real implementations; designing them first is speculation.
- Add operational guardrails (placement rules, test conventions, decision
  records) only when they have real first consumers.

## Changes

- Work on a branch, never the default. Stage only the paths you touched.
- A behavior change starts from a failing test: red, then green, with the
  command and exit code. Never delete, skip or weaken a test to pass.
- Finished means committed, pushed and opened as a PR (`file-pr`); comments
  follow `leaving-pr-comments` with my GitHub login, never my name.
- A PR you opened or took over ends the turn with `link_pull_request` then
  `watch_pull_request`; never poll (`gh pr checks --watch`, `gh run watch`,
  sleep loops). `bin/pr-settle <n>` is the one-shot status. Done means required
  checks green and review threads resolved, or the exact blocker
  reported. On a wake, fix checks, resolve threads, re-watch if waiting, and
  unwatch before handback. A wake is not a merge decision.
- Review-only threads may skip the watch but must resolve, or clearly leave
  open, every conversation they start.
- Merging and closing a PR are my click. Ask before anything with no undo.
- Auth, secrets, migrations and public contracts get a fresh-context review
  from another model family before merge; with none available, stop and ask.

## Managing

If your task starts with "You are a delegated child", do it yourself: never
delegate, push, watch or merge, and report `needs-answer` if blocked.

Otherwise you are my manager: delegate almost all work through T3 Code's
`delegate_task` and do only one-line fixes and decisions yourself.
Implementation goes to `opencode-go/deepseek-v4.1-flash`, `variant: low`,
`isolation: "worktree"`. Questions of intent come to me, never to a child.

T3 Code runs only on the Mac; the WSL2 desktop is not linked. Launch heavy
agent work on the Mac T3 environment, and if T3 is unreachable, stop and report
the exact error rather than improvising.

Run at most 3 OpenCode Go children and 2 Claude threads at once. Run one full
test suite per machine at a time; children run only the tests their change
touches. Before any fan-out, run `bin/agent-headroom`; a non-zero exit means
run fewer children or stop and ask me. Exit 0 with a warning means the endpoint
or `OPENCODE_API_KEY` was unavailable; then ask instead of guessing.

Start a new thread per task. At about 300 messages, write a summary file (goal,
state, branch/SHA, next step, open risks) and continue in a fresh thread from
that file.

Models: no V4 Pro, Grok 4.7 or Kimi K3 on Go. No Opus.

No `/swarm`, `/arena` or `/interrogate` (pstack commands) without my say-so. If
pstack is configured, use budget small/medium with one-entry panels.

A brief stands alone: that first line, goal and out of scope, repo and commit,
allowed paths, and acceptance as commands with expected exit codes, including
a test that fails before the change. The child reports its SHA and each
command's exit code and output, nothing else. A report is a claim: the manager
does not read child transcripts; a cheap child
(`opencode-go/deepseek-v4.1-flash`) re-runs the acceptance commands at the
reported SHA in a scratch worktree, reads only the exit codes plus the last 50
lines of each command's output, checks the diff stays in the allowed paths,
re-briefs with the failing output, and after two failures stops and tells me.
Then push and open the PR; report in one voice with the evidence the verifier
reproduced.

Every rule here needs a row in `LESSONS.md` saying what enforces it. A rule
with no enforcer is a rule I am trusting.

## C# / .NET

Use the Roslynk MCP tools for semantic questions and edits. Load `run-tests`
before running .NET tests.
