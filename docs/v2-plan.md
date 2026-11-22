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
| `AGENTS.md` size | 11,835 chars | ≤ 8,000 chars, capped by lint |
| `claude-agent/*` models in opencode config or `agents/*.md` | 4 pins + plugin | 0 |
| Claude-model work run in Claude Code (T3 `claudeAgent` or `claude`) | partial (#53) | all of it |
| Installed state matches the repo render (`install.cs --doctor`) | 20 paths drifted, 3 stale agents | exit 0, no extras |
| `deny` vectors pass through every render | 152/152 (guard + opencode) | 152/152 through guard, opencode and Claude settings |
| `evals/cases` reviewer recall on native Claude Code | 2 of 9 measured (#53) | 9/9, equal to or better than opencode |
| Gates that write a ledger row | none since 2026-11-14 | review, consult: 100% |
| Lint checks that assert a phrase exists | 91 | ≤ 10, each tied to a named incident |
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
| DeepSeek, Gemini, other `opencode-go/*` / `opencode/*` | opencode | `opencode` | `~/.config/opencode/opencode.json`, `agents/` |
| Grok | Grok Build | `grok` | `~/.grok/AGENTS.md`, the hook in trusted folders (see open decision 2) |

What this changes:

1. **Agent definitions use logical model names.** `agents/<name>.md`
   frontmatter says `family: claude` and `model: opus` (or
   `family: opencode-go`, `model: deepseek-v4.1-flash`). `sync-harness`
   renders each agent only into its family's harness: Claude agents into
   `~/.claude/agents/`, others into opencode. No agent is rendered twice.
2. **opencode stops hosting Claude.** `review-deep`, `advisor` and (until it is
   cut) `verifier` move to Claude Code native agents. `opencode.json` and the
   opencode agent renders contain no `claude-agent/*` id. `plugins/claude-entrypoint.js`
   is deleted: it exists only because opencode spawns Claude processes. Lint
   rejects any `claude-agent/` string outside `evals/` history.
3. **Delegation follows the family.** The cross-family rule stays, and the
   target follows from the writer:

   | Writer | Required review | Optional second review |
   | --- | --- | --- |
   | opencode (DeepSeek) | Claude Code `review-deep` (Opus), via T3 `delegate_task` with `providerInstanceId: claudeAgent` | — |
   | Claude Code (Opus or Sonnet) | a non-Claude reviewer at frontier capability (Grok 4.7 or Gemini via opencode), not a flash model | a fresh-context Claude `review-deep` |

   This follows the evidence. A cross-vendor reviewer was no more accurate than
   a fresh same-model one, but its findings overlap only 41% of the time, and one
   fresh same-model plus one cross-model reviewer found 56.7% of planted errors
   against 42.7% for two same-model reviewers. A lightweight cross-vendor
   reviewer did worse than same-model, so capability matters more than vendor
   ([arXiv 2610.01471v2](https://arxiv.org/html/2610.01471v2), a single-author
   preprint). DeepSeek flash is not an acceptable reviewer of an Opus diff.
4. **Off T3, the commands are equivalent:**
   `claude -p --agent review-deep "<bundle>"` for a Claude review, and
   `opencode run --agent <non-Claude reviewer> "<bundle>"` for the other
   direction. `evals/run-claude.sh` (#53) already drives the first.
5. **Metering.** T3 labels its Claude processes `CLAUDE_CODE_ENTRYPOINT=t3-code`,
   and an interactive `claude` run is metered as the CLI. With opencode no longer
   spawning Claude, nothing needs the plugin's override.

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

A rule is admitted only with a named incident or a failing eval, stated in the
PR. Lint caps `AGENTS.md` at 8,000 characters; raising the cap is its own
change. The phrase lint shrinks to at most 10 anti-deletion pins. Each pin names
the incident it protects, and the pins cover only text that has no enforcing
layer.

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

- **The review records what it catches.** Each review and each consult appends
  `kind, date, artifact, head, reds, ambers, acted, dismissed, model, harness`
  to `~/.config/opencode/reviews.jsonl`. This revives the format that `bin/review-log`
  wrote until #41, and adds a `kind` field. A gate with no rows for 30 days is
  proposed for removal.
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
- **The verifier is cut.** It is the largest prompt (292 lines) and has no
  recorded run that produced a finding. The cut takes all six wiring points
  with it: `bin/lint-config`, `bin/sync-harness`, `ci.yml`, both test files,
  and the default agent list in the vectors.

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

No published team reports outcomes for autonomous agent merges. Required checks
prove only that today's tests pass, and agents are documented weakening tests to
get there: [ImpossibleBench](https://arxiv.org/html/2510.20270v1) found 54–76%
on impossible tasks.

## Phases

Each phase is one PR, red check first, with a cross-family review. Phase 0 lands
on v1 `main`; the rest build on a `v2` branch that is switched in with
`install.cs --from`.

| Phase | Change | Red check | Rough size |
| --- | --- | --- | --- |
| 0a | Relink live config to `~/dotfiles`; merge the split `pending/2026-11-20.md` (person runs it) | `install.cs --check` reports 20 drifted paths | none |
| 0b | Canonical-root guard in `install.cs` | running from a worktree exits 0 today | +60 |
| 0c | Stamped renders + prune stale `~/.claude/agents/*` | the 3 retired agents survive `--apply` | +80 |
| 1 | `family`/`model` frontmatter; render Claude agents only to Claude Code; delete plugin and `claude-agent/*` pins | lint: a `claude-agent/` id in opencode config is rejected | −150 / +120 |
| 2 | Delegation table in contract + review dispatch by writer family; `evals/run-claude.sh` on all 9 cases | eval parity script fails until 9/9 recorded | +60 |
| 3 | Contract rewrite to ≤ 8,000 chars; procedures → skills; scoped rules | cap check fails at 11,835 | −4,000 chars |
| 4 | Phrase lint 91 → ≤ 10 pins with named incidents | each removed pin listed in the PR body with its replacement layer | −300 |
| 5 | Ledger with `kind`; evidence-required findings; round cap | `tests/review_log.py` fails with no writer | +120 |
| 6 | Cut verifier and its six wiring points | removal-only; suite green, no remaining reference | −450 |
| 7 | Sandbox on by default; guard bypass corpus + three-way parity | parity test fails on a known bypass | +200 |
| 8 | Memory: weekly promote cadence, drafter prompt, doctor-before-dream | dream run with drifted links must refuse | +40 |
| 9 | Live on v2 for one week; compare against the goals table | — | — |

Before Phase 1 starts, the plan gets one advisor consult. It trips three
triggers at once: more than three files, more than 400 lines, and the removal
of checks.

## Open decisions (for the person)

1. **Default writer.** Default: keep DeepSeek in opencode as the default writer,
   and move all Claude-model work (reviews, advisor, hard tasks you choose to
   run on Opus) to Claude Code. The alternative, Claude Code as the primary
   writer, changes the review table: every default change would need a non-Claude
   frontier reviewer.
2. **Grok Build.** Default: keep its render (it is cheap and tested), but no new
   v2 work targets it. Drop it if you do not run Grok weekly.
3. **Frontier non-Claude reviewer for Claude-written diffs.** Default:
   `xai/grok-4.7` through opencode, with Gemini as the fallback. Phase 2
   measures it on the 9 eval cases before it becomes required.
4. **Self-merge.** Default: v2.1, after the four gates above.
