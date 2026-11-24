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
# Every case in evals/writer-checks.json exports the fixture repo's base
# commit into a fresh repository (no history, no remote), applies the case patch (which reverts only the production files, so
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
#
# --supervise MODEL is the lead/implementor split as the person means it
# (2026-11-23): the writer (-m) does all the work, blind; then a skeptical
# supervisor runs in the clone (build, shell allowed, told not to edit), reruns
# the check, reads the diff and writes .eval-verdict.md: first line ACCEPT or
# REJECT, then findings. A REJECT gives the writer one fix round with the
# findings. The line records pre_pass (the writer's first attempt scored
# right), verdict, sup=ok|catch|false_alarm|miss, and sup_cost/sup_tokens for
# the supervisor's sessions alone. EVAL_SUPERVISOR_CMD replaces its opencode run.
#
# --bare runs the writer on bare opencode: an empty config directory as
# XDG_CONFIG_HOME and OPENCODE_DISABLE_CLAUDE_CODE=1, so no AGENTS.md (nor the
# ~/.claude/CLAUDE.md fallback), harness skills, plugins, policy or MCP servers
# load (the person, 2026-11-23: "is bare t3/opencode better than what I have?").
# Skills the person installed outside this repo (~/.agents/skills) still load in
# both arms.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK_ROOT="${EVAL_WORK_ROOT:-/private/var/folders/cy/4_ykzyn94plgzgh4v_vwhzrh0000gn/T/opencode/evals-run}"
CASES="${EVAL_CASES_DIR:-$HERE/cases}"
CHECKS="${EVAL_WRITER_CHECKS:-$HERE/writer-checks.json}"
MODEL=""
LEAD=""
SUPERVISOR=""
BLIND=0
BARE=0
PROJECT=1
ROLE=""
AGENT="build"
ONLY=""
RUNS=1
FAILED=0
RAN=0
TOTAL=0
PASSED=0
CASE_TIMEOUT="${EVAL_CASE_TIMEOUT:-900}"

usage() {
  echo "usage: $0 -m provider/model[#variant] [-a agent] [-c case-id] [--runs N] [--blind] [--lead provider/model[#variant]] [--supervise provider/model[#variant]] [--bare] [--no-project] [--role NAME]" >&2
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
    --supervise) [ $# -ge 2 ] || usage; SUPERVISOR="$2"; BLIND=1; shift 2 ;;
    --bare) BARE=1; shift ;;
    --no-project) PROJECT=0; shift ;;
    --role) [ $# -ge 2 ] || usage; ROLE="$2"; shift 2 ;;
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
WRITER_ENV=(env)
if [ "$BARE" -eq 1 ]; then
  mkdir -p "$WORK/bare-config/opencode"
  # Unset any config a launching shell carries, or the harness reaches the bare arm (review, 2026-11-23).
  WRITER_ENV=(env -u OPENCODE_CONFIG -u OPENCODE_CONFIG_DIR -u OPENCODE_CONFIG_CONTENT XDG_CONFIG_HOME="$WORK/bare-config" OPENCODE_DISABLE_CLAUDE_CODE=1)
fi
# --no-project also sets OPENCODE_DISABLE_PROJECT_CONFIG=1, skipping the
# repository's own AGENTS.md, so bare vs bare --no-project measures the
# project's agent layer (the person, 2026-11-23: "is poly's agent stuff crap too?").
if [ "$PROJECT" -eq 0 ]; then
  WRITER_ENV+=(OPENCODE_DISABLE_PROJECT_CONFIG=1)
fi
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

Run the check yourself before you finish. Do not launch subagents. Do not download code or patches from the network; solve it from this repository."
  # --role: the prompt opens with the role line a T3 brief carries, so the plugin
  # applies that role as it does for a T3 child (2026-11-24).
  if [ -n "$ROLE" ]; then prompt="role: ${ROLE}
${prompt}"; fi

  k=1
  while [ "$k" -le "$RUNS" ]; do
    co="$WORK/co/$id-$k"
    outdir="$WORK/results/$id/run-$k"
    mkdir -p "$outdir"
    rm -rf "$co"

    # The writer gets the base's files in a fresh repository whose only commit
    # is the bugged state: no parent, no remote, no fixture objects. A clone
    # kept the fixed base as HEAD~1, and writers copied the fix from it (review
    # of PR #57, 2026-11-23). With no remote, a push has nowhere to go either.
    mkdir -p "$co"
    if ! git -C "$repo" archive --format=tar "$base" | tar -x -C "$co"; then
      mark_failed "export failed"
      k=$((k+1)); continue
    fi
    if ! git -C "$co" init -q; then
      mark_failed "init failed"
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
      ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "${WRITER_ENV[@]}" opencode run --standalone --agent "$AGENT" --model "$MODEL" --auto "$writer_prompt" ) > "$outdir/writer.txt" 2>&1
      wrc=$?
    fi

    sup_reason=""
    verdict="-"
    pre_pass="-"
    sup_class="-"
    sup_start_ms=0
    sup_end_ms=0
    if [ -n "$SUPERVISOR" ] && [ -z "$lead_reason" ]; then
      ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" bash -c "$check" ) > "$outdir/pre-check.txt" 2>&1
      pre_crc=$?
      pre_touched=""
      while IFS= read -r p; do
        [ -n "$p" ] || continue
        if [ -n "$(git -C "$co" diff --name-only refs/eval/bugged -- "$p" 2>/dev/null)$(git -C "$co" ls-files --others --exclude-standard -- "$p" 2>/dev/null)" ]; then
          pre_touched=1
        fi
      done <<< "$protect"
      if [ "$wrc" -eq 0 ] && [ "$pre_crc" -eq 0 ] && [ -z "$pre_touched" ]; then pre_pass=1; else pre_pass=0; fi
      snap() { { git -C "$co" diff refs/eval/bugged; git -C "$co" ls-files --others --exclude-standard | grep -vx '.eval-verdict.md' | sort; } | shasum; }
      before_sup="$(snap)"
      sup_prompt="You are the skeptical supervisor of an implementor who claims to have fixed the failing check below. Do not edit, create or delete any file except .eval-verdict.md; you may run commands. Verify, do not trust: rerun the check, read \`git diff refs/eval/bugged\` and any untracked files, and look for edits to the oracle paths, a fix that special-cases the check, a symptom fixed instead of its cause, and missing or broken behaviour the check does not cover. Then write .eval-verdict.md in this directory: first line exactly ACCEPT or REJECT, then your findings with evidence. A REJECT goes back to the implementor for one more attempt.

${prompt}"
      sup_start_ms=$(( $(date +%s) * 1000 ))
      if [ -n "${EVAL_SUPERVISOR_CMD:-}" ]; then
        ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "$EVAL_SUPERVISOR_CMD" "$sup_prompt" ) > "$outdir/supervisor.txt" 2>&1
      else
        ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" opencode run --standalone --agent build --model "$SUPERVISOR" --auto "$sup_prompt" ) > "$outdir/supervisor.txt" 2>&1
      fi
      sup_end_ms=$(( $(date +%s) * 1000 + 1000 ))
      if [ -f "$co/.eval-verdict.md" ]; then
        mv "$co/.eval-verdict.md" "$outdir/verdict.md"
        verdict="$(head -n 1 "$outdir/verdict.md" | tr -d '[:space:]*#' | tr '[:lower:]' '[:upper:]')"
        case "$verdict" in ACCEPT|REJECT) ;; *) sup_reason="no verdict"; verdict="none" ;; esac
      else
        sup_reason="no verdict"
        verdict="none"
      fi
      if [ "$(snap)" != "$before_sup" ]; then
        sup_reason="${sup_reason:+$sup_reason; }supervisor edited"
      fi
      if [ -z "$sup_reason" ]; then
        case "$verdict:$pre_pass" in
          ACCEPT:1) sup_class=ok ;; ACCEPT:0) sup_class=miss ;;
          REJECT:0) sup_class=catch ;; REJECT:1) sup_class=false_alarm ;;
        esac
      fi
      if [ -z "$sup_reason" ] && [ "$verdict" = "REJECT" ]; then
        fix_prompt="${writer_prompt}

SUPERVISOR FINDINGS (your supervisor rejected your first attempt; address them)
$(tail -n +2 "$outdir/verdict.md")"
        printf '\n[eval] fix round after REJECT\n' >> "$outdir/writer.txt"
        if [ -n "${EVAL_WRITER_CMD:-}" ]; then
          ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "$EVAL_WRITER_CMD" "$fix_prompt" ) >> "$outdir/writer.txt" 2>&1
        else
          ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "${WRITER_ENV[@]}" opencode run --standalone --agent "$AGENT" --model "$MODEL" --auto "$fix_prompt" ) >> "$outdir/writer.txt" 2>&1
        fi
        wrc=$?
      fi
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

    reason="$lead_reason${sup_reason:+${lead_reason:+; }$sup_reason}"
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

    # The fixture repository stays on disk; mark a writer that names it.
    if grep -q -F -- "$repo" "$outdir/writer.txt" 2>/dev/null; then fixture_ref=1; else fixture_ref=0; fi
    # The merged fix is public: mark a writer that reached a code host (Phase 8c,
    # DeepSeek ran `curl .../pull/<n>.diff` and cloned the repository).
    if grep -q -E "github\.com|githubusercontent\.com|api\.github|gh (pr|repo|api) " "$outdir/writer.txt" 2>/dev/null; then web_ref=1; else web_ref=0; fi
    usage_line="$(python3 -I - "$co" "$start_ms" "$sup_start_ms" "$sup_end_ms" <<'PY'
import os, sqlite3, sys
co, since, s0, s1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
db = os.path.expanduser("~/.local/share/opencode/opencode.db")
dirs = {co, os.path.realpath(co)}
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = "SELECT coalesce(sum(cost),0), coalesce(sum(tokens_input+tokens_output+tokens_cache_read),0) FROM session_v2 WHERE time_created >= ? AND directory IN (%s)" % ",".join("?" * len(dirs))
    cost, tokens = con.execute(q, (since, *dirs)).fetchone()
    sq = q + " AND time_created < ?"
    scost, stokens = con.execute(sq, (s0, *dirs, s1)).fetchone() if s0 else (0, 0)
except Exception:
    cost, tokens, scost, stokens = 0, 0, 0, 0
print(f"cost={cost:.4f} tokens={tokens} sup_cost={scost:.4f} sup_tokens={stokens}")
PY
)"
    printf '\n[eval] exit=%s check=%s case=%s run=%s/%s agent=%s model=%s lead=%s supervisor=%s blind=%s bare=%s project=%s role=%s seconds=%s %s brief_code=%s pre_pass=%s verdict=%s sup=%s fixture_ref=%s web_ref=%s\n' \
      "$wrc" "$crc" "$id" "$k" "$RUNS" "$AGENT" "$MODEL" "${LEAD:--}" "${SUPERVISOR:--}" "$BLIND" "$BARE" "$PROJECT" "${ROLE:--}" "$((end-start))" "$usage_line" "$brief_code" "$pre_pass" "$verdict" "$sup_class" "$fixture_ref" "$web_ref" >> "$outdir/writer.txt"

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
