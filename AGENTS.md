# Agent instructions

A repository's own `AGENTS.md` adds to this and wins where they differ.

## Changes

- Work on a branch, never the default branch. Stage only the paths you touched.
- A behavior change gets a failing check first: run it red, then green, and
  report the command and exit code. Never delete, skip or weaken a test to make
  a change pass.
- A finished change is committed, pushed and opened as a PR (`file-pr`).
  Comments posted for me follow `leaving-pr-comments`, naming my GitHub login,
  never my real name; babysitting a PR follows `babysit-pr`.
- Merging, auto-merge and closing a PR are my click unless I say so in the thread.
- Stop and ask before anything with no undo: deleting data, a migration, money.

## Review

A change to auth, secrets, a schema or data migration, or a public contract
gets one fresh-context, read-only review before it lands. Do not share your
reasoning with the reviewer; send the diff and what done means.

## Dispatch

Other agents run through T3 Code's `delegate_task`, with the brief holding all
the context a child needs. A delegated child never watches a PR and never
merges.

## C# / .NET

Use the Roslynk MCP tools for semantic questions and edits. Load `run-tests`
before running .NET tests.
