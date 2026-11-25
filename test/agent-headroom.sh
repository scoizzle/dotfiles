#!/bin/sh
# Pace-math and warning tests for bin/agent-headroom.
# Fixtures use AGENT_HEADROOM_JSON_FILE and AGENT_HEADROOM_NOW so no network
# or real clock is needed. Epochs are fixed UTC instants in November 2026.
set -u

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
script="$here/../bin/agent-headroom"
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

fails=0
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }

fixture() { # fixture <path> <weekly percent>
  printf '{"usage":{"rolling":{"status":"ok","percent":1,"resetsAt":"x"},"weekly":{"status":"ok","percent":%s,"resetsAt":"x"},"monthly":{"status":"ok","percent":1,"resetsAt":"x"}}}\n' "$2" > "$1"
}

check_exit() { # check_exit <name> <expected exit> <epoch> <weekly percent>
  json="$tmp/$1.json"
  fixture "$json" "$4"
  rc=0
  AGENT_HEADROOM_JSON_FILE=$json AGENT_HEADROOM_NOW=$3 OPENCODE_API_KEY=test \
    sh "$script" > "$tmp/out" 2> "$tmp/err" || rc=$?
  if [ "$rc" -eq "$2" ]; then pass "$1"; else
    fail "$1: exit $rc, want $2"
    sed 's/^/  /' "$tmp/err"
  fi
}

check_exit "wed-1200-weekly-45" 0 1795608000 45
check_exit "wed-1200-weekly-47" 1 1795608000 47
check_exit "mon-0000-weekly-11" 1 1795392000 11
check_exit "mon-0000-weekly-10" 0 1795392000 10
check_exit "sun-2300-weekly-99" 0 1795993200 99

# No key and no fixture: warn and pass.
json="$tmp/tue-warn.json"
fixture "$json" 1
rc=0
( unset OPENCODE_API_KEY AGENT_HEADROOM_JSON_FILE
  AGENT_HEADROOM_NOW=1795485600 sh "$script" > "$tmp/out" 2> "$tmp/err" ) || rc=$?
if [ "$rc" -eq 0 ] && grep -q "warning" "$tmp/err"; then pass "no-key-warns"; else
  fail "no-key-warns: exit $rc, stderr:"
  sed 's/^/  /' "$tmp/err"
fi

check_warn() { # check_warn <name> <epoch> <want: yes|no>
  json="$tmp/$1.json"
  fixture "$json" 1
  AGENT_HEADROOM_JSON_FILE=$json AGENT_HEADROOM_NOW=$2 OPENCODE_API_KEY=test \
    sh "$script" > "$tmp/out" 2> "$tmp/err" || true
  if grep -q "double-rate" "$tmp/err"; then got=yes; else got=no; fi
  if [ "$got" = "$3" ]; then pass "$1"; else fail "$1: double-rate warning $got, want $3"; fi
}

check_warn "tue-0200-warns" 1795485600 yes
check_warn "tue-0500-quiet" 1795496400 no
check_warn "tue-0700-warns" 1795503600 yes
check_warn "sat-0200-quiet" 1795831200 no

if [ "$fails" -ne 0 ]; then
  echo "$fails failing"
  exit 1
fi
echo "all passed"
