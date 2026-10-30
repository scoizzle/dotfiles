# Plan: migrate all tooling to C# Native AOT, with dotnetup as the toolchain

Status: revised after plan review. Transient document — delete after the migration lands.

Terminology: **Native AOT** = `PublishAot=true` (IL compiled to native, no JIT, trimmed
CoreCLR, needs clang). Not ReadyToRun (keeps IL + JIT fallback), not Mono "full AOT".
`install.cs` stays a file-based app and is *not* one of the native tools — it is the thing
that builds them.

## Goal

The seven workflow/reporting programs in this repo become C# Native AOT binaries, built at
install time, with `dotnetup` owning the SDK. No Python, no bash except the bootstrap.

## Done-when (each has a command and a failure it can produce)

| # | check | expected |
| --- | --- | --- |
| 1 | `./setup.sh` twice on a clean `$HOME` | 2nd run exits 0 and performs no installs |
| 2 | `grep -rn "10\.0\." --include=*.cs --include=*.sh --include=*.ps1 .` | only `global.json` matches |
| 3 | `for f in bin/review-bundle bin/review-log bin/smoke-workflow bin/evals-*; do printf '%s ' "$f"; /usr/bin/time -p "$f" --help 2>&1 >/dev/null | grep real; done` | each ≤ 20 ms, 5 warm runs, median |
| 4 | `PATH=$PATH` with clang hidden; `./install.cs` | exit 0, every `bin/*` still executes, install prints `degraded: <tool> (no native toolchain)` |
| 5 | `./install.cs --oracle` | every tool reports `match`; exits 1 and names the tool on any mismatch |
| 6 | `bin/smoke-workflow --case T0` | exit 0, `1/1 cases passed` |
| 7 | `./install.cs --doctor` | exit 0 on macOS with dotnetup; each check names the fact it read |
| 8 | `grep -rn "python3\|\.py\b" bin src install.cs setup.sh` | no matches |

`--oracle` is a new `install.cs` mode that runs the frozen fixtures (below) through the
C# tools and compares against recorded digests. It is the executable form of item 5.

## Non-goals

- **Windows.** Symlinks need elevation, `{env:HOME}` is unset, and Native AOT wants the
  MSVC linker. WSL2 covers it. Revisit only on real need.
- Deleting a Python predecessor before its C# replacement passes `--oracle`.
- Committing binaries. `bin/` is generated.
- Making `setup.sh` C# — it bootstraps the SDK that runs C#.

## P0 — spike (DONE — see `docs/dotnetup-notes.md`)

Verified on this machine, dotnetup `0.3.0-preview.1`:

- Bare `dotnetup sdk install` **does** read `global.json` → installed 10.0.403, spec recorded
  as `source: GlobalJson`, `versionOrChannel: "10.0"`. `latestFeature` → channel `10.0`.
- **`dotnetup list --format Json` exists.** The plan previously said it did not and told
  `install.cs` not to scrape; there is JSON, so probes read `installSpecs`/`installations`.
- **`dotnetup env script`** prints an eval-able block for the *current* process — this
  replaces the planned `exec dotnetup dotnet -- run install.cs` hand-off.
- The managed install root is `~/Library/Application Support/dotnetup/dotnet` — **spaces**.
- Hand-off verified both ways: `eval "$(dotnetup env script)" && ./install.cs --check` and
  `dotnetup dotnet -- run install.cs --check` both exit 0 under SDK 10.0.403.
- Repo now has `global.json` (`10.0.100`, `rollForward: latestFeature`); both the system SDK
  (10.0.401) and the dotnetup SDK (10.0.403) satisfy it.

## P1 — bootstrap, pinning, layout (no tool changes)

- `global.json`: `{"sdk":{"version":"10.0.104","rollForward":"latestFeature"}}`.
  `rollForward` is a **host policy for SDK selection**, not an installer channel; dotnetup
  derives its channel from `global.json` via its own mapping. P0 confirms the mapping.
- `setup.sh` (POSIX sh, ~90 lines): detect OS/distro; require `curl`; install dotnetup from
  `https://aka.ms/dotnetup/get-dotnetup.sh`; `cd` to repo; `dotnetup sdk install`;
  then report missing `git`/`clang` with the exact command per detected manager (Arch:
  `pacman -S --needed git clang zlib`; Debian: `apt-get install -y git clang zlib1g-dev`;
  macOS: `xcode-select --install`, which is interactive — print, never run).
  `--install` executes them. Then bring the managed toolchain into the **current** process
  with `eval "$(dotnetup env script)"` and run `./install.cs`. Quote every path: the
  managed root contains spaces.
- `install.cs`: create `bin/` and the config dirs **before** the symlink pass; do not skip
  an absent managed entry (current `install.cs:64-67` skips, which is why a fresh clone
  would never link `bin`).
- `.gitignore`: `bin/`, `.build/`, `*.dSYM/`, `*.dbg`. Added only when the tree is still
  fully tracked, so nothing is silently lost.
- README: Omarchy bootstrap becomes `./setup.sh`.

Done-when: item 1.

## P2 — build orchestration in `install.cs`

`BuildTools()`:
- Stamp content = `sha256(source)` + `dotnet --version` + `native|shim`. An SDK bump or a
  degradation/recovery forces a rebuild; source-only stamping would miss both.
- Exclusive lock on `.build/<name>.lock`; two concurrent installs must not share an output
  directory.
- Publish to `.build/out/<name>/` with an explicit `-p:PublishAot=true -c Release`
  (**never** rely on the in-source `#:property` alone). Per-tool, not per-run.
- Validate the output is a single native executable (no `.runtimeconfig.json`, no
  `*.dll` beside it). If not, treat as failure.
- Install with a same-volume `rename` over `bin/<name>` — never a copy, which can leave a
  half-written executable that the next run accepts as present.
- Exit code mapping: publish failure is non-zero unless we deliberately degraded.

Degradation, precisely:
- Probe the toolchain by attempting one minimal AOT publish (P0 records the command).
  `which clang` is insufficient (AOT wants Apple clang; `zlib` is not a PATH executable,
  so probe `zlib.h`/`libz`, not `which zlib`).
- **Missing toolchain** → write `bin/<name>` shim with an **absolute** path baked in at
  write time: `exec dotnet run --file "$REPO/src/<name>.cs" -- "$@"`. It must work from any
  cwd, because callers run it from the repo under review.
- **Compile error** → leave the existing `bin/<name>` untouched, print the compiler
  diagnostics, exit non-zero. Never fall into the shim path; that would replace a working
  tool with a broken one.
- Stamp records `shim`, so installing clang later rebuilds instead of being treated as
  current.

`--check` must not build. `--copy` must not copy generated `bin/` (it would go stale);
either republish-on-stamp or exclude it explicitly.

`--doctor` hardening (each check names the fact it reads):
- SDK: `dotnet --version` against `global.json` major/minor.
- resolved `dotnet` path, and whether it is under `~/.dotnetup` or system.
- `which roslynk` vs the `{env:HOME}`-substituted path `opencode.json` expects.
- toolchain: the P0 AOT probe, reported as a note (native is an optimization).
- `python3`: **hard requirement until P6**, because `review-log` etc. are still Python.
  Demoting it now would show green on a machine whose ledger cannot be written.

Done-when: items 3 and 4.

## P3 — `review-bundle`

Replace only after `--oracle` passes for this tool.

Corrected compatibility surface (plan-review caught four wrong claims):
- Exit codes: `2` = usage, unknown flag, `--show` without path, or `rev-parse
  --is-inside-work-tree` failing. `4` = a failure inside `git_ok` only. `3` = over-limit,
  **stdout still prints the path**. `git show HEAD:<rel>` failure is *not* fatal — it
  renders `absent at HEAD`. `hash-object` failure is recorded in the baseline JSON, not
  raised.
- Secret pathspecs apply to `diff --stat` and `diff` **only**. `diff --name-only HEAD` runs
  without them — that is what produces the "secret path; excluded" omitted lines.
- `20 MiB` limit counts `02/03/04/05/99` and excludes `00-status.txt` and `01-diffstat.txt`.
- Inherit the ambient environment and *add* `GIT_OPTIONAL_LOCKS=0`; do not replace the env.
- Match Python's `text=True` decoding (locale + universal newlines) or CRLF diffs diverge.
- Default temp dir must be **portable**: `$OPENCODE_TMP`, else `$TMPDIR/opencode`, else
  `/tmp/opencode`. The literal `/private/var/folders/...` was macOS-only and made the tool
  die on Linux with `PermissionError: '/private'`. Already fixed in the Python originals
  (measured: works on Ubuntu with no env var), so the port must match the **new** rule.
- No regex in this tool, so `RegexOptions.Compiled` is irrelevant here. JSON via source-gen
  context (needed for the AOT path; reflection still works under `dotnet run`).

## P4 — `review-log`

- Malformed lines are `strip()`ed and blanks dropped — not kept verbatim.
- Key order must match `json.loads`/`json.dumps` round-trip, and **include `resolved_at`**
  on resolve.
- `model` falls back to `--models` when `--model` is empty.
- Number formatting: Python emits `0.0`; `System.Text.Json` emits `0`. Use a parser-based
  comparison in the oracle, or format explicitly.
- Timestamps are `isoformat()` with `+00:00` and microseconds. A `Z` suffix is skipped by
  `scoreboard.py:63-66` until P5, so do not "improve" the format.
- Atomic full-file rewrite via `<path>.tmp` + replace.

## P5 — `smoke-workflow`

- `--timeout` default **900** (docstring says 1200; the argparse wins).
- Root validation allows `base`, `base + "-"`, `base + os.sep` — not a raw prefix check.
- Tier scanner stops on `subagent`, `task`, `edit`, `write`, `patch` only.
- Agent list printed as Python `repr`; keep that shape or the pass/fail text changes.
- Fixture modes: scripts `0o755`, `AGENTS.md` `0o644`. `run()` sets `PWD`.
- Unit-test the tier regex, the tool stop-list, and root validation against recorded
  inputs; a live `--case T0` is an integration check, not the equivalence proof.

## P6 — `evals/`

- Keep `evals/run.sh`, `evals/score.py`, `evals/cost.py`, `evals/scoreboard.py` as **thin
  exec wrappers** onto `bin/evals-*`, so `evals/README.md:13-23,44-47,115-116` and
  `evals/2026-10-18-gate-model-decision.md:46-49` keep working. Deleting them requires
  updating both docs in the same phase; wrappers are cheaper and safer.
- `score.py` resolves `cases/` from the **script location**. A binary in `bin/` will not
  find `evals/cases/`; under the shim, `AppContext.BaseDirectory` is the shadow build dir.
  Bake the repo root at build/shim-write time via `CallerFilePath` or an absolute constant.
- Preserve `EVAL_WORK_ROOT`, `EVAL_CASE_TIMEOUT` (default 900), `EVAL_RUN_ID`, and the
  `$$`-style pid suffix that keeps concurrent runs from sharing checkouts
  (`Environment.ProcessId`).
- `run.sh` calls `cost.py` at the end and ignores failure — keep the call and its tolerance.
- Keep `git clone --shared --no-checkout` (README states the safety property) and the exact
  prompt bytes; changing either changes scores.
- Timeout: `perl alarm` yields SIGALRM → rc 142. `Process.Kill()` gives SIGKILL → 137.
  Downstream only requires non-zero, but if rc parity matters send signal 14. Decide and
  record it in the oracle.
- `pkill -f "$WORK/co/.*/Poly.Mcp"` is a pattern; preserve it verbatim (Unix-only, matches
  the Windows non-goal).
- `scoreboard`: `Microsoft.Data.Sqlite` connection string uses `Mode=ReadOnly`, not
  `mode=ro`. AOT compatibility unverified — if it fails, scoreboard stays framework-
  dependent and is **removed from "all native"** in the goal and in done-when 3.

## P7 — remove Python

Delete Python sources, flip `bin/` to generated, update `AGENTS.md`, `README.md`,
`evals/README.md`. Promote `python3` in `--doctor` from hard to absent.

## Oracle

Freeze the corpus first; live repos and live databases are not an oracle.

- Fixture repos: clone `~/Projects/Poly/Poly` and two small synthetic repos to
  `.build/fixtures/`, and pin them. Synthetic cases must cover: secrets present, untracked
  files, binary files, a non-UTF-8 file, a clean tree with no changes, and a diff > 1500
  lines (chunking).
- `review-bundle`: record for each fixture — bundle relative file tree, each file's bytes
  (normalising bundle dir name and `05-baseline.json`.`timestamp`), plus exit code and
  stderr for: no args, unknown flag, `--show` without path, non-git dir, `--baseline`,
  `--show`, and an artificially over-limit bundle (rc 3).
- `review-log`: append + resolve on a copy of the ledger; compare parsed JSON (not bytes)
  ignoring `id`, `ts`, `resolved_at`; compare stdout shape (12 hex) and exit codes 0/1/2.
- `cost`/`score`: point at a **real run directory** created by `run.sh`, not
  `evals/canary-2026-10-18/` — that directory is a permission canary and contains neither
  `stats-*.json` nor `results/<id>/*.txt`, so comparing there would pass while testing
  nothing.
- `scoreboard`: copy `opencode.db` to a fixture and pin the window (`--days`/`--all`
  equivalent) so `time.time()` cannot make two runs differ.
- `evals-run`: oracle *without* calling `opencode` — validation exits, `WORK` layout,
  produced prompt bytes, trailer line, timeout rc.

Red test first: `--oracle` must fail with `review-bundle: mismatch` before
`src/review-bundle.cs` exists.

## Swap discipline

The workflow must never have a window where `~/.config/opencode/bin/review-bundle` is
missing or broken:

1. `bin/<name>` stays the Python script throughout.
2. C# candidate publishes to `.build/out/<name>/`, and runs directly from there for the
   oracle.
3. On `--oracle` pass for that tool: `rename` candidate over `bin/<name>`, and
   `git rm --cached bin/<name>` — never delete the live file first.
4. `bin/` is gitignored only when no tracked file remains inside it.

## Test environments

| env | RID | role | status |
| --- | --- | --- | --- |
| macOS arm64 (host) | `osx-arm64` | primary dev | verified: dotnetup, SDK 10.0.403, `install.cs`, `review-bundle` |
| Ubuntu 26.04 arm64 (Parallels VM) | `linux-arm64` | **primary Linux gate** | verified: bootstrap, 6 symlinks, `review-log`, `review-bundle`, `dotnet` on PATH |
| Arch / Omarchy | `linux-arm64` | secondary distro branch | untestable (M3 Pro unsupported); not optimised for |

Verified on the VM so far: `setup.sh` end-to-end (exit 0), `dotnetup` +
`global.json` → SDK 10.0.403, `install.cs --doctor` (blocking vs advisory split),
`install.cs` symlinking 6 entries, idempotent `--check`, `review-log` append, and
`review-bundle` producing a bundle with no `OPENCODE_TMP` set.

Not yet verifiable there: `smoke-workflow` (needs `opencode` on PATH) and the MCP server.
Still open: Native AOT publish on `linux-arm64` — the P2 build step does not exist yet.


**The Parallels shared mount (`/media/psf/Home`, `fuse.prl_fsd`) was measured, not assumed.**
Symlinks of files and directories work, and `mv` over an existing file works. So the mount
is not the symlink barrier I first claimed. It is still not where the tests should run:

- everything appears owned by `root` (`user_id=0` in the mount options), so file modes and
  ownership are not the guest's, and `git status` cannot be trusted for mode changes;
- `nosuid` is set (not `noexec`, so binaries do run);
- it is FUSE, so it is slow — and an AOT build writes a lot.

Copy to ext4 with `rsync -a` and `chown -R parallels:parallels` before running anything.

Ubuntu bootstrap (also the `setup.sh` apt branch):

```sh
sudo apt-get install -y git curl clang zlib1g-dev libicu-dev
curl -fsSL https://aka.ms/dotnetup/get-dotnetup.sh | bash
export PATH="$HOME/.dotnetup:$PATH"
cd ~/dotfiles && dotnetup sdk install && eval "$(dotnetup env script)"
```

`libicu-dev` is a runtime need, not an AOT need. Ubuntu's apt `dotnet-sdk` lags a feature
band behind, which is the case dotnetup exists to remove.

Verify in the VM, most-expensive-to-discover-late first:

1. `--doctor` on a non-Mac — no `~/Library/...`, no `xcode-select` expectations.
2. `uname -m` = `aarch64` and `dotnet --info` RID = `linux-arm64`. An emulated x64 SDK
   makes everything downstream a false pass.
3. Symlink round trip: `--copy`, then link mode; backups land, links resolve. Settles
   `ReparsePoint` vs `LinkTarget` on Linux.
4. The `pwd -P` shim trick through the `~/.config/opencode/bin` symlink.
5. AOT publish; then remove `clang` and confirm degradation instead of destruction.
6. `setup.sh` must not assume `shasum` (macOS); Ubuntu may only have `sha512sum`.
7. `opencode` and `roslynk` must exist for `linux-arm64`. **Unverified** — `smoke-workflow`
   needs `opencode` on PATH and `dotnet tool install -g roslynk` needs an arm64 package.
   The installer can work while the workflow cannot; treat these as separate gates.

## Risks

- `dotnetup` is public preview; P0 pins the surface (see `docs/dotnetup-notes.md`),
  `global.json` pins the SDK, and probes read `dotnetup list --format Json` rather than
  parsing human-readable text.
- Publish cost ≈ 6 s cold per tool, ≈ 1 s incremental; 7 tools ≈ 40 s first install.
- Native AOT constraints: source-gen JSON, no `RegexOptions.Compiled`, no dynamic loading.
- Partial migration is the standing risk; swap discipline exists for it.

## Verification

```
./setup.sh                      # idempotent
./install.cs --check            # config symlinks, does not build
./install.cs                    # build + link
./install.cs --oracle           # equivalence gate
./install.cs --doctor           # probes
bin/smoke-workflow --case T0
```
