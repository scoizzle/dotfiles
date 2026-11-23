#!/bin/bash
# Writer eval: runs a writer agent against a bugged fixture and scores whether
# it fixed the production code without editing the tests that define the oracle.
#
#   ./run-writer.sh -m opencode-go/deepseek-v4.1-flash#low
#   ./run-writer.sh -m opencode-go/deepseek-v4.1-flash#low -c mcp-nav-rendering --runs 3
#
# The writer runs as the `build` agent, the default agent whose pin this eval
# measures; -a names another. -m overrides that agent's configured model.
#
# Every case in evals/writer-checks.json clones the fixture repo at its base
# commit, applies the case patch (which reverts only the production files, so
# the fix's own tests stay in the tree and fail), commits that state inside the
# scratch clone, and runs the writer there. A run passes only when the check
# exits 0 and no protected path differs from the committed bugged state.
#
# EVAL_WRITER_CMD replaces the `opencode run` invocation: it is run in the
# scratch clone with the prompt as its one argument. tests/eval_writer.py uses
# that to exercise this script without a model.
#
# --blind gives the writer only the case's claim, the check and the protected
# paths, not the cause notes (with them every arm scored 18/18, Phase 6).
# --lead MODEL runs a lead first, as `build` in the same clone with shell, told
# to diagnose, not edit, and write .eval-brief.md per skills/implementor-brief;
# the writer then gets that brief (blind). A lead that edits or writes no brief
# fails the run. EVAL_LEAD_CMD replaces the lead's `opencode run` like
# EVAL_WRITER_CMD. Each run's [eval] line records cost= and tokens= summed over
# every opencode session in its clone (lead and writer), from the session store,
# and brief_code= (1 when the brief carries a fenced code block).
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK_ROOT="${EVAL_WORK_ROOT:-/private/var/folders/cy/4_ykzyn94plgzgh4v_vwhzrh0000gn/T/opencode/evals-run}"
CASES="${EVAL_CASES_DIR:-$HERE/cases}"
CHECKS="${EVAL_WRITER_CHECKS:-$HERE/writer-checks.json}"
MODEL=""
LEAD=""
BLIND=0
AGENT="build"
ONLY=""
RUNS=1
FAILED=0
RAN=0
TOTAL=0
PASSED=0
CASE_TIMEOUT="${EVAL_CASE_TIMEOUT:-900}"

usage() {
  echo "usage: $0 -m provider/model[#variant] [-a agent] [-c case-id] [--runs N] [--blind] [--lead provider/model[#variant]]" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    -m) [ $# -ge 2 ] || usage; MODEL="$2"; shift 2 ;;
    -a) [ $# -ge 2 ] || usage; AGENT="$2"; shift 2 ;;
    -c) [ $# -ge 2 ] || usage; ONLY="$2"; shift 2 ;;
    --runs) [ $# -ge 2 ] || usage; RUNS="$2"; shift 2 ;;
    --blind) BLIND=1; shift ;;
    --lead) [ $# -ge 2 ] || usage; LEAD="$2"; BLIND=1; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[ -n "$MODEL" ] || usage
case "$RUNS" in
  ''|*[!0-9]*) echo "error: --runs needs a positive integer" >&2; exit 2 ;;
esac
[ "$RUNS" -gt 0 ] || { echo "error: --runs needs a positive integer" >&2; exit 2; }
[ -d "$CASES" ] || { echo "no cases directory: $CASES" >&2; exit 2; }
[ -f "$CHECKS" ] || { echo "no writer checks: $CHECKS" >&2; exit 2; }
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$CHECKS" \
  || { echo "invalid JSON: $CHECKS" >&2; exit 2; }

field() { python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2"; }

check_for() {
  python3 -c 'import json,sys
entry = json.load(open(sys.argv[1])).get(sys.argv[2])
print(entry.get("check", "") if isinstance(entry, dict) else "")' "$CHECKS" "$1"
}

protect_for() {
  python3 -c 'import json,sys
entry = json.load(open(sys.argv[1])).get(sys.argv[2])
paths = entry.get("protect", []) if isinstance(entry, dict) else []
print("\n".join(paths))' "$CHECKS" "$1"
}

notes_for() {
  python3 -c 'import json,sys
print("\n".join(e.get("notes", "") for e in json.load(open(sys.argv[1])).get("expected", [])))' "$1"
}

# Expand a leading ~/ or $HOME/ so eval cases stay portable across machines.
# ${p#~/} does not strip under dash — `~` is special in the pattern — so count chars.
expand_home() {
  # shellcheck disable=SC2088  # matching the literal "~/" prefix is the whole point
  case "$1" in
    "~/"*) printf '%s/%s\n' "$HOME" "${1#??}" ;;
    "\$HOME/"*) printf '%s/%s\n' "$HOME" "${1#??????}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

# $$ keeps concurrent invocations apart, exactly as run.sh does.
WORK="$WORK_ROOT/${EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}-writer-$$"
mkdir -p "$WORK/co" "$WORK/results"
printf '%s\n' "$MODEL" > "$WORK/model"

mark_failed() {
  mkdir -p "$WORK/results/$id/run-$k"
  printf '%s\n' "$1" > "$WORK/results/$id/run-$k/FAILED"
  printf '  %-28s %s/%s FAIL (%s)\n' "$id" "$k" "$RUNS" "$1"
  FAILED=1
  TOTAL=$((TOTAL+1))
}

for dir in "$CASES"/*/; do
  id="$(basename "$dir")"
  if [ -n "$ONLY" ] && [ "$ONLY" != "$id" ]; then continue; fi

  check="$(check_for "$id")"
  if [ -z "$check" ]; then
    if [ -n "$ONLY" ]; then
      echo "error: no writer check for $id in $CHECKS" >&2
      exit 2
    fi
    continue
  fi
  RAN=1

  cfg="$dir/case.json"
  if [ ! -f "$cfg" ]; then
    echo "missing case: $cfg" >&2
    exit 2
  fi
  repo="$(expand_home "$(field "$cfg" repo)")"
  base="$(field "$cfg" base)"
  patch="$(field "$cfg" patch)"; [ -n "$patch" ] || patch=change.patch
  notes="$(notes_for "$cfg")"
  protect="$(protect_for "$id")"

  claim="$(field "$cfg" claim)"
  if [ "$BLIND" -eq 1 ]; then
    report="CHANGE (what the bugged change was meant to do; the cause is not given)
${claim}"
  else
    report="BUG REPORT
${notes}"
  fi
  prompt="The check below fails in this repository, and it is the oracle for a bug report: it encodes the behaviour that is currently broken. Fix the production code so the check passes. The fix is not in the tree.

${report}

CHECK (exit 0 means fixed)
${check}

Do not modify these paths; they are the oracle, and editing one fails the run:
${protect}

Run the check yourself before you finish. Do not launch subagents."

  k=1
  while [ "$k" -le "$RUNS" ]; do
    co="$WORK/co/$id-$k"
    outdir="$WORK/results/$id/run-$k"
    mkdir -p "$outdir"
    rm -rf "$co"

    if ! git clone --shared --no-checkout -q "$repo" "$co"; then
      mark_failed "clone failed"
      k=$((k+1)); continue
    fi
    if ! git -C "$co" checkout -q "$base"; then
      mark_failed "checkout failed"
      k=$((k+1)); continue
    fi
    # The writer has shell and runs with --auto, which approves a push. The
    # clone's only remote is the fixture repository itself, so point it at a
    # path that does not exist; the shared object store does not use the URL.
    # (`git remote remove` also deletes every remote-tracking ref, which fails
    # on a fixture whose branch names collide on a case-insensitive disk.)
    if ! git -C "$co" remote set-url origin "$co/.git/eval-no-remote"; then
      mark_failed "remote disable failed"
      k=$((k+1)); continue
    fi
    if ! git -C "$co" apply "$dir$patch"; then
      mark_failed "apply failed"
      k=$((k+1)); continue
    fi
    git -C "$co" -c user.name=eval-writer -c user.email=eval-writer@example.invalid add -A
    if ! git -C "$co" -c user.name=eval-writer -c user.email=eval-writer@example.invalid \
        commit -q -m "eval: bugged state"; then
      mark_failed "commit failed"
      k=$((k+1)); continue
    fi
    # A ref pins the bugged tree so a writer that commits or rewrites history
    # cannot hide a test edit from the protected-path diff.
    git -C "$co" update-ref refs/eval/bugged HEAD

    start=$(date +%s)
    start_ms=$(( $(date +%s) * 1000 ))
    lead_reason=""
    brief_code="-"
    writer_prompt="$prompt"
    if [ -n "$LEAD" ]; then
      lead_prompt="You are the lead. Do not edit, create or delete any file except .eval-brief.md; you may run commands, including the check. Diagnose why the check below fails, then write .eval-brief.md in this directory: a brief for an implementor who will fix it, following the implementor-brief skill (goal, done check, proof wanted, what you know, constraints, files in scope). The implementor sees only your brief and the check.

${prompt}"
      if [ -n "${EVAL_LEAD_CMD:-}" ]; then
        ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "$EVAL_LEAD_CMD" "$lead_prompt" ) > "$outdir/lead.txt" 2>&1
      else
        ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" opencode run --standalone --agent build --model "$LEAD" --auto "$lead_prompt" ) > "$outdir/lead.txt" 2>&1
      fi
      if [ -f "$co/.eval-brief.md" ]; then
        mv "$co/.eval-brief.md" "$outdir/brief.md"
        if grep -q '```' "$outdir/brief.md"; then brief_code=1; else brief_code=0; fi
      else
        lead_reason="no brief"
      fi
      if [ -n "$(git -C "$co" status --porcelain)" ]; then
        lead_reason="${lead_reason:+$lead_reason; }lead edited"
      fi
      writer_prompt="An implementor brief from your lead follows; the check is the oracle.

BRIEF
$(cat "$outdir/brief.md" 2>/dev/null)

CHECK (exit 0 means fixed)
${check}

Do not modify these paths; they are the oracle, and editing one fails the run:
${protect}

Run the check yourself before you finish. Do not launch subagents."
    fi
    if [ -n "$lead_reason" ]; then
      wrc=0
      : > "$outdir/writer.txt"
    elif [ -n "${EVAL_WRITER_CMD:-}" ]; then
      ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "$EVAL_WRITER_CMD" "$writer_prompt" ) > "$outdir/writer.txt" 2>&1
      wrc=$?
    else
      ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" opencode run --standalone --agent "$AGENT" --model "$MODEL" --auto "$writer_prompt" ) > "$outdir/writer.txt" 2>&1
      wrc=$?
    fi

    ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" bash -c "$check" ) > "$outdir/check.txt" 2>&1
    crc=$?
    end=$(date +%s)

    touched=""
    while IFS= read -r p; do
      [ -n "$p" ] || continue
      changed="$(git -C "$co" diff --name-only refs/eval/bugged -- "$p" 2>/dev/null)"
      untracked="$(git -C "$co" ls-files --others --exclude-standard -- "$p" 2>/dev/null)"
      if [ -n "$changed" ] || [ -n "$untracked" ]; then
        touched="$touched $p"
      fi
    done <<< "$protect"

    reason="$lead_reason"
    if [ "$wrc" -ne 0 ]; then
      if [ "$wrc" -eq 142 ] || [ "$wrc" -eq 124 ]; then
        reason="timeout"
      else
        reason="writer exit $wrc"
      fi
    fi
    if [ "$crc" -ne 0 ]; then
      reason="${reason:+$reason; }check failed"
    fi
    if [ -n "$touched" ]; then
      reason="${reason:+$reason; }touched tests (${touched# })"
    fi

    usage_line="$(python3 -I - "$co" "$start_ms" <<'PY'
import os, sqlite3, sys
co, since = sys.argv[1], int(sys.argv[2])
db = os.path.expanduser("~/.local/share/opencode/opencode.db")
dirs = {co, os.path.realpath(co)}
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = "SELECT coalesce(sum(cost),0), coalesce(sum(tokens_input+tokens_output+tokens_cache_read),0) FROM session_v2 WHERE time_created >= ? AND directory IN (%s)" % ",".join("?" * len(dirs))
    cost, tokens = con.execute(q, (since, *dirs)).fetchone()
except Exception:
    cost, tokens = 0, 0
print(f"cost={cost:.4f} tokens={tokens}")
PY
)"
    printf '\n[eval] exit=%s check=%s case=%s run=%s/%s agent=%s model=%s lead=%s blind=%s seconds=%s %s brief_code=%s\n' \
      "$wrc" "$crc" "$id" "$k" "$RUNS" "$AGENT" "$MODEL" "${LEAD:--}" "$BLIND" "$((end-start))" "$usage_line" "$brief_code" >> "$outdir/writer.txt"

    TOTAL=$((TOTAL+1))
    if [ -z "$reason" ]; then
      PASSED=$((PASSED+1))
      printf '  %-28s %s/%s PASS\n' "$id" "$k" "$RUNS"
    else
      FAILED=1
      printf '  %-28s %s/%s FAIL (%s)\n' "$id" "$k" "$RUNS" "$reason"
    fi
    k=$((k+1))
  done
done

if [ -n "$ONLY" ] && [ "$RAN" -eq 0 ]; then
  echo "case did not run: $ONLY" >&2
  exit 2
fi

echo
printf 'TOTAL %s/%s runs passed\n' "$PASSED" "$TOTAL"
echo "results: $WORK"
if [ "$FAILED" -ne 0 ]; then
  echo "one or more writer runs failed" >&2
  exit 1
fi
