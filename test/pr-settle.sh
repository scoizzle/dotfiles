#!/bin/sh
# Exit-code tests for bin/pr-settle.
#
# A fake `gh` on PATH serves fixture values, so no network, auth or real PR is
# touched. The cases mirror the exit codes documented in bin/pr-settle.
set -u

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
script="$here/../bin/pr-settle"
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

fails=0
target=60
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }

mkdir "$tmp/bin"
cat > "$tmp/bin/gh" <<'EOF'
#!/bin/sh
# Fixture gh: every value comes from the environment, set per test.
# GH_FAIL_AFTER=n lets the first n calls through, then fails (auth or network
# loss mid-run).
if [ -n "${GH_FAIL_AFTER:-}" ]; then
  echo x >> "$GH_COUNT"
  if [ "$(wc -l < "$GH_COUNT")" -gt "$GH_FAIL_AFTER" ]; then
    echo "gh: HTTP 401: Bad credentials" >&2
    exit 1
  fi
fi
case "$1" in
  pr)
    case "$2" in
      view)
        if [ "${GH_FAIL:-0}" = 1 ]; then
          echo "gh: could not resolve PR" >&2
          exit 1
        fi
        # state, isDraft, mergeable, mergeStateStatus, url as @tsv.
        printf '%s\t%s\t%s\t%s\t%s\n' "${PR_STATE:-OPEN}" "${PR_DRAFT:-false}" \
          "${PR_MERGEABLE:-MERGEABLE}" "${PR_MERGE_STATE:-CLEAN}" \
          "${PR_URL:-https://github.com/scoizzle/dotfiles/pull/60}"
        ;;
      checks)
        if [ -n "${PR_CHECKS_ERR:-}" ]; then
          echo "$PR_CHECKS_ERR" >&2
          exit 1
        fi
        printf '%s\n' "${PR_CHECKS:-pass}"
        ;;
      *)
        echo "fake gh: unhandled pr subcommand: $2" >&2
        exit 1
        ;;
    esac
    ;;
  api)
    printf '%s\n' "${PR_THREADS:-0}"
    ;;
  *)
    echo "fake gh: unhandled command: $1" >&2
    exit 1
    ;;
esac
EOF
chmod +x "$tmp/bin/gh"

check() { # check <name> <expected exit> [env assignments...]
  name=$1
  want=$2
  shift 2
  rc=0
  rm -f "$tmp/count"
  env PATH="$tmp/bin:$PATH" GH_COUNT="$tmp/count" "$@" sh "$script" "$target" > "$tmp/out" 2> "$tmp/err" || rc=$?
  if [ "$rc" -eq "$want" ]; then
    pass "$name"
  else
    fail "$name: exit $rc, want $want"
    sed 's/^/  out: /' "$tmp/out"
    sed 's/^/  err: /' "$tmp/err"
  fi
}

# Ready: green checks, no unresolved threads, mergeable.
check "ready" 0 PR_CHECKS="pass pass"
# Failing checks win over everything except hard blockers.
check "failing" 1 PR_CHECKS="pass fail" PR_THREADS=2
# Cancel counts as a failure.
check "cancelled" 1 PR_CHECKS="pass cancel"
# Pending checks, even with unresolved threads, still report checks first.
check "pending" 2 PR_CHECKS="pass pending" PR_THREADS=1
# Checks fine, unresolved review threads.
check "unresolved-threads" 3 PR_CHECKS="pass pass" PR_THREADS=1
# A merged PR is not a thing to settle.
check "merged" 4 PR_STATE=MERGED
# A closed PR likewise.
check "closed" 4 PR_STATE=CLOSED
# Conflicts block merge.
check "conflicting" 4 PR_MERGEABLE=CONFLICTING
# DIRTY merge state is a conflict even if mergeable lags.
check "dirty" 4 PR_MERGE_STATE=DIRTY
# Unknown mergeability is GitHub still computing, so it is pending, not a
# blocker: a manager should wait, not report a blocker right after a push.
check "unknown-mergeable-pending" 2 PR_MERGEABLE=UNKNOWN
# The merge state can lag at UNKNOWN on its own; that is pending too.
check "unknown-merge-state-pending" 2 PR_MERGE_STATE=UNKNOWN
# Merge state BLOCKED with mergeable lags behind: not ready.
check "blocked-merge-state" 4 PR_MERGE_STATE=BLOCKED
# Branch behind its base is not ready either.
check "behind-merge-state" 4 PR_MERGE_STATE=BEHIND
# A draft PR is not ready.
check "draft" 4 PR_DRAFT=true
# gh failure is a clear blocker, not a crash.
check "gh-failure" 4 GH_FAIL=1
# gh failing after the first call is still a blocker, never "failing checks".
check "gh-failure-mid-run" 4 GH_FAIL_AFTER=1
# No checks configured counts as green.
check "no-checks" 0 PR_CHECKS=
# With --required, gh reports no required checks on the base branch; that is
# "nothing required", not a gh error.
check "no-required-checks" 0 PR_CHECKS_ERR="no required checks reported on the 'main' branch"
# A full URL is accepted and resolves the same way.
target=https://github.com/scoizzle/dotfiles/pull/60
check "url-arg" 0 PR_CHECKS="pass pass"
target=60

# The URL form must be passed through as a repo-qualified target, not treated
# as a bare number. The fake gh records its arguments. Its `checks` answers
# only to --required: without the flag it reports a failing optional check.
cat > "$tmp/bin/gh" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$GH_ARGS_LOG"
case "$1" in
  pr)
    case "$2" in
      view)
        printf 'OPEN\tfalse\tMERGEABLE\tCLEAN\t%s\n' \
          "https://github.com/scoizzle/dotfiles/pull/60"
        ;;
      checks)
        case " $* " in
          *" --required "*) echo pass ;;
          *) echo fail ;;
        esac
        ;;
    esac
    ;;
  api) echo 0 ;;
esac
EOF
rc=0
GH_ARGS_LOG="$tmp/args" PATH="$tmp/bin:$PATH" sh "$script" \
  https://github.com/scoizzle/dotfiles/pull/60 > "$tmp/out" 2> "$tmp/err" || rc=$?
if [ "$rc" -eq 0 ] && grep -q -- "--repo scoizzle/dotfiles" "$tmp/args"; then
  pass "url-repo-flag"
else
  fail "url-repo-flag: exit $rc, args:"
  sed 's/^/  /' "$tmp/args" 2>/dev/null
fi

# Only required checks decide readiness: a failing optional check must not hold
# the PR at 1, which means `gh pr checks --required`.
rc=0
GH_ARGS_LOG="$tmp/args" PATH="$tmp/bin:$PATH" sh "$script" "$target" \
  > "$tmp/out" 2> "$tmp/err" || rc=$?
if [ "$rc" -eq 0 ] && grep -q -- "checks.*--required" "$tmp/args"; then
  pass "required-checks-only"
else
  fail "required-checks-only: exit $rc, args:"
  sed 's/^/  /' "$tmp/args" 2>/dev/null
fi

# Bad input is a blocker with usage, not a silent success.
rc=0
PATH="$tmp/bin:$PATH" sh "$script" not-a-pr > "$tmp/out" 2> "$tmp/err" || rc=$?
if [ "$rc" -eq 4 ] && grep -q "usage" "$tmp/err"; then
  pass "bad-arg"
else
  fail "bad-arg: exit $rc"
  sed 's/^/  /' "$tmp/err"
fi

if [ "$fails" -ne 0 ]; then
  echo "$fails failing"
  exit 1
fi
echo "all passed"
