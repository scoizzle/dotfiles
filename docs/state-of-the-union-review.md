# State of the union — 2026-11-17

Scope: this repository, the opencode / Claude Code / Grok harness. Baseline is
`dad8c1b` (2026-11-02); the comparison point is `70d0715` (2026-11-17). That is
14 days and 27 commits. This is a comparison of the two trees, not a memory of
the work.

## The short version

The harness got quieter where it was talking and louder where it was checking.
In two weeks it removed a tier machine, a routing table, an advisor, a second
reviewer, a review ledger and a workflow smoke script — and added a control
plane for live harness config, an opt-in Claude Code sandbox, heredoc and
no-op-edit decisions in the guard, and 59 policy vectors. It also grew its first
test suite: `tests/` did not exist at the baseline.

The through-line is a move from *ceremony that asks the model to behave* to
*checks that fail*. What the model is told is now about half the size; what the
machine enforces is roughly twice.

## By the numbers

| Metric | 2026-11-02 | 2026-11-17 | Δ |
| --- | --- | --- | --- |
| Commits in window | — | 27 | |
| Files changed | — | 64 | +7,220 / −1,688 lines |
| `AGENTS.md` | 9,908 B | 9,455 B | −453 B (−4.6%) |
| `agents/` files | 7 | 6 | −4 deleted, +3 added |
| `bin/` programs | 7 | 5 | −2 |
| `commands/` | 4 | 3 | −1 |
| `skills/` | 1 | 5 | +4 vendored, pinned |
| `tests/` | absent | 12 suites, 2,516 lines | new |
| Policy shell rules | 1 ask / 7 deny | 2 ask / 15 deny | +9 |
| Policy sections | 7 | 9 (`control_plane`, `sandbox`) | +2 |
| Policy vectors | 197 | 256 | +59 |
| CI: Python suites run | 0 | 12 | +12 |

## What moved

### 1. Workflow: from an orchestrator to a default agent that works

The baseline prompt opened with tiers. Every request was classified T0/T1/T2,
then dispatched: `plan-review-deep` before a plan, `implement-deep` after it,
`review-light` for T1, `review-deep` plus `second-opinion` for T2, an advisor
at three named moments, a `review-log` ledger entry at the end. A separate
`smoke-workflow` script exercised the sequence.

That is gone. `AGENTS.md` now names two kinds of change, ordinary and sensitive;
the default agent does the work and may call a lookup or one read-only review.
The expensive table left but the review did not: `agents/*`, `bin/*`,
`commands/*`, `policy/*`, `evals/cases/*`, `skills/*`, `memory/core/*`,
`*.csproj`, `*.sln(x)` and `*Dockerfile*` are named as sensitive, the review is
required, and it must come from a different vendor family than the writer
(`272e97f`). If no such reviewer exists, the change stops for a person instead
of borrowing the writer's family. That stop rule is the strongest line in the
file and it is new.

The PR path also changed. A finished change on a thread branch is now
committed, pushed and opened as a PR without waiting to be asked; only the
touched paths are staged and nothing lands on the default branch (`57dabd6`).
The baseline said not to commit unless asked.

Deleted: `agents/{implement-deep,plan-review-deep,review-light,second-opinion}.md`,
`bin/{review-log,smoke-workflow}`, `commands/second-opinion.md`.
Added: `agents/{build,explore,implementor}.md`. (`agents/advisor.md` was both
added and removed inside the window.)

### 2. Enforcement: a second and third layer under the rules

Policy and guard did most of the growing.

- **New denials** in `policy/permissions.json`: `gh pr merge`, `npm publish`,
  `git restore`, `git checkout --`, `git branch -D`, `git stash drop|clear`,
  push-delete refspecs (`:*`), alongside the existing force/mirror/rm -rf set.
  `git worktree remove` is `ask`.
- **Control plane** (`8d5c394`). A write to live harness configuration —
  `~/.config/opencode/{AGENTS.md,opencode.json,bin,policy,agents,plugins}`,
  `~/.claude/{CLAUDE.md,settings.json}`, `~/.grok/AGENTS.md`, and the checkout
  they link to — is `ask`, not `deny`. `harness-guard` resolves both the target
  and the installed entries to real paths, so an edit through the symlink and
  one through the checkout are the same file.
- **Sandbox** (`8d5c394`). The same policy carries an opt-in Claude Code
  Bash-sandbox profile: home-directory writes and off-list domains refused, two
  NuGet cache paths allowed, `~/.dotnet` deliberately not writable because the
  global tools there run outside the sandbox. `--scope sandbox` previews;
  `--apply --sandbox` merges; a plain `--apply` never touches it.
- **Guard decisions** (`0d8602b`). A heredoc body copied into a file by `cat`,
  `tee` or `dd` is denied; `python3 - <<PY` asks; an interpreter reading data
  allows. An edit whose old and new text are identical is denied for Claude Code
  and trusted-folder Grok. A policy denial now ends with "this is a boundary,
  not an obstacle", and `AGENTS.md` says the same.
- **Lint** pins the wiring: `./bin/lint-config` exits 0 with "9 agents checked",
  and CI runs the 12 Python suites that back it.

### 3. Evidence: the review bundle learned to show its work

The bundle now has `06-test-changes` and `07-checks` (`70d0715`).

- `06-test-changes` lists removed test declarations and assertions, added
  skips, and deleted or moved test files, each with a findable line number. It
  is explicitly a heuristic, and its `none` line names the markers it does not
  check.
- `--check '<cmd>'` records one command's exit code, duration and output in
  `07-checks`, killed at `--check-timeout` (default 900 s). It refuses anything
  `harness-guard` would deny or ask about, because it cannot prompt.
- `--show AGENTS.md --show agents/review-deep.md` puts the base copies in the
  bundle, and `review-deep` must treat them as the governing rules: a diff that
  weakens a check is a 🔴 for a person, not a finding the reviewer may waive.
- `/verify` was rewritten around those three pieces, so a reviewer gets a real
  run instead of a claim.

### 4. Memory: dream reads more and writes less

- The digest was failures only. It now adds recoveries (the command that failed
  and the first that completed after it) and user follow-ups (post-first-message
  heads, top-level sessions, 20 max, 200 characters each), all redacted and
  capped at 12,000 characters. `--no-user-text` keeps a person's words out of
  the prompt that leaves the machine (`8d5c394`).
- The write path was contradictory across `AGENTS.md`, `memory/INDEX.md` and
  `memory/learnings/README.md`. All three now say an agent appends only to
  `pending/`; a person's `--promote` writes the dated files and compacts
  `working.md` deterministically, with duplicates collapsed and sources cited.
  `memory/core/` is never written, and a test proves an agent-written block is
  promotable (`ebd18d8`, `8d5c394`).

### 5. Skills, evals, plugins

- `skills/` went from one local skill to five: `roslynk-rules` plus four
  vendored `dotnet/skills` test skills, byte-identical at `2877c712`, with
  `UPSTREAM.md`, a sha256 pin, and CI verification. `AGENTS.md` gained a Skills
  block with precedence stated, and `review-deep` must load the two
  test-quality skills before judging a test change.
- The eval harness gained a **writer oracle**: `run-writer.sh` clones a case at
  its bugged base, runs a writer, and scores "check exits 0 and no protected
  path changed". `evals/README.md` has the proof procedure for adding a check.
- `plugins/claude-entrypoint.js` was ported to OpenCode 2's `Plugin.define`
  default export after the v1 named export silently dropped the label, with a
  lint check for the failure modes (`d669c16`).

## Regressions and costs

Ranked, and none of them is a reason to undo the trade.

1. **Ordinary behaviour changes get no independent review.** Sensitive ones get
   one. Deleting `review-light` removed the cheapest independent look, and no
   replacement covers a non-sensitive behavioural diff.
2. **The review ledger is gone.** There is no aggregate record of what reviews
   caught or missed; the evals are the only signal left.
3. **Enforcement is uneven by harness.** opencode has no hook. Heredoc,
   no-op-edit and control-plane decisions are Claude Code and Grok only.
   opencode's share is text globs, and a session started inside the live
   checkout sends project-relative paths that no control-plane rule matches
   (verified on opencode 2.3.0). `docs/security-model.md` says so plainly; that
   is honesty, not coverage.
4. **The sandbox is a macOS/Claude Code profile.** Linux and WSL2 are
   unverified, no test run was performed (only a build), `gh` and
   `git push/fetch/pull` are outside it, and whether Grok honours the key is
   unknown.
5. **The default writer is still a default.** The `#high` → `#low` move now has
   a first reading: 6/6 versus 5/6 on six cases, where the one `#high` "failure"
   is a 900 s timeout rather than a wrong fix. One run per cell, one repository,
   one language — the log itself says this cannot rank the variants.
6. **`docs/plan-csharp-native-migration.md` is stale.** It plans seven `bin/`
   programs, including P4 `review-log` and P5 `smoke-workflow`, both deleted in
   `c49e7bd`. It still calls `python3` a hard requirement "until P6, because
   `review-log` etc. are still Python", and there is no `review-log`.
7. **`evals/cases/*/case.json` still points at `~/Projects/Poly/Poly`.** It was
   machine-bound before and is machine-bound now; the README documents it, but
   nothing checks it.
8. **The contract is easier to read and harder to prove.** `AGENTS.md` shrank
   453 bytes while the enforceable surface grew by two policy sections, 59
   vectors and 12 test suites. `lint-config` pins phrases and wiring, not
   semantics.

## What this review verified

| Check | Command | Result |
| --- | --- | --- |
| Policy/render/guard/classifier suites | the 9 scripts in `.github/workflows/ci.yml` | exit 0 each |
| Skills and vendored pin | `python3 tests/skills.py` | exit 0 |
| Dream compaction and digest | `python3 tests/dream_compact.py`, `tests/dream_digest.py` | exit 0 each |
| Rendered policy agrees with the guard | `./bin/lint-config` | exit 0, "9 agents checked" |
| Tree | `git status` | clean at `70d0715` |

Not re-run: `./install.cs`, the sandbox probes, and the eval harness (needs the
Poly fixture and model quota). Sandbox and eval numbers above are taken from
`docs/security-model.md`, `evals/README.md` and the decision log, not measured
here.

## Open threads for the next two weeks

- Decide whether an ordinary behavioural change needs a cheap review, or write
  down in `AGENTS.md` why it does not.
- Rewrite or retire the C# Native AOT plan around five programs; P4 and P5 are
  already deleted.
- Run the writer comparison at `--runs 3` and record it. The current 6/6 vs 5/6
  is one run per cell and cannot gate a pin.
- Prove the sandbox on Linux/WSL2, or call it macOS-only in the README rather
  than in a verification note.
- Decide whether `evals/cases` becomes a vendored fixture or the Poly path is
  declared a required local dependency.
