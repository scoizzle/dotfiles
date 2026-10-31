---
name: roslynk-rules
description: Local rules for Roslynk when working in a C#/.NET solution with this config — which Roslynk tools read-only review agents may use, and why get_diagnostics is a compile check rather than a test run. Use when the task touches *.cs, *.razor or *.cshtml in a repo that has a .sln or .slnx.
license: MIT
compatibility: opencode
metadata:
  upstream: https://github.com/mrpmorris/Roslynk/blob/master/skills/roslynk/SKILL.md
  upstream-license: MIT
---

# Roslynk — local rules

Upstream's entire skill is one line, vendored here verbatim (MIT):

> Follow server instructions and tool schemas.

That is deliberate: the Roslynk MCP server injects its own tool documentation, and the
upstream skill exists only to point at it. **Do not copy the long example prompt from the
Roslynk README into `AGENTS.md`** — it duplicates the MCP `instructions` and this file, and
costs every session the context whether or not C# is involved.

This file adds only what neither the server nor the README covers: how Roslynk interacts
with this config's review gates.

## Gate: only with a solution

Roslynk is configured globally (`opencode.json`) and is the default for C# work;
no repository has to opt in. Before using it:

1. Confirm a `.sln` or `.slnx` exists — at the git toplevel, within two levels, or
   one level above the working directory. `.cs` files alone are not a
   trigger — dotfiles, file-based apps (`install.cs`) and generated code have no
   solution.
2. Call `open_solution` with the **absolute** path. The returned `solutionId` is the handle
   every other tool needs.
3. If no solution exists, or `open_solution` is unavailable or the load fails, say so in one
   line and fall back to normal file reads. Do not silently pretend Roslynk answered.

## Read-only agents: read-only tools only

`review-light`, `review-deep`, `plan-review-deep` and `second-opinion` are read-only by
this repo's `AGENTS.md`. Roslynk's write tools are therefore **out of scope for them**,
even though the upstream instructions say to prefer Roslynk over hand edits.

Allowed for read-only agents:

`get_solution_status`, `get_diagnostics`, `get_symbol`, `get_symbol_body`, `get_members`,
`search_symbols`, `find_definition`, `get_expression_info`, `find_references`, `find_reads`,
`find_writes`, `get_callers`, `get_callees`, `find_implementations`, `get_type_hierarchy`,
`find_dead_code`, `find_dead_conditionals`, `multi_query`, `get_code_actions`,
`open_solution`, `reload_solution`.

Forbidden for read-only agents — these write to disk:

`apply_code_fix`, `apply_code_action`, `apply_patch`, `rename_symbol`, `rename_parameter`,
`change_signature`, `extract_method`, `remove_unused_usings`.

`reload_solution` is read-only on disk but must still only be called when the user
explicitly asks; the file watcher normally handles edits.

## Compile check is not a test run

`get_diagnostics` replaces `dotnet build` for finding compile errors and analyzer warnings,
and it is cheap enough to call once at the end of a task rather than after every edit.

It is **not** a substitute for tests. This repo's workflow requires the changed-area tests
and then the full suite; a clean `get_diagnostics` proves the code compiles, nothing more.
Reviewers "never rebuild", but `get_diagnostics` is a read and is fine for them.
