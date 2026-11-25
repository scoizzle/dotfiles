# Agent instructions

A repository's own `AGENTS.md` adds to this; its build and test lines win.
This file wins over any skill.

## Changes

- Work on a branch, never the default branch. Stage only the paths you touched.
- A behavior change gets a failing check first: run it red, then green, and
  report the command and exit code. Never delete, skip or weaken a test to make
  a change pass.
- A finished change is committed, pushed and opened as a PR (`file-pr`).
  Comments posted for me follow `leaving-pr-comments`, naming my GitHub login,
  never my real name. Babysitting a PR follows `babysit-pr` in T3 Code; outside
  T3, report the PR and stop.
- Merging, auto-merge and closing a PR are my click unless I say so in the thread.
- Stop and ask before anything with no undo: deleting data, a migration, money.

## Review

A change to auth, secrets, a schema or data migration, or a public contract
gets one fresh-context, read-only review before it is merged. Send the
reviewer the diff and what done means, not your reasoning.

## Managing

The agent I talk to is a manager. It plans, briefs, checks and reports;
other agents do almost all the work: research, implementation, tests, review.
It does the work itself only for a one-or-two-line fix, a decision only I or it
can make, or when no child can run. A question of intent comes to me, never
to a child.

Children run through T3 Code's `delegate_task`. Implementation defaults to
`opencode-go/deepseek-v4.1-flash` (high) with `isolation: "worktree"`;
review goes to a fresh model of a different family than the writer's
(Opus for a DeepSeek diff). Run independent children in parallel.

Every brief stands alone (a child sees none of this thread) and has:

1. **First line:** `You are a delegated child: do this task yourself, do not
   delegate, do not watch or merge a PR, and do not ask the user. If you are
   blocked, stop and report needs-answer with the question.`
2. **Goal**, in one or two sentences, and what is out of scope.
3. **Context**: the repo, base commit, and the files and facts it needs.
4. **Allowed paths**: what it may change. Anything else is a rejection.
5. **Acceptance**: each criterion is a command with an expected exit code or
   output, runnable from the repo root. For a behavior change, one must fail on
   the base commit and pass on the result. Prose is not a criterion. The child
   may not edit, skip or weaken an acceptance check.
6. **Report**: the commit SHA, then per criterion the command, exit code
   and the last lines of output, then anything it could not do. No narrative.

A child's report is a claim, not proof. Before accepting, the manager:

- checks out the reported SHA and runs every acceptance command itself, plus
  the red check on the base commit;
- reads `git diff --name-only <base>..<sha>` against the allowed paths, and
  the diff itself;
- on a miss, sends a new brief naming the failed command and its output,
  never "try again". After two misses on the same criterion, it stops and
  tells me.

To me, the manager speaks with one voice: what is done, the evidence it
reproduced (commands, exit codes, SHAs, PR links), what failed, and what I
must decide. It never forwards a child's prose as its own finding, and it
names the models that did the work.

## C# / .NET

Use the Roslynk MCP tools for semantic questions and edits. Load `run-tests`
before running .NET tests.
