#!/bin/sh
# No private PR status script. T3's pull_request_read is the one-shot status and
# watch_pull_request is the watch; AGENTS.md must name the first.
set -u

root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
status=0
for f in bin/pr-settle test/pr-settle.sh; do
  [ ! -e "$root/$f" ] || { echo "FAIL $f is back; use pull_request_read"; status=1; }
done
grep -q 'pull_request_read' "$root/AGENTS.md" ||
  { echo "FAIL AGENTS.md lost pull_request_read"; status=1; }
[ "$status" -eq 0 ] && echo ok
exit "$status"
