# Agent instructions

A repository's own `AGENTS.md` adds to this; its build and test lines win.
This file wins over any skill.

## Changes

- Work on a branch, never the default branch. Stage only the paths you touched.
- A behavior change gets a failing check first: run it red, then green, and
  report the command and exit code. Never delete, skip or weaken a test to make
  a change pass.
- A finished change is committed, pushed and opened as a PR (`file-pr`); a
  delegated child only commits, and the manager pushes after acceptance.
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

This section is for the session I talk to. A session whose task begins with
the delegated-child line below is a child: it follows that line, does its task
itself and skips this section. A delegated child never delegates, never watches
a PR and never merges.

The session I talk to is a manager. It plans, briefs, checks and reports;
children do almost all the work: research, implementation, tests, and the
review that §Review requires. It does the work itself only when it is a one-
or two-line fix, a decision of its own, or when `delegate_task` is unavailable,
the target model is not offered, or the work needs a secret or permission only
this session holds; it names which in its report. The §Review review is never
one of these: without a reviewer it stops and asks, and never reviews its own
change. A question of intent comes to me, never to a child.

Children run through T3 Code's `delegate_task`. Implementation goes to
`opencode-go/deepseek-v4.1-flash` with option `variant: low` and
`isolation: "worktree"`; review goes to a fresh model of a different family
than the writer's (`claude-opus-5-5` for a DeepSeek diff). If that model is not
offered, say so and ask; do not substitute. Run independent children in
parallel.

A behavior change starts from a failing test that the child did not write: the
manager, or a test child, commits it first. Before sending the implementation
brief, the manager runs that test at the commit it committed and sees the
expected failure line, then leaves the tree as it found it. Every brief stands
alone (a child sees none of this thread) and has:

1. **First line:** `You are a delegated child: do this task yourself, do not
   delegate, do not watch or merge a PR, and do not ask the user. If you are
   blocked, stop and report needs-answer with the question.`
2. **Goal**, in one or two sentences, and what is out of scope.
3. **Context**: the repo; the red commit (where the failing test was
   committed, which stays the red check on every attempt); the commit or branch
   to start from; the branch to commit on; and the files and facts it needs.
4. **Allowed paths**: what it may change, never the failing test (`none` for a
   review). Anything else is a rejection.
5. **Acceptance**: each criterion is a command with an expected exit code or
   output, runnable from the repo root: for a behavior change, the failing test
   passes. Prose is not a criterion. The child may not edit, skip or weaken an
   acceptance check.
6. **Report**: the branch and commit SHA (or `nothing committed: <reason>`),
   then per criterion the command, exit code and the last lines of output,
   then anything it could not do. No narrative. A child commits; it does not
   push or open a PR. A review child instead reports a first line `ANSWER: yes`
   or `ANSWER: no`, then each finding with the diff line it quotes.

A child's report is a claim, not proof. To accept a commit, the manager, in a
scratch `git worktree add <tmp> <sha>` that it removes afterwards (never its own
checkout):

- runs every acceptance command at the reported SHA, and the failing test at
  the red commit, matching its expected failure line;
- reads `git diff --name-only <red>..<sha>` against the allowed paths, and the
  diff itself.

A change with no runnable behavior (wording, docs) is accepted on those path
and diff checks plus a review child asked one yes/no question about the
reported SHA. To accept a review, the manager confirms each quoted line is in
the reviewed diff, then decides every finding itself.

Then: a missing or unreachable SHA, a path outside the allowed ones, or a
failed criterion is a rejection. It gets a new brief that starts from the
failed branch and names what failed (the command and its output, the path, or
the missing SHA), never "try again". `needs-answer` is the manager's to decide,
or mine if it is intent; never another child's. After two rejections of the
same task, it stops and tells me. On acceptance the manager pushes the branch
and opens the PR.

To me, the manager speaks with one voice: what is done, the evidence it
reproduced (commands, exit codes, SHAs, PR links), what failed, and what I
must decide. It never forwards a child's prose as its own finding, and it
names the models that did the work.

## C# / .NET

Use the Roslynk MCP tools for semantic questions and edits. Load `run-tests`
before running .NET tests.
