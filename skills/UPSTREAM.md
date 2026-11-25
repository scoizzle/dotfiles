# Vendored skills

Copied verbatim (byte-identical) and pinned in `UPSTREAM.sha256`; CI runs
`shasum -a 256 -c UPSTREAM.sha256` here. Do not edit them; put a difference in
`AGENTS.md`.

| Skills | From | License |
| --- | --- | --- |
| `run-tests`, `platform-detection`, `test-anti-patterns`, `assertion-quality` | [dotnet/skills](https://github.com/dotnet/skills) `2877c712edc20643b72f64e2983b168e6661d607`, `plugins/dotnet-test/skills/` | MIT, `UPSTREAM-LICENSE-dotnet` |
| `file-pr`, `leaving-pr-comments`, `babysit-pr`, `modernize`, `takeover` | [t3dotgg/tstack](https://github.com/t3dotgg/tstack) `11e37a74d0a6868c121cd0910ab2b3bd9873b92a`, `skills/` | MIT, `UPSTREAM-LICENSE-tstack` |

Not vendored: `babysit-pr/scripts/pr-wait` (T3's `watch_pull_request` does that
job), and tstack's `full-send`, `full-stop`, `council` and `sol-loop`.

Known gaps:
- `test-anti-patterns` and `assertion-quality` may name sibling skills that are not installed
  here; that is a report, not a failure.
- `modernize` triggers on "rebase a pr", so a plain rebase gets its full procedure.
- `leaving-pr-comments` puts `<user>` in a public comment: use the GitHub login, never a real
  name (`AGENTS.md` wins).

To re-vendor: download the same paths at a new commit, read the diff, then re-pin from this
directory with `shasum -a 256 <skill>/<file> ...` and update the table.
