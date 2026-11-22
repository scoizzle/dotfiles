# dotfiles v2 plan

Status: proposal. Nothing here is implemented. Every phase below touches a
sensitive path, so each lands as its own reviewed PR.

## Why a v2

v1 works, but it grew in the wrong places:

- **Rules pile up and nothing removes them.** Of the eight workflow PRs since #39,
  only one came from an incident. `AGENTS.md` grew from 85 lines at import to
  11,835 characters. The 10,000-character cap came off in #23 the moment it
  failed CI. Lint checks that assert a phrase exists went from 34 to 91 in three
  days.
- **Enforcement is in the wrong layer.** Most rules are prose, and the lint can
  only prove that a sentence exists. The text-matching guard is called a
  boundary, but its own vendor says it is not one (below).
- **What is installed is not what the repo says.** On 2026-11-20 `install.cs` ran
  from the #52 worktree. Every harness then loaded its contract, its guard hook
  and its memory from a merged feature branch for 32+ hours, and nothing noticed.
  `~/.claude/agents/` still holds three agents retired in #41 (`plan-review-deep`,
  `review-light`, `second-opinion`), and Claude Code can still dispatch them.
- **Claude models run through opencode.** Opus and Sonnet reach opencode through
  the `claude-agent/*` provider. That route needs `plugins/claude-entrypoint.js`
  to correct how Anthropic meters the 5-hour window. It also splits one Claude
  agent definition into two renders (`agents/*.md` and `~/.claude/agents/`).

## Goals: v2 has to beat v1 on these numbers

| Measure | v1 now | v2 target |
| --- | --- | --- |
| Instruction text loaded every session (`AGENTS.md` + `~/.claude/rules/*.md` + opencode `instructions`) | 11,835 chars + pstack's rule file (#54) | ≤ 8,000 chars in total, capped by lint |
| `claude-agent/*` models in opencode config or `agents/*.md` | 4 pins + plugin | 0 |
| Claude-model work run in Claude Code (T3 `claudeAgent` or `claude`) | partial (#53) | all of it |
| Installed state matches the repo render (`install.cs --doctor`) | 20 paths drifted, 3 stale agents | exit 0, no extras |
| `deny` vectors pass through every render | 152/152 (guard + opencode) | 152/152 through guard, opencode and Claude settings |
| `evals/cases` reviewer recall on native Claude Code | 2 of 9 measured (#53) | 9/9, equal to or better than opencode |
| Gates that write a ledger row | none since 2026-11-14 | review, consult: 100% |
| Lint checks that assert a phrase exists | 91 | 0. Replaced by a rule table whose enforcers the lint resolves (see The contract) |
| Mandatory steps from edit to PR | ~7 | ≤ 3 |

If v2 misses any row, we keep v1 and fix the gap there.

## What does not change

These have real incidents behind them, so v2 keeps them as they are:

- `policy/permissions.json` as the single source, all 256 vectors, the
  `harness-guard` hook and `bin/sync-harness`. Behind them: #16 (four bypass
  rounds), #31, #43.
- The git boundaries: push asks; force, delete, mirror and `+refspec` are denied.
- An independent, read-only review for sensitive changes. The ledger shows 32
  reds across 89 reviews and 84% of findings acted on.
- The freeze on `memory/core/**`, and the person-promoted `dream` queue.
- Test discipline: red before green; never weaken a test to pass; test cleanup
  is its own change.

## Harness topology

One rule: **a model runs in its own vendor's harness.**

| Model family | Harness | T3 provider | Config v2 renders |
| --- | --- | --- | --- |
| Claude (Opus, Sonnet, Fable, Haiku) | Claude Code | `claudeAgent` | `~/.claude/CLAUDE.md`, `settings.json` (permissions, hook, sandbox), `agents/`, `skills/`, `commands/` |
| DeepSeek, Gemini, other `opencode-go/*` / `opencode/*` | opencode 2 (version pinned) | `opencode` | `~/.config/opencode/opencode.json`, `agents/` |
| Grok | Grok Build | `grok` | `~/.grok/AGENTS.md`, the hook in trusted folders (see open decision 2) |

What this changes:

1. **Agent definitions use logical model names.** `agents/<name>.md`
   frontmatter says `family: claude` and `model: opus` (or
   `family: opencode-go`, `model: deepseek-v4.1-flash`). `sync-harness`
   renders each agent only into its family's harness: Claude agents into
   `~/.claude/agents/`, others into opencode. No agent is rendered twice.
2. **opencode stops hosting Claude.** `review-deep`, `advisor` and `verifier` move
   to Claude Code native agents. `opencode.json` and the
   opencode agent renders contain no `claude-agent/*` id. `plugins/claude-entrypoint.js`
   is deleted: it exists only because opencode spawns Claude processes. Lint
   rejects any `claude-agent/` string outside `evals/` history.
3. **Review follows whoever wrote the diff** (roles are in the next section).
   The rule becomes *independent, fresh-context and read-only*. It is
   cross-family whenever the writer is DeepSeek, which is the default:

   | Diff written by | Ordinary change | Sensitive change |
   | --- | --- | --- |
   | DeepSeek implementor (the default) | the Opus lead reads the diff and reruns the check at the named commit | also a fresh-context `review-deep` (Opus): a Claude Code native agent, read-only, given only the bundle, with no share of the lead's context. Cross-family. |
   | the Opus lead itself (small fixes, review findings) | rerun the check | a fresh-context `review-deep` on **Sonnet**. Same family; decided by the person on 2026-11-21, because Grok usage is not paid for at volume. |

   This is a deliberate relaxation of v1's "must come from a different family"
   for one case. The evidence makes it a modest loss, not a large one. A fresh
   same-model reviewer was statistically indistinguishable from a top-tier
   cross-model one (F1 28.6% vs 32.3%, p = 1.00), and on code it was ahead. What
   is lost is decorrelation: about 59% of unique findings came from only one of
   the two approaches, and same-family self-preference becomes possible.

   Two mitigations keep that case rare:
   - **Opus routes sensitive edits to an implementor,** even small ones. The
     writer is then DeepSeek, and the Opus review is cross-family at no extra
     cost. Opus writing a sensitive diff itself is the exception and is stated
     in the PR.
   - **Sonnet reviews Opus, not Opus reviewing Opus.** A different model with no
     shared context limits correlation within the family.

   A sensitive DeepSeek diff gets a fresh reviewer, not just the lead's own
   read. The lead wrote the brief and is primed by its own reasoning, and the
   research measures fresh context as an independent lever.

   Source for the review numbers:
   [arXiv 2610.01471v2](https://arxiv.org/html/2610.01471v2), a single-author
   preprint. The same study found a lightweight cross-vendor reviewer did worse
   than same-model review, so capability matters more than vendor. That is why
   DeepSeek flash never reviews an Opus diff.
4. **Off T3, the commands are equivalent:**
   `claude -p --agent review-deep "<bundle>"`, and add `--model sonnet` when
   the writer was Opus. `evals/run-claude.sh` (#53) already drives this.
5. **Metering.** T3 labels its Claude processes `CLAUDE_CODE_ENTRYPOINT=t3-code`,
   and an interactive `claude` run is metered as the CLI. With opencode no longer
   spawning Claude, nothing needs the plugin's override.

## Roles: Opus leads, DeepSeek implements

Decided by the person on 2026-11-21, based on what they see working at
Anomaly.

The top-level session is **Opus in Claude Code**. It plans, writes the brief,
dispatches the implementation, reviews it and lands it. Implementation goes to
`implementor` on `opencode-go/deepseek-v4.1-flash#low` in opencode, through
T3 `delegate_task` with `providerInstanceId: opencode` and
`isolation: worktree`. Low effort and staying on opencode both follow from the
Harness leaderboard section below.

This reverses #39's top-level rule ("You do the work. Do not dispatch a
writer"). That rule existed because a DeepSeek top level was dispatching to
avoid editing. With a stronger lead, dispatch becomes the point, not an escape.

The research supports the split, under conditions:
- Aider's architect/editor split scored 85.0% against 79.7% solo.
- Anthropic's advisor pattern pairs a strong model's judgement with a cheap
  executor.
- Cognition's "smart friend" failed because the weak model decided when to
  escalate. Here the strong model decides.

The conditions, each tied to a source or an incident:

1. **One writer per task and per worktree.** Parallel implementors only on
   disjoint files, never sharing a design decision mid-flight. Cognition: writes
   stay single-threaded. Cursor: 20 agents gave the throughput of 2–3.
2. **The brief carries the decisions, not pointers.** It states the done-when,
   the red check, the files in scope as repo-relative paths, the base
   (`git fetch origin && git checkout -b <b> origin/main`), and at most three
   issues. From the 2026-11-21 lessons: a delegate worktree is cut from the
   parent's commit, and DeepSeek delegates hit their step limit beyond about
   three issues and leave work uncommitted. The brief template is a skill
   (`skills/implementor-brief/`), not contract text.
3. **The implementor is bounded.** It cannot dispatch, cannot run `install.cs`,
   `sync-harness --apply` or `sync-pstack --apply`, and cannot use `git stash`.
   It commits on its own branch and returns the head SHA, the red and green
   commands with their exit codes, and the files it touched.
4. **The lead verifies; it does not trust the summary.** It reruns the check at
   the returned SHA and reads `git status` before calling anything green.
5. **Concurrency is capped:** at most two test-running implementors at once,
   from the 2026-11-21 RAM incident.
6. **Usage limits.** When Opus hits a usage limit, the lead does not retry Opus
   (2026-11-21 lesson). It switches to Sonnet. If Sonnet is limited too, it stops
   and hands back, with the implementor results it has harvested so far.

What this costs: Opus tokens for every plan and review, and a serial review
queue. The research names review bandwidth, not generation, as the ceiling,
which is another reason for the two-implementor cap.

Phase 6 measures the split before it becomes the contract. It runs the writer
eval (`evals/run-writer.sh`, `tests/eval_writer.py`) on DeepSeek implementors
from Opus briefs and compares against Opus implementing alone: first-pass green
rate, review reds per change, and Opus tokens per change.

## Learnings from poteto (Lauren Tan, Cursor)

Sources: the pstack guide and principle skills at the commit #54 pins
(`cursor/plugins@0b46ec3`, `pstack/docs/guide/`, `pstack/skills/principle-*`),
and her post "The Complete Guide to pstack, Part 1: Verification is all you
need". Her claim of 10,000 internal runs a week is her own report, not a
measurement we can check.

How each lesson changes this plan:

| Her lesson | What v2 does with it |
| --- | --- |
| **Verification is critical infrastructure.** An agent that can check its own work closes the loop without you. Keep the verification skill current with a daily maintenance pass. | Here the product being verified is the harness. `install.cs --doctor` plus the per-harness load check is that verification, and the daily job runs it before anything else. It moves to Phase 0 and is the first thing built. |
| **Prove it works:** check the real artifact, never a proxy. "It compiles" does not count. | A green lint is a proxy. The real artifact is what each harness actually loads. That is why both audits in this thread missed the 32-hour relink: they read the repo, not `~/.config`. |
| **Encode lessons in structure / `correct`.** Architecture, then types, then a lint whose error names the fix, then a test, then docs. A rule table pairs each rule with its enforcer. | Adopted as the shape of the contract (next section). It replaces the 91 phrase checks outright, rather than trimming them to 10. |
| **Subtract before you add.** Remove first; design for observed usage; no speculative guards; simplify prompts. | The phases are reordered so cuts land before additions (Phases). The advisor's four triggers and the ambiguity section each get a 30-day ledger window, and the remaining "preventive" rules from #45 and #48 face the admission rule. |
| **Separate before serializing shared state.** Give each actor its own file, key or branch, and merge where the state is read. "Instructions are not concurrency control." | Every write target that parallel agents share becomes per actor. Dream writes `pending/<date>-<run>.md` instead of appending to one dated file (the 2026-11-20 file split in two). The ledger writes one file per review, aggregated on read. Delegates commit WIP instead of stashing. Global config has one writer: `install.cs` from the canonical root. |
| **Guard the context window.** Send bulk reading to subagents, keep findings in the main chat, cap the scope of each phase. | The Opus lead sends repo-wide reads to `explore` on DeepSeek and keeps only findings. This is the same split as Roles, applied to reading. |
| **Never block on the human:** proceed on reversible work and present it; confirm only irreversible actions; product direction comes from the person. | v2's stops are audited against this. A stop stays only if it guards an irreversible action or a question of intent. v1's "stop and ask" points that guard neither become "proceed and say so". |
| **Pitfall: polishing an abstract plan.** "Adversarial review of a plan with no code behind it invents risks that will never happen." Prototype, then review what got built. | This thread is the example: four rounds on plans before any code. The required advisor consult (it trips three triggers) runs on the Phase 0 diff together with this plan, not on the plan alone. Phase 0 is small enough to serve as the prototype. |
| **Pitfall: accepting every review comment.** Keep only the findings a rerun proves, and list what was dropped. | This becomes the evidence rule in Gates. A finding the reviewer cannot reproduce is reported but does not block. |
| **Say the goal, not the ceremony.** A prompt has five parts: the goal, a done check that can pass or fail, the proof you want, what you already know, and the real constraints. Leave out the how. | These five are `skills/implementor-brief/`, plus the files in scope. The brief carries design decisions already made, never a how the implementor could choose better. |
| **Earn the trust before the loop.** You have done the task by hand; the agent has your tools; every stage proves its work and can stop the line; repeated failures from transcripts are already checks. | These are the v2.1 preconditions for agents merging their own PRs, alongside the four gates. |
| **Prefer cloud agents to local worktrees** past a handful in parallel. | Not in v2.0. When the two-implementor cap binds, the next step is implementors on a linked T3 environment (another machine), not more local worktrees. |
| **Build the lever:** if a script can do a step the same way every time, use the script, and save agents for judgment. | The PR sequence (push → create → link → watch) and the review bundle become one script each. They come out of the contract text. |

One implication for open work: by her own "test a skill change blind" rule,
#54 adopts 19 pstack skills without an eval on this harness. v2 requires that
eval before #54 merges, or a smaller first set that can be evaluated.

## Harness leaderboard

Source: Joel Niklaus's
[Harness Leaderboard](https://huggingface.co/spaces/joelniklaus/harness-leaderboard),
board release **v0.1.11** (2026-11-21), read from its public `results/cells.csv`.
Each row holds the model fixed and varies only the harness at a pinned version:
Terminal-Bench 2.1 plus DeepSWE v1.1, 198 tasks, 3 attempts each (594 trials per
setup), with 95% CIs and a paired bootstrap for ties. A trial that reached the
task's answer counts as a fail.

DeepSeek-V4.1-Flash (✓ = tied for first):

| Harness | Low effort | High effort | $/pass, low |
| --- | --- | --- | --- |
| OpenCode 2.2.6 | 71.8 [65.6, 78.0] ✓ | 69.8 [63.5, 76.1] ✓ | 0.135 |
| Grok Build | 70.1 ✓ | 71.8 ✓ | 0.136 |
| Claude Code | 68.9 [62.5, 75.2] ✓ | 70.1 [63.8, 76.4] ✓ | 0.150 |
| mini-swe-agent | 68.0 ✓ | 69.1 ✓ | 0.182 |
| Hermes Agent | 60.7 | 63.2 | 0.141 |

What it changes:

1. **DeepSeek implementors stay in opencode.** On DeepSeek, OpenCode 2 is
   statistically tied with Claude Code and Grok Build for first, and costs no
   more per pass. It uses about 27% more tokens per trial than Claude Code at
   low effort (7.8M vs 6.1M), which is worth watching against subscription
   limits but is not a reason to move. The subscription is already paid for,
   so moving would only add an API bill.
2. **Low effort, not high.** OpenCode scores 71.8 at low and 69.8 at high,
   tied, and low is about 20% cheaper per pass (0.135 vs 0.171) and uses about
   20% fewer tokens. The implementor runs at low unless our own eval shows
   otherwise.
3. **Harness version matters as much as harness choice.** OpenCode 1.19.0 scored
   57.6 on this board's 2026-11-02 snapshot. Its replacement, 2.2.6 on 2026-11-09,
   ties for first. Most of the old gap was setup: 1.19 talked to the model through
   a Responses-to-Chat bridge and had no context limit, so it compacted only after
   the provider refused a request. For v2 this means two things. The opencode
   version is pinned in `tools.json` like every other tool, and a version bump
   reruns the writer eval.
4. **One run per eval case cannot rank anything.** In the 2026-11-02 snapshot, a
   rerun of the same harness flipped about 25% of DeepSeek tasks, against 32% for
   a harness swap. The Oct 18 gate-model decision and the 2-of-9 measurement in #53
   were single runs. v2 evals run 3 attempts per case, report the rerun flip rate
   next to any comparison, and call two setups tied unless a paired CI excludes
   zero.
5. **Answer access counts as a fail in our evals too.** If a writer reads the
   hidden test or the reference patch, the attempt fails, whatever the grader
   says.

Caveats: the board measures autonomous benchmark tasks, run headless with
stock prompts. It does not measure our repos, our `AGENTS.md`, or a brief from an
Opus lead. It is a strong prior and does not replace the Phase 6 measurement.

Correction: an earlier revision of this section quoted the 2026-11-02
`docs/blog/numbers.md`, which still showed OpenCode 1.19.0 trailing by 13.7
points, and concluded that implementors should leave opencode. That file
predates the OpenCode 2 swap. The live `results/` data above replaces it. This
is poteto's "explain the number" pitfall: a number was trusted before checking
what it measured.

## Phase 2b result (2026-11-22)

`evals/compare.py` over the 8 change cases, 3 attempts each, `review-deep`'s
prompt in every arm:

| Arm | Pass | Rerun flips | Cost (list) |
| --- | --- | --- | --- |
| A, Opus native (`claude -p`) | 24/24 | 0/8 | $9.48 |
| B, Opus via opencode `claude-agent/opus#medium` | 22/24 | 1/8 | not reported by opencode |
| C, Sonnet native | 22/24 | 2/8 | $3.18 |

A − B: +0.08 per case, 95% CI [+0.00, +0.25], tied. A − C: +0.08, CI
[+0.00, +0.17], tied.

What the misses were:
- Both of B's misses were the same 🟠 on the clean case, "no evidence the red
  tests were run". It names no defect and would not block under the evidence
  rule in Gates.
- C had one speculative 🟠 on the clean case. It also missed the 🔴 CI-restore
  break in `wip-slice-c8-tc2` once in three attempts. That is the one real miss
  in 72 reviews. It is relevant because Sonnet reviews Opus-written diffs.

Phase 3's gate (A ties B or better) passes. Eight cases cannot separate the arms
statistically. The result says that going native loses nothing measurable.

Not measured: B's wall time and cost. opencode reports no cost, and the
directory timestamps do not give a usable duration.

## v2 reimagined: one harness, roles, profiles (2026-11-22)

Decided by the person, superseding Harness topology and Roles where they differ:

- **opencode only.** Claude runs through opencode again (Phase 2b: 22/24, tied
  with native 24/24). Phase 3 is reverted and the metering plugin comes back.
  The Claude Code native render, its sandbox profile, `run-claude.sh` and the
  Grok links are deleted.
- **No container.** The person accepts weaker isolation. What is kept costs
  nothing and needs no isolation: branch protection on `main` (server-side, so
  it covers every harness), no secrets exported into every shell, backups. The
  guard stays as an accident-catcher, not a boundary.
- **Models are chosen by person and machine,** because friends use this repo
  with other subscriptions.

### Model roles

The repo names roles, never model ids: `lead`, `implementor`, `reviewer`,
`advisor`, `verifier`, `explore`, `drafter`. Agent files say `role:`.

Resolution, later layers win:
1. **Repo defaults** (`models/roles.json`): a profile that works for anyone.
2. **A profile** (`models/profiles/<name>.json`), one per subscription bundle,
   e.g. `claude-max`, `opencode-go`, `api-keys`. A person picks one, or
   `install.cs` suggests one from the providers `opencode models` reports.
3. **The machine** (`~/.config/opencode/models.local.json`, untracked): only
   what differs here.

`install.cs` writes the resolved config opencode reads, and `--doctor` checks
every resolved model exists on this machine. Invariants are checked on the
resolved set, not the defaults: the reviewer never shares the implementor's
family, and a local file cannot weaken a gate. Extends `pstack/models.json`'s
routes table (#54) rather than adding a second one.

Review when a profile has only one model family (the person's decision,
2026-11-22): a fresh same-model reviewer by default (fresh context, capable
model, noted in the PR), since the research found it about as good as a
cross-model one. A person can set `"review": {"single_family": "stop"}` in
their local file to require stop-and-ask instead. Multi-family profiles keep
the cross-family rule.

`main` is protected (2026-11-22): PRs only, the four CI jobs required, no force
push or delete, admins included because agents use the person's token.

Portability for friends: nothing personal in tracked defaults (bot names, the
bootstrap slug, memory, the author's paths); the README says how to pick a
profile.

## The contract

`AGENTS.md` keeps only what the model cannot get any other way: commands,
boundaries, and traps that contradict a default. Everything else moves to the
layer that can enforce it:

| Kind of rule | Where it lives in v2 | Example |
| --- | --- | --- |
| Must never happen | `policy/permissions.json` → guard, native deny, sandbox | force push, reading `~/.ssh` |
| Must hold for a change to land | a test or CI check | phrase-pinned review rule → required check (see Gates) |
| A procedure | a skill, loaded only when used | the sensitive-review steps, the PR-open sequence, Roslynk usage |
| Applies to some paths only | a scoped rule (`paths:` frontmatter) | `.cs` → Roslynk; `memory/core/**` → frozen |
| Obvious from the code | deleted | — |

This is poteto's `correct` order, adopted as is: architecture first, then
types, then a lint whose error names the fix, then a test, and docs last, only
for judgment calls. Her corollary decides what happens to the prose: "If the
fix is structural, only use the structural fix. The instruction is the
symptom." Once a rule has an enforcer, its sentence is deleted, not pinned.

**The rule table replaces the phrase lint.** `AGENTS.md` ends with one table
that pairs each rule with what enforces it: a policy id, a test name, a hook or
a CI job. `bin/lint-config` resolves every enforcer: the policy id exists, the
test exists and runs in CI. It fails on a row whose enforcer is missing. A row
whose enforcer is `judgment` must carry a one-line example of the failure it
prevents. When a correction repeats a rule that is already in the table with no
enforcer, that is a repeat, and the fix moves up a level in the same change. A
row is dropped once its mistake can no longer happen.

**Admission.** A mistake class counts once it has happened twice, or once if
the damage cannot be undone. The new check must be proven to fail on the real
past mistake. For example, the 0b red check runs `install.cs` from an actual
feature worktree. An exception goes on the offending line with a reason, an
expiry date and the person's approval. This covers the vectors' `skip_agents`
and `native_overblock_ok`, which today carry neither a reason nor an expiry.

**An edit to a rule or skill is an experiment.** Before it is kept, a change to
`AGENTS.md`, an agent prompt, or a skill, including adopting someone else's
skills, runs blind against the writer eval: same task, candidates unaware of
the eval and of each other, one judge. poteto's reason applies directly: "A fix
written from one bad session tends to overfit that session, and over many
edits the skill drifts."

Lint caps the always-loaded instruction text at 8,000 characters in total.
Raising the cap is its own change.

The research behind this split:
[IFScale](https://arxiv.org/abs/2507.11538) found instruction-following falls
as rule count grows, and the rules that get dropped are mostly the later ones.
[ETH Zurich](https://arxiv.org/abs/2602.11988) found context files cost about
20% more inference with little gain, and the only benefit came from build
commands and unusual tooling. Anthropic's Claude Code guidance says to keep the
file under ~200 lines and to use hooks rather than emphasis
([best practices](https://www.anthropic.com/engineering/claude-code-best-practices)).

## The install is part of the product

1. **Canonical root.** `install.cs` refuses to run from any root other than the
   canonical checkout (`~/dotfiles`, or `DOTFILES_ROOT`) unless given an explicit
   `--from <path>`. With `--from` it prints a warning and records the root.
   Red check: run it from a worktree and expect a non-zero exit.
2. **It owns what it renders.** Every file `sync-harness` writes into
   `~/.claude/agents/`, `~/.claude/rules/` and opencode's agent dir carries a
   stamp. `--apply` removes stamped files it no longer renders and reports
   unstamped ones. Red check: a stale stamped `review-light.md` must be removed.
3. **A manifest and a doctor.** `install.cs --doctor` writes
   `~/.config/opencode/install-manifest.json`: the resolved root, every link
   target, and every rendered file's hash. It exits 1 on any drift. The daily
   T3 dream job runs `--doctor` first and stops on drift, so dream never writes
   into a non-canonical tree.
4. **A load check per harness.** The precedence rules for `AGENTS.md` and
   `CLAUDE.md` differ across products. The doctor confirms that each harness's
   loaded contract file resolves to the canonical `AGENTS.md`.

## Gates

- **The review records what it catches.** Each review and each consult writes
  one record (`kind, date, artifact, head, reds, ambers, acted, dismissed,
  model, harness`) as its own file under `~/.config/opencode/reviews/`, and the
  records are aggregated on read. One file per review means parallel reviewers
  never append to a shared file. The fields revive the format `bin/review-log`
  wrote until #41, plus `kind`. The existing 89 rows in `reviews.jsonl` are
  imported once. A gate with no records for 30 days is proposed for removal.
- **Findings carry evidence.** A red or amber names a failing test, a
  line-level counterexample, or a broken rule. Findings without evidence are
  reported but do not block. Style is out of scope.
- **Rounds are capped.** One review, plus one re-review of the fix delta.
  Another round happens only if the re-review raises a new red. #54 took seven
  rounds.
- **Advisor.** The research supports keeping it: Anthropic's advisor pattern
  measured +2.7 points at −11.9% cost per task, and a fixed trigger avoids the
  failure where the weak model decides when to escalate. It becomes a Claude
  Code agent, keeps its two-per-change cap, and has 30 days of ledger rows to
  justify itself.
- **The verifier stays** (decided 2026-11-21, reversing an earlier "cut").
  The cut rested on "no recorded run that produced a finding", which is false.
  `evals/README.md` records a verifier finding: a candidate fixture's added
  tests still passed with the fix reverted, so the fixture was withdrawn. The
  verifier is also the only agent that runs plan cases (`plan-ide-storage-tab`)
  and the verifier gate. It runs on request only, so its 292-line prompt costs
  nothing until it is called. Cutting it would have touched about 15 files and
  14 policy vectors, not the six wiring points the first draft counted. Like
  the advisor, it gets ledger records (Phase 7) and a 30-day window.

## Security

- **The sandbox becomes the boundary.** The Claude Code sandbox profile (today
  opt-in via `--sandbox`) is on by default: no ambient credentials, and network
  egress on an allowlist. Anthropic calls permission deny rules "a best-effort
  pattern match… not a hard security boundary", and published audits found
  eight bypasses and a CVE in them
  ([GMO Flatt](https://flatt.tech/research/posts/pwning-claude-code-in-8-different-ways)).
- **The guard is reclassified.** It catches accidents and leaves an audit
  trail. Its tests gain the published bypass corpus and parity checks that run
  the same command through every render and expect the same decision.
- **No shared-state writes from agents.** `git stash` is denied in favour of
  WIP commits. Delegates may not run `install.cs`, `sync-harness --apply` or
  `sync-pstack --apply`. Concurrency is capped by host RAM and review capacity:
  at most two full test suites at once, as the 2026-11-21 lesson records.

## Memory

- Today a `source:` line covers each dream block. v2 requires one per lesson
  (session, PR, or transcript), and `--promote` rejects a lesson without it.
  It serves as provenance and as the handle for removing a bad lesson.
- Promotion runs on a fixed weekly cadence that the person owns. If two weeks
  pass with nothing promoted, dream stops drafting, rather than filling a queue
  nobody reads.
- The drafter prompt says what memory is for and leaves salience to the model.
  A "record only failures" style checklist reduced memory's benefit in
  Anthropic's measurement
  ([components of agent memory](https://www.anthropic.com/research/components-of-agent-memory)).

## Not in v2.0: agents merging their own PRs

This is deferred to v2.1, and only after all four of these exist and have been
run once:

1. a test-integrity check that rejects removed or weakened assertions and new
   skip or xfail markers, structurally rather than by path diff;
2. a check that the diff does not touch `.github/workflows/**`, branch
   protection, or `policy/**`;
3. required status checks on `main`;
4. a revert that has been rehearsed.

poteto's four conditions for trusting a loop must also hold:
- the person has merged this kind of change by hand;
- the agent has the same signals the person would use;
- every stage proves its work and can stop the line;
- repeated failures from transcripts are already checks.

No published team reports outcomes for autonomous agent merges. Required checks
prove only that today's tests pass, and agents are documented weakening tests to
get there: [ImpossibleBench](https://arxiv.org/html/2510.20270v1) found 54–76%
on impossible tasks.

## Phases

Each phase is one PR, red check first, with the review that the table under
Harness topology assigns to the writer. Phase 0 lands
on v1 `main`; the rest build on a `v2` branch that is switched in with
`install.cs --from`.

The order is verify, then subtract, then add.

| Phase | Change | Red check | Rough size |
| --- | --- | --- | --- |
| **Verify the harness** | | | |
| 0a | Relink live config to `~/dotfiles`; merge the split `pending/2026-11-20.md` (person runs it) | `install.cs --check` reports 20 drifted paths | none |
| 0b | Canonical-root guard in `install.cs` | run from a real feature worktree: exits 0 today | +60 |
| 0c | `--doctor` with manifest + per-harness load check; daily job runs it before dream | doctor exits 0 against today's drifted links | +120 |
| **Subtract** | | | |
| 1 | Stamped renders; prune the 3 retired `~/.claude/agents/*` | the 3 retired agents survive `--apply` | −3 files / +80 |
| 2 | ~~Cut verifier~~ Keep the verifier; correct this plan (its premise was false) | — (docs only) | 0 |
| 2b | **Measure before deleting the Claude path.** Run `review-deep` on all 9 eval cases, 3 attempts each, in three arms: (A) Opus native, `claude -p --agent review-deep`; (B) Opus through opencode, `claude-agent/opus`, with the plugin as it is today; (C) Sonnet native. Record recall, false reds, tokens and wall time per arm, plus the rerun flip rate, and a paired CI for A vs B. A trial that reads the case's answer counts as a fail. | `evals/run-claude.sh` has no opencode arm and refuses fewer than 3 attempts | +80, no deletions |
| 3+4 | **One PR, per the second advisor consult (2026-11-22).** `review-deep`, `advisor` and `verifier` are roles, not Claude agents: they **stay in `agents/` and in opencode**, and only their `claude-agent/*` pins go. A Grok or Go lead, `commands/verify.md` and `evals/run.sh -a verifier` still need them. Commits: C1 adds a lint that rejects `claude-agent/` in opencode-scoped config, red. C2 is cleanup on its own: it removes the plugin's lint check (`lint-config` 540–547, and the empty-`plugins/` failure at 516–518) and its `tests/lint_config.py` cases, saying why nothing replaces them. C3 deletes `plugins/claude-entrypoint.js`, drops the pins, and rewrites `AGENTS.md` to ≤ 8,000 characters with its lint needles, so the contract never disagrees with the config. Before C3, run the native verifier on one plan case and one change case. The deletions need the person's confirmation. | C1 red | −4,000 chars, −150 lines |
| 5 | Phrase lint → rule table + enforcer-resolving lint | lint fails on a table row whose test does not exist | −300 / +80 |
| **Add** | | | |
| 6 | Roles: Opus lead + DeepSeek `implementor#low` in opencode, with the opencode version pinned in `tools.json`; blind writer eval of the split, 3 attempts per case; `skills/implementor-brief/` (the five parts); review by writer family (reviewer recall already measured in 2b) | the eval script refuses a comparison with fewer than 3 attempts per case | +150 |
| 7 | Ledger as one file per review with `kind`; evidence-required findings; round cap | `tests/review_log.py` fails with no writer | +120 |
| 8 | **8a** sync-harness applies to the real home only from the canonical checkout (done). **8b** deny `git stash pop` (done). **8c** per-run dream files: *dropped*, because no concurrent-write failure was observed within one tree, dream already locks and hash-checks, and the 2026-11-20 split came from two trees, which 0c prevents. **8d** bypass corpus: six published forms closed (done). **8e** sandbox on by default: *the person decides*, because it changes every Claude Code session's network and file access. Three-way parity is already enforced (`check_policy` runs each vector through guard, opencode and native) | per item | +200 |
| 9 | Memory cadence: dream stops staging when the oldest pending file is over 14 days old and nothing was promoted in 14 days (done). Drafter prompt: *unchanged*. It has no failure-only checklist, and with no incident or eval behind a change, the admission rule keeps it out | tests/dream_cadence.py | +60 |
| 10 | Live on v2 for one week; compare against the goals table | — | — |

The required advisor consult (more than three files, more than 400 lines,
removal of checks) runs once, on the Phase 0 diff together with this plan.
That follows poteto's pitfall: a review of a plan with nothing built behind it
invents risks.

## Open decisions (for the person)

1. **Default writer.** Decided 2026-11-21: Opus leads at the top level in
   Claude Code, and DeepSeek implementors write. See Roles.
2. **Grok Build.** Default: keep its render (it is cheap and tested), but no new
   v2 work targets it. Drop it if you do not run Grok weekly.
3. **Reviewer for Claude-written diffs.** Decided 2026-11-21: a fresh-context
   Sonnet `review-deep`, not Grok. Phase 2b runs `evals/run-claude.sh` with
   Sonnet on the 9 eval cases, so its recall is a number rather than an
   assumption.
4. **Self-merge.** Default: v2.1, after the four gates above.
5. **Which harness runs the DeepSeek implementor.** Settled by the evidence:
   opencode 2, which is tied for first on DeepSeek on the current board and
   already covered by the subscription. Not a question for the person unless
   Phase 6's eval disagrees.
