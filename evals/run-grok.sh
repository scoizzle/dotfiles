#!/bin/bash
# Golden-set runner for Grok Build's own harness, so a model can be compared
# across harnesses with the same cases, prompt, and scorer.
#
#   ./run-grok.sh -c concat-nonstring-operand
#   ./run-grok.sh -c clean-enum-backing-type -m grok-4.7 -e high
#   ./run-grok.sh --tier T1
#
# The cases, the clone/apply steps, the prompt, the timeout, and the results
# layout are the same as run.sh. What differs is the harness: `grok -p` instead
# of `opencode run`, with the verifier's instructions passed as appended system
# rules. Grade the run with ./score.py, exactly as an opencode run.
#
#   ./run-grok.sh -c concat-nonstring-operand
#   ./score.py /private/var/folders/.../opencode/evals-run/grok-...
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK_ROOT="${EVAL_WORK_ROOT:-/private/var/folders/cy/4_ykzyn94plgzgh4v_vwhzrh0000gn/T/opencode/evals-run}"
MODEL="${GROK_MODEL:-grok-4.7}"
EFFORT="${GROK_EFFORT:-high}"
ONLY=""
TIER=""
FAILED=0
RAN=0
CASE_TIMEOUT="${EVAL_CASE_TIMEOUT:-900}"

usage() {
  echo "usage: $0 [-m model] [-e effort] [-c case-id] [-t T0|T1|T2]" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    -m) [ $# -ge 2 ] || usage; MODEL="$2"; shift 2 ;;
    -e|--effort) [ $# -ge 2 ] || usage; EFFORT="$2"; shift 2 ;;
    -c) [ $# -ge 2 ] || usage; ONLY="$2"; shift 2 ;;
    -t|--tier) [ $# -ge 2 ] || usage; TIER="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

case "$TIER" in
  ""|T0|T1|T2) ;;
  *) usage ;;
esac

command -v grok >/dev/null || { echo "grok not on PATH" >&2; exit 2; }

field() { python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2"; }

expand_home() {
  # shellcheck disable=SC2088  # matching the literal "~/" prefix is the whole point
  case "$1" in
    "~/"*) printf '%s/%s\n' "$HOME" "${1#??}" ;;
    "\$HOME/"*) printf '%s/%s\n' "$HOME" "${1#??????}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

# The verifier's instructions live in the OpenCode agent file; take its body
# (everything after the second frontmatter fence) so both harnesses get the same
# text.
RULES="$(awk 'BEGIN { n = 0 } /^---$/ { n++; next } n >= 2 { print }' "$HERE/../agents/verifier.md")"
[ -n "$RULES" ] || { echo "could not read agents/verifier.md" >&2; exit 2; }

for cfg in "$HERE"/cases/*/case.json; do
  tier="$(field "$cfg" tier)"
  case "$tier" in
    T0|T1|T2) ;;
    *) echo "invalid tier: $cfg (got '$tier')" >&2; exit 2 ;;
  esac
  artifact="$(field "$cfg" artifact)"; [ -n "$artifact" ] || artifact=change
  case "$artifact" in
    change|plan) ;;
    *) echo "invalid artifact: $cfg (got '$artifact')" >&2; exit 2 ;;
  esac
done

WORK="$WORK_ROOT/${EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}-grok-$$"
mkdir -p "$WORK/co" "$WORK/results"
printf '%s\n' "grok-build/$MODEL#$EFFORT" > "$WORK/model"

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
  [ -n "$tier" ] || { echo "missing tier: $id ($cfg)" >&2; exit 2; }

  # Same selection rules as run.sh: -c wins over the tier filter, --tier covers
  # change cases only, and a bare run is change cases only.
  if [ -z "$ONLY" ]; then
    if [ "$artifact" = "plan" ]; then continue; fi
    if [ -n "$TIER" ] && [ "$tier" != "$TIER" ]; then continue; fi
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
  else
    patch="$(field "$cfg" patch)"; [ -n "$patch" ] || patch=change.patch
    if ! git -C "$co" apply "$dir$patch"; then
      echo "apply failed: $id" >&2
      mark_failed "apply failed"
      continue
    fi
    git -C "$co" add -A
    prompt="Verify the uncommitted change in this repository. The artifact is a CHANGE. Collect the evidence yourself: run git status, git diff HEAD, and the repository's build and changed-area tests as its AGENTS.md names them. Do not run the full suite; the parent owns it at the pre-ship gate. Begin with the coverage block from your instructions."
    claim="$(field "$cfg" claim)"
    if [ -n "$claim" ]; then prompt="$prompt The author describes it as: ${claim}"; fi
  fi

  prompt="$prompt Do not launch subagents. Do not modify any file in the repository. Report your findings directly in your final message, in the severity format from your instructions, with file and line references."

  mkdir -p "$WORK/results/$id"
  out="$WORK/results/$id/$(printf '%s' "grok-build-$MODEL-$EFFORT" | tr '#/' '__').txt"
  start=$(date +%s)
  ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" \
      grok -p "$prompt" \
        --rules "$RULES" \
        --model "$MODEL" \
        --reasoning-effort "$EFFORT" \
        --permission-mode bypassPermissions \
        --always-approve \
        --no-subagents \
        --disable-web-search \
        --output-format plain ) > "$out" 2>&1
  rc=$?
  end=$(date +%s)
  if [ "$rc" -ne 0 ]; then
    mark_failed "grok exit $rc"
  fi
  printf '\n[eval] exit=%s case=%s artifact=%s tier=%s harness=grok-build model=%s#%s seconds=%s\n' \
    "$rc" "$id" "$artifact" "$tier" "$MODEL" "$EFFORT" "$((end-start))" >> "$out"
  printf '  %-32s %-6s %-4s %-14s %4ss  exit=%s\n' \
    "$id" "$artifact" "$tier" "grok-build" "$((end-start))" "$rc"
done

if [ -n "$ONLY" ] && [ "$RAN" -eq 0 ]; then
  echo "case did not run: $ONLY" >&2
  exit 2
fi

echo
echo "results: $WORK"
if [ "$FAILED" -ne 0 ]; then
  echo "one or more cases failed" >&2
  exit 1
fi
