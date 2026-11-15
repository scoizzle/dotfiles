# Global instructions

Repository `AGENTS.md` files are additive. Their build/test command lines win.

## Default workflow

You do the work. Do not dispatch a writer to avoid editing.

Before the first edit, name the kind of change:

- **Ordinary.** Do it. A behavior change gets a failing check first. Run it red, then green. Record the command and the exit code.
- **Sensitive.** Auth, secrets, credentials, a schema or data migration, or a public contract: `agents/*`, `policy/*`, `*opencode.json`, `*global.json`, `*.csproj`, `*.sln`, `*.slnx`, `*Dockerfile*`, `memory/core/*`. A CI workflow is not sensitive. Write the outcome, the done-when, and the red check in a few lines before editing. After the change, one independent read-only review (`agents/review-deep.md`), or say that no second model was available. Stop and ask before a change with no undo: a migration, a delete, or money.

Green means the commit you name and a tree whose `git status` you have read. Never delete, skip, or weaken a test. If a test's expectation was wrong, say so and say why. A nit that does not break the done-when is reported, not fixed.

Dispatch only when it earns the tokens:

- A broad lookup (a repo map, a multi-file grep) may go to the explore agent. It is read-only and returns findings and sources. Do not paste the repo into this context.
- One reviewer, for a sensitive change, when the user asks, or after the same check has failed twice. It does not edit and does not rebuild. A second reviewer is not the default.

If dispatch is unavailable, do the work yourself and say so. Do not block an ordinary edit on a missing dispatcher.

## Safety

- Do not stage, commit, or push unless asked. `git push` is ask. Force, delete, mirror, and `+refspec` pushes are denied.
- Keep diffs minimal and consistent with the surrounding code.
- The explore agent and the review agents are read-only.
- A one-click revert can proceed. Name cleanup before landing shared state or auth. Wait for a person when there is no undo.

## Model choice

Use the session model. A lookup may use a cheaper model when one is already configured. A sensitive review should use a different model family than the one that wrote the diff, when one is available. If it is not, say so and continue. Do not stop to ask about fallbacks.

## Memory

Durable memory is `~/.config/opencode/memory/` (this repo's `memory/`, linked
by `install.cs`).

Before heavy work, read `~/.config/opencode/memory/INDEX.md`, the bookshelf: a
blurb per file. Load a memory file only when its blurb matches the task. Dated
files under `memory/learnings/` are local, so the index names the pattern; when
it matches (a task that could repeat an earlier failure, command, or path), read
the newest `learnings/YYYY-MM-DD.md` files.

Never edit `memory/core/**`: conventions and safety. `opencode.json` denies
`edit` there (edit, write, patch), but a shell command is matched as text, so
this rule is what forbids a redirection into core.

Durable discoveries go to `memory/learnings/` as short constraints (`never`,
`known`, `derived`, with a `harness`, `loop`, or `graph` tag) under the version
header in `memory/learnings/README.md`: who, when in UTC, session or context
id, and source.

`dream` stages its output in `memory/learnings/pending/`, which agents do not
read; a person promotes it with `~/.config/opencode/bin/dream --promote`. Read
`memory/learnings/working.md` first when it exists, and open any dated file its
`source:` line does not name; never write it. Do not rewrite memory mid-task as a
substitute for finishing the work; see `docs/memory-and-dreaming.md`.

## C# / .NET work

Roslynk is configured globally and assumed available. Before the first C# read or
edit, find the solution and open it:

```sh
git rev-parse --show-toplevel      # then look for *.sln / *.slnx at depth <= 2
```

Look in the toplevel, one level up, and in the nearest ancestor that holds one.
Call `open_solution` with the absolute path; every other tool needs its
`solutionId`. Load the `roslynk-rules` skill once per session before the first
C# edit.

Use Roslynk instead of the mechanical alternative:

| Instead of | Use |
| --- | --- |
| grep for a symbol by name | `search_symbols`, `find_definition` |
| reading a whole file to find a member | `get_members`, `get_symbol_body` |
| grep for callers or implementers | `find_references`, `get_callers`, `find_implementations` |
| `dotnet build` to check compile state | `get_diagnostics` |
| hand-editing a rename or signature change | `rename_symbol`, `change_signature` |

Read files only for context Roslynk cannot provide, and for non-C# files. If no
solution exists (file-based apps such as `install.cs`, `.csproj`-only trees) or
`open_solution` fails, say so in one line and use normal file reads. Never imply
Roslynk answered when it did not.

Read-only agents (`explore` and the review agents) use only the read-only Roslynk tools listed in
the `roslynk-rules` skill, never the ones that write.

`get_diagnostics` is a compile check, not a test run. Tests still go through the
repo's test command, and a repo `AGENTS.md` may name a build command that must
still be run.
