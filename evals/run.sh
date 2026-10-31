#!/bin/bash
# Golden-set runner: runs a reviewer agent over fixture cases with one model
# and writes results that score.py grades.
#
#   ./run.sh -m opencode-go/glm-5.3#max
#   ./run.sh --tier T1 -a review-light -m opencode-go/mimo-v2.6-flash
#   ./run.sh --tier T2 -a review-deep -m xai/grok-4.7#high
#   ./run.sh -a plan-review-deep -m xai/grok-4.7#high -c plan-ide-storage-tab
#   ./run.sh -a verifier -m claude-agent/sonnet#medium -c concat-nonstring-operand
#
# `tier` is required on every case.json. `--tier` selects change cases only; a
# plan case runs only with `-c` or `-a plan-review-deep`. `-m` is optional; when
# omitted the agent's configured model is used (cost attribution is then zero).
#
# Each case clones the fixture repo at its base commit into a scratch checkout and
# runs the agent there. A "change" case applies its patch first; a "plan" case
# leaves the tree clean and passes the plan in the prompt. The source repository is
# never modified: `git clone --shared` reads its objects and writes nothing back.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK_ROOT="${EVAL_WORK_ROOT:-/private/var/folders/cy/4_ykzyn94plgzgh4v_vwhzrh0000gn/T/opencode/evals-run}"
MODEL=""
ONLY=""
AGENT=""
TIER=""
FAILED=0
RAN=0
CASE_TIMEOUT="${EVAL_CASE_TIMEOUT:-900}"

usage() {
  echo "usage: $0 [-m provider/model[#variant]] [-c case-id] [-a agent] [-t T0|T1|T2]" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    -m) [ $# -ge 2 ] || usage; MODEL="$2"; shift 2 ;;
    -c) [ $# -ge 2 ] || usage; ONLY="$2"; shift 2 ;;
    -a) [ $# -ge 2 ] || usage; AGENT="$2"; shift 2 ;;
    -t|--tier) [ $# -ge 2 ] || usage; TIER="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

case "$TIER" in
  ""|T0|T1|T2) ;;
  *) usage ;;
esac

if [ -n "$AGENT" ] && [ -z "$ONLY" ] && [ -z "$TIER" ] && [ "$AGENT" != "plan-review-deep" ]; then
  echo "error: -a needs -c or --tier (or -a plan-review-deep for the plan case)" >&2
  exit 2
fi

if [ "$AGENT" = "review-light" ] && [ "$TIER" = "T2" ]; then
  echo "error: review-light is T1 only" >&2
  exit 2
fi
if [ "$AGENT" = "second-opinion" ] && [ "$TIER" = "T1" ]; then
  echo "error: second-opinion is T2 only" >&2
  exit 2
fi
if [ "$AGENT" = "plan-review-deep" ] && [ -n "$TIER" ]; then
  echo "error: a plan case runs with -c, not --tier" >&2
  exit 2
fi
case "$MODEL" in
  *mimo-v2.6-flash*)
    if [ "$TIER" = "T2" ]; then
      echo "error: MiMo Flash is T1 only; do not use it for a T2 bakeoff" >&2
      exit 2
    fi
    ;;
esac

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

for cfg in "$HERE"/cases/*/case.json; do
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
mkdir -p "$WORK/co" "$WORK/results"
printf '%s\n' "${MODEL:-${AGENT:-default}}" > "$WORK/model"

snapshot_stats() { opencode stats --days 0 --models --json > "$1" 2>/dev/null || printf '{}' > "$1"; }
snapshot_stats "$WORK/stats-before.json"

mark_failed() {
  mkdir -p "$WORK/results/$id"
  printf '%s\n' "$1" > "$WORK/results/$id/FAILED"
  FAILED=1
}

for dir in "$HERE"/cases/*/; do
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

  if [ -n "$AGENT" ] && [ "$AGENT" = "plan-review-deep" ] && [ "$artifact" != "plan" ]; then
    continue
  fi
  if [ -n "$AGENT" ] && [ "$AGENT" != "plan-review-deep" ] && [ "$artifact" = "plan" ]; then
    if [ -n "$ONLY" ]; then
      echo "error: plan case $id needs -a plan-review-deep" >&2
      exit 2
    fi
    continue
  fi
  if [ -n "$AGENT" ] && [ "$AGENT" = "review-light" ] && [ "$tier" = "T2" ]; then
    echo "error: review-light is T1 only ($id)" >&2
    exit 2
  fi
  if [ -n "$AGENT" ] && [ "$AGENT" = "second-opinion" ] && [ "$tier" != "T2" ]; then
    if [ -n "$ONLY" ]; then
      echo "error: second-opinion is T2 only ($id)" >&2
      exit 2
    fi
    continue
  fi

  # A plan case runs only with an explicit -c or -a plan-review-deep. A bare
  # run is change cases only.
  if [ -z "$ONLY" ] && [ "$artifact" = "plan" ] && [ "$AGENT" != "plan-review-deep" ]; then
    continue
  fi

  if [ -n "$AGENT" ]; then
    agent="$AGENT"
  elif [ "$artifact" = "plan" ]; then
    agent="plan-review-deep"
  elif [ "$tier" = "T1" ]; then
    agent="review-light"
  else
    agent="review-deep"
  fi

  case "$MODEL" in
    *mimo-v2.6-flash*)
      if [ "$tier" = "T2" ]; then
        echo "error: MiMo Flash is T1 only ($id)" >&2
        exit 2
      fi
      ;;
  esac

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
      prompt="Review the uncommitted changes in this repository. The artifact is a CHANGE. The diff is provided below; you have no shell and cannot run git.

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

  prompt="$prompt Do not launch subagents. Do not modify any file in the repository. Report your findings directly in your final message, in the severity format from your instructions, with file and line references."

  mkdir -p "$WORK/results/$id"
  out="$WORK/results/$id/$(printf '%s' "${MODEL:-$agent}" | tr '#/' '__').txt"
  start=$(date +%s)
  if [ -n "$MODEL" ]; then
    ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" opencode run --standalone --agent "$agent" --model "$MODEL" --auto "$prompt" ) > "$out" 2>&1
  else
    ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" opencode run --standalone --agent "$agent" --auto "$prompt" ) > "$out" 2>&1
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
