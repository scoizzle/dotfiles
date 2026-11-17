# Vendored skills from dotnet/skills

Four skills copied verbatim (byte-identical) from [dotnet/skills](https://github.com/dotnet/skills)
at commit `2877c712edc20643b72f64e2983b168e6661d607` (2026-11-12). MIT; the upstream notice is
`UPSTREAM-LICENSE` in this directory.

Do not edit them here. A local change gets overwritten by the next re-vendor, and the upstream
copy is the one their evaluator measures. If a repository needs different behaviour, put it in
that repository's `AGENTS.md`, or use the overlay convention the upstream skills already read
(`.agents/skill-overlays/<plugin>/<skill>.md` with matching `core:`/`binding-revision:`/`mode:`
frontmatter).

## What is here, and why

| Skill | Upstream path | Why |
| --- | --- | --- |
| `run-tests` | `plugins/dotnet-test/skills/run-tests` | The exact `dotnet test` command, filter syntax, and output mode for classic, VSTest, bridged MTP, and native MTP. Under Microsoft.Testing.Platform the obvious command is wrong. |
| `platform-detection` | `plugins/dotnet-test/skills/platform-detection` | Which platform and framework a repo uses, resolving `global.json` and `Directory.Build.props` precedence. `run-tests` calls it by name, so both travel together. |
| `test-anti-patterns` | `plugins/dotnet-test/skills/test-anti-patterns` | Evidence for the test-cleanup rule in `AGENTS.md`: duplication, tautological or missing assertions, swallowed exceptions, order-dependent flakes, magic values. |
| `assertion-quality` | `plugins/dotnet-test/skills/assertion-quality` | Whether a named "survivor" test actually asserts anything, which is what a duplicate removal has to show. |

`platform-detection/references/command-mode.md` ships with its skill and is vendored too.

`UPSTREAM.sha256` pins every vendored file. `tests/skills.py` fails when a pinned
file is edited in place, a pinned file goes missing, a vendored skill gains an
unpinned file, a skill header does not match its directory, or a skill names a
`references/` path it does not ship.

## Known gaps

- `test-anti-patterns` and `assertion-quality` read a reference-only `test-analysis-extensions`
  catalog for per-language rules. That bundle is not vendored. Both skills say to report the
  missing reference and fall back to their built-in rules, so a run will name the gap and still
  work.
- `test-anti-patterns` routes several non-overlapping questions to sibling skills that are not
  installed here (`coverage-analysis`, `test-gap-analysis`, `test-tagging`, `crap-score`,
  `writing-mstest-tests`, `test-smell-detection`). Routing to a missing skill is a report, not a
  failure; the answer for those questions is "not installed".
- Upstream's numbers come from their own evaluator (Sonnet-5 executor, GPT judge, their
  scenarios). They justify vendoring; they do not predict results here.

## Re-vendoring

Pick a new commit, download the same paths, re-pin, and update the table. Verify
identity before committing:

```sh
SHA=<new commit>
B="https://raw.githubusercontent.com/dotnet/skills/$SHA/plugins/dotnet-test/skills"
for f in run-tests/SKILL.md platform-detection/SKILL.md \
         platform-detection/references/command-mode.md \
         test-anti-patterns/SKILL.md assertion-quality/SKILL.md; do
  curl -fsSL "$B/$f" -o "skills/$f"
done
# after confirming the diff, re-pin with the same five paths:
shasum -a 256 run-tests/SKILL.md platform-detection/SKILL.md \
  platform-detection/references/command-mode.md \
  test-anti-patterns/SKILL.md assertion-quality/SKILL.md
python3 tests/skills.py
```

Read the diff of a re-vendor like any other change: a skill may gain a dependency on a sibling
that is not installed, or change its trigger description in a way that misfires.
