#!/bin/bash
# Golden-set runner: runs a reviewer agent over fixture cases with one model
# and writes results that score.py grades.
#
#   ./run.sh -m opencode-go/glm-5.3#max
#   ./run.sh --tier T1 -a review-deep -m claude-agent/haiku
#   ./run.sh -a review-deep -m xai/grok-4.7#high -c concat-nonstring-operand
#   ./run.sh -a verifier -m xai/grok-4.7#high -c plan-ide-storage-tab
#
# `tier` is required on every case.json. It is a case label, not an agent
# selector: `--tier` filters change cases, and every change case runs on
# review-deep. A plan case runs on verifier, and only with `-c` (or `-a verifier`
# with `-c`). `-m` is optional; when omitted the agent's configured model is used
# (cost attribution is then zero).
#
# Each case clones the fixture repo at its base commit into a scratch checkout and
# runs the agent there. A "change" case applies its patch first; a "plan" case
# leaves the tree clean and passes the plan in the prompt. The source repository is
# never modified: `git clone --shared` reads its objects and writes nothing back.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
CASES="${EVAL_CASES_DIR:-$HERE/cases}"
BARE=0
PROJECT=1
WORK_ROOT="${EVAL_WORK_ROOT:-/private/var/folders/cy/4_ykzyn94plgzgh4v_vwhzrh0000gn/T/opencode/evals-run}"
MODEL=""
ONLY=""
AGENT=""
TIER=""
FAILED=0
RAN=0
CASE_TIMEOUT="${EVAL_CASE_TIMEOUT:-900}"

usage() {
  echo "usage: $0 [-m provider/model[#variant]] [-c case-id] [-a agent] [-t T0|T1|T2] [--bare] [--no-project]" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    -m) [ $# -ge 2 ] || usage; MODEL="$2"; shift 2 ;;
    -c) [ $# -ge 2 ] || usage; ONLY="$2"; shift 2 ;;
    -a) [ $# -ge 2 ] || usage; AGENT="$2"; shift 2 ;;
    -t|--tier) [ $# -ge 2 ] || usage; TIER="$2"; shift 2 ;;
    --bare) BARE=1; shift ;;
    --no-project) PROJECT=0; shift ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

case "$TIER" in
  ""|T0|T1|T2) ;;
  *) usage ;;
esac

if [ -n "$AGENT" ] && [ -z "$ONLY" ] && [ -z "$TIER" ]; then
  echo "error: -a needs -c or --tier" >&2
  exit 2
fi

field() { python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2"; }

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

for cfg in "$CASES"/*/case.json; do
  tier="$(field "$cfg" tier)"
  case "$tier" in
    T0|T1|T2) ;;
    *)
      echo "invalid tier: $cfg (got '$tier')" >&2
      exit 2
      ;;
  esac
  artifact="$(field "$cfg" artifact)"; [ -n "$artifact" ] || artifact=change
  case "$artifact" in
    change|plan) ;;
    *)
      echo "invalid artifact: $cfg (got '$artifact')" >&2
      exit 2
      ;;
  esac
done

# $$ keeps concurrent invocations apart: a second-resolution timestamp alone
# collides, and colliding runs share their scratch checkouts and clobber each other.
WORK="$WORK_ROOT/${EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}-$$"
# --bare (2026-11-23): bare opencode, an empty config and no Claude Code
# compatibility, so no AGENTS.md, harness skills, plugin, policy or MCP servers.
# macOS bash 3.2 errors on an empty array under set -u, so always start with env.
RUN_ENV=(env)
if [ "$BARE" -eq 1 ]; then
  mkdir -p "$WORK/bare-config/opencode"
  RUN_ENV=(env -u OPENCODE_CONFIG -u OPENCODE_CONFIG_DIR -u OPENCODE_CONFIG_CONTENT XDG_CONFIG_HOME="$WORK/bare-config" OPENCODE_DISABLE_CLAUDE_CODE=1)
fi
# --no-project also sets OPENCODE_DISABLE_PROJECT_CONFIG=1, skipping the
# repository's own AGENTS.md, so bare vs bare --no-project measures the
# project's agent layer (the person, 2026-11-23: "is poly's agent stuff crap too?").
if [ "$PROJECT" -eq 0 ]; then
  RUN_ENV+=(OPENCODE_DISABLE_PROJECT_CONFIG=1)
fi
mkdir -p "$WORK/co" "$WORK/results"
printf '%s\n' "${MODEL:-${AGENT:-default}}" > "$WORK/model"

snapshot_stats() { opencode stats --days 0 --models --json > "$1" 2>/dev/null || printf '{}' > "$1"; }
snapshot_stats "$WORK/stats-before.json"

mark_failed() {
  mkdir -p "$WORK/results/$id"
  printf '%s\n' "$1" > "$WORK/results/$id/FAILED"
  FAILED=1
}

for dir in "$CASES"/*/; do
  id="$(basename "$dir")"
  if [ -n "$ONLY" ] && [ "$ONLY" != "$id" ]; then continue; fi

  cfg="$dir/case.json"
  artifact="$(field "$cfg" artifact)"; [ -n "$artifact" ] || artifact=change
  tier="$(field "$cfg" tier)"
  if [ -z "$tier" ]; then
    echo "missing tier: $id ($cfg)" >&2
    exit 2
  fi

  # An explicit -c wins over the tier filter. Otherwise --tier selects change
  # cases only; plan cases are skipped by --tier.
  if [ -z "$ONLY" ]; then
    if [ -n "$TIER" ] && [ "$artifact" = "plan" ]; then continue; fi
    if [ -n "$TIER" ] && [ "$tier" != "$TIER" ]; then continue; fi
  fi

  # A plan case runs only with an explicit -c, and only on the verifier: a bare
  # run and --tier are change cases only.
  if [ -z "$ONLY" ] && [ "$artifact" = "plan" ]; then
    continue
  fi
  if [ -n "$AGENT" ] && [ "$artifact" = "plan" ] && [ "$AGENT" != "verifier" ]; then
    echo "error: plan case $id needs -a verifier" >&2
    exit 2
  fi

  if [ "$BARE" -eq 1 ]; then
    agent="build"
  elif [ -n "$AGENT" ]; then
    agent="$AGENT"
  elif [ "$artifact" = "plan" ]; then
    agent="verifier"
  else
    agent="review-deep"
  fi

  co="$WORK/co/$id"
  RAN=1
  rm -rf "$co"
  if ! git clone --shared --no-checkout -q "$(expand_home "$(field "$cfg" repo)")" "$co"; then
    echo "clone failed: $id" >&2
    mark_failed "clone failed"
    continue
  fi
  if ! git -C "$co" checkout -q "$(field "$cfg" base)"; then
    echo "checkout failed: $id" >&2
    mark_failed "checkout failed"
    continue
  fi

  if [ "$artifact" = "plan" ]; then
    plan_file="$(field "$cfg" plan)"; [ -n "$plan_file" ] || plan_file=plan.md
    goal="$(field "$cfg" goal)"
    if [ ! -f "$dir$plan_file" ]; then
      echo "plan missing: $id" >&2
      mark_failed "plan missing"
      continue
    fi
    prompt="Review the plan below. The artifact is a PLAN, not a change: there is no diff. Verify every claim it makes about this repository against the actual files, and find what it would get wrong if executed as written.

GOAL: ${goal}

--- PLAN: ${plan_file} ---
$(cat "$dir$plan_file")
--- END PLAN ---"
  elif [ "$artifact" = "change" ]; then
    patch="$(field "$cfg" patch)"; [ -n "$patch" ] || patch=change.patch
    if ! git -C "$co" apply "$dir$patch"; then
      echo "apply failed: $id" >&2
      mark_failed "apply failed"
      continue
    fi
    git -C "$co" add -A
    claim="$(field "$cfg" claim)"
    if [ "$agent" = "verifier" ]; then
      # The verifier owns its own evidence: it has shell, and a diff pasted into
      # the prompt would let it skip the build and the changed-area tests.
      prompt="Verify the uncommitted change in this repository. The artifact is a CHANGE. Collect the evidence yourself: run git status, git diff HEAD, and the repository's build and changed-area tests as its AGENTS.md names them. Do not run the full suite; the parent owns it at the pre-ship gate. Begin with the coverage block from your instructions."
      if [ -n "$claim" ]; then prompt="$prompt The author describes it as: ${claim}"; fi
    else
      if [ "$BARE" -eq 1 ]; then shell_note="The diff is provided below."; else shell_note="The diff is provided below; you have no shell and cannot run git."; fi
      prompt="Review the uncommitted changes in this repository. The artifact is a CHANGE. ${shell_note}

--- STATUS ---
$(git -C "$co" status --short)
--- DIFF (staged + unstaged vs HEAD, including new files) ---
$(git -C "$co" diff HEAD)
--- END DIFF ---"
      if [ -n "$claim" ]; then prompt="$prompt The author describes it as: ${claim}"; fi
    fi
  else
    echo "unknown artifact: $artifact ($id)" >&2
    mark_failed "unknown artifact"
    continue
  fi

  if [ "$BARE" -eq 1 ]; then
    # Bare opencode has no review prompt: name the markers score.py reads.
    format="marking each finding 🔴 (breaks or unsafe), 🟠 (likely bug or missing required coverage), 🟡 (worth fixing, not blocking) or 🟢 (nit)"
  else
    format="in the severity format from your instructions"
  fi
  prompt="$prompt Do not launch subagents. Do not modify any file in the repository. Report your findings directly in your final message, ${format}, with file and line references."

  mkdir -p "$WORK/results/$id"
  out="$WORK/results/$id/$(printf '%s' "${MODEL:-$agent}" | tr '#/' '__').txt"
  start=$(date +%s)
  if [ -n "$MODEL" ]; then
    ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "${RUN_ENV[@]}" opencode run --standalone --agent "$agent" --model "$MODEL" --auto "$prompt" ) > "$out" 2>&1
  else
    ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "${RUN_ENV[@]}" opencode run --standalone --agent "$agent" --auto "$prompt" ) > "$out" 2>&1
  fi
  rc=$?
  end=$(date +%s)
  if [ "$rc" -ne 0 ]; then
    mark_failed "reviewer exit $rc"
  fi
  printf '\n[eval] exit=%s case=%s artifact=%s tier=%s agent=%s model=%s seconds=%s\n' \
    "$rc" "$id" "$artifact" "$tier" "$agent" "${MODEL:-agent-default}" "$((end-start))" >> "$out"
  printf '  %-32s %-6s %-4s %-14s %4ss  exit=%s\n' \
    "$id" "$artifact" "$tier" "$agent" "$((end-start))" "$rc"
done

if [ -n "$ONLY" ] && [ "$RAN" -eq 0 ]; then
  echo "case did not run: $ONLY" >&2
  exit 2
fi

snapshot_stats "$WORK/stats-after.json"
python3 "$HERE/cost.py" "$WORK" 2>/dev/null || true
echo
echo "results: $WORK"
pkill -f "$WORK/co/.*/Poly.Mcp" 2>/dev/null || true
if [ "$FAILED" -ne 0 ]; then
  echo "one or more cases failed" >&2
  exit 1
fi
