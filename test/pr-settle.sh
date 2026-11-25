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
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }

mkdir "$tmp/bin"
cat > "$tmp/bin/gh" <<'EOF'
#!/bin/sh
# Fixture gh: every value comes from the environment, set per test.
case "$1" in
  pr)
    case "$2" in
      view)
        if [ "${GH_FAIL:-0}" = 1 ]; then
          echo "gh: could not resolve PR" >&2
          exit 1
        fi
        case "$*" in
          *mergeStateStatus*) printf '%s\n' "${PR_MERGE_STATE:-CLEAN}" ;;
          *mergeable*) printf '%s\n' "${PR_MERGEABLE:-MERGEABLE}" ;;
          *isDraft*) printf '%s\n' "${PR_DRAFT:-false}" ;;
          *url*) printf '%s\n' "${PR_URL:-https://github.com/scoizzle/dotfiles/pull/60}" ;;
          *state*) printf '%s\n' "${PR_STATE:-OPEN}" ;;
          *)
            echo "fake gh: unhandled pr view: $*" >&2
            exit 1
            ;;
        esac
        ;;
      checks)
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
  env PATH="$tmp/bin:$PATH" "$@" sh "$script" 60 > "$tmp/out" 2> "$tmp/err" || rc=$?
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
# Unknown mergeability is a blocker for a one-shot check.
check "unknown-mergeable" 4 PR_MERGEABLE=UNKNOWN
# A draft PR is not ready.
check "draft" 4 PR_DRAFT=true
# gh failure is a clear blocker, not a crash.
check "gh-failure" 4 GH_FAIL=1
# No checks configured counts as green.
check "no-checks" 0 PR_CHECKS=
# A full URL is accepted and resolves the same way.
check "url-arg" 0 PR_CHECKS="pass pass"

# The URL form must be passed through as a repo-qualified target, not treated
# as a bare number. The fake gh records its arguments for this one check.
cat > "$tmp/bin/gh" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$GH_ARGS_LOG"
case "$1" in
  pr)
    case "$2" in
      view)
        case "$*" in
          *mergeStateStatus*) echo CLEAN ;;
          *mergeable*) echo MERGEABLE ;;
          *isDraft*) echo false ;;
          *url*) echo "https://github.com/scoizzle/dotfiles/pull/60" ;;
          *state*) echo OPEN ;;
        esac
        ;;
      checks) echo pass ;;
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
