---
name: finish-change
description: Use when a change is finished on a thread branch (commit, push, open and link the PR, one watch, hand back), and whenever a dispatch names a bot and a thread id (the notify-bot callback at the end). A delegated child follows the commit, push and link steps but skips the watch and the notify.
license: MIT
compatibility: opencode
---

# Finish a change

A finished change on a thread branch is committed, pushed and opened as a PR
without waiting to be asked (`AGENTS.md` → Safety). Never on the default branch,
and an unreviewed sensitive change stays uncommitted and is reported
`unreviewed`.

## In T3 Code

`t3-code*` tools own the worktree and the link/watch state; `git` and
`gh pr create` (or `pull_request_*`) own the PR.

1. Stage only the paths you touched, commit, `git push`.
2. Open the PR (`gh pr create`, or `pull_request_create`, which links it); its
   title and description follow `file-pr`, and any comment `leaving-pr-comments`.
3. `link_pull_request` with the full URL, as the next call.
4. One `watch_pull_request`, then end the turn. It is never re-armed, and a wake
   is not a merge: merging is the person's click. When the person asks to
   babysit the PR, `babysit-pr`'s T3 section runs the watch loop and the review
   handling; merging stays the person's click.
5. `unwatch_pull_request` before handing the thread back.
6. `t3_worktree_handoff` goes last: it ends the session.

Children never watch.

## Where this wins over the vendored skills

`file-pr`, `leaving-pr-comments`, `babysit-pr`, `modernize` and `takeover` are
vendored verbatim (`skills/UPSTREAM.md`); where they differ, this skill and
`AGENTS.md` win:

- Never merge, enable auto-merge or close a PR unless the person says so in
  this thread; "babysit" or "take over" alone is not that.
- In a `leaving-pr-comments` note, `<user>` is the GitHub login of the account
  posting, never a real name.
- `babysit-pr`'s `pr-wait` is not installed. Outside T3, check the PR once and
  hand back. A GitHub rate limit is reported, not waited out with a sleep.

## Bot callback

A dispatch that names a bot, a thread id and a configured webhook ends with
`notify-bot <BOT> <status> "<one-line summary>" <thread-id>`
(`~/.local/bin/notify-bot` if it is not on PATH). Not from a delegated child; a
notify failure never fails the task; never print the secret.
