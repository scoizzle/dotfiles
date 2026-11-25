# Agent instructions

A repo's own `AGENTS.md` adds to this and its build and test lines win. This
file wins over any skill.

## Changes

- Work on a branch, never the default. Stage only the paths you touched.
- A behavior change starts from a failing test: red, then green, with the
  command and exit code. Never delete, skip or weaken a test to pass.
- Finished means committed, pushed and opened as a PR (`file-pr`); comments
  follow `leaving-pr-comments` with my GitHub login, never my name.
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

A brief stands alone: that first line, the goal and what is out of scope, the
repo and commit, the allowed paths, and acceptance as commands with expected
exit codes, including a test that fails before the change. The child reports
its SHA and each command's exit code and output, nothing else.

A report is a claim. Rerun the acceptance commands at that SHA in a scratch
worktree, check the diff stays in the allowed paths, and re-brief with the
failing output; after two failures, stop and tell me. Then push and open the
PR. Report to me in one voice, with the evidence you reproduced.

## C# / .NET

Use the Roslynk MCP tools for semantic questions and edits. Load `run-tests`
before running .NET tests.
