#!/bin/bash
# Golden-set runner for Claude Code's own harness, so `review-deep` can be
# compared with the same cases, prompt, and scorer whether it runs under
# opencode's Claude Agent integration or as a native `claude -p` process.
#
#   ./run-claude.sh -c concat-nonstring-operand
#   ./run-claude.sh -c clean-enum-backing-type -m opus -e medium
#   ./run-claude.sh --tier T1
#
# The cases, the clone/apply steps, the prompt, the timeout, and the results
# layout are the same as run.sh. What differs is the harness: `claude -p`
# instead of `opencode run`, with the review-deep instructions appended as a
# system prompt and the policy's read-only tool list passed explicitly.
# Grade the run with ./score.py, exactly as an opencode run.
#
#   ./run-claude.sh -c concat-nonstring-operand
#   ./score.py /private/var/folders/.../opencode/evals-run/claude-...
#
# This runner is review-deep only: it runs change cases. A plan case needs the
# verifier's shell, so it belongs to `run.sh -a verifier`.
#
# EVAL_CLAUDE_CMD replaces the `claude -p` invocation: it is run in the scratch
# clone with the prompt as its one argument, and must print one JSON result
# envelope (the shape `--output-format json` produces). tests/eval_claude.py
# uses that to exercise this script without a model.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK_ROOT="${EVAL_WORK_ROOT:-/private/var/folders/cy/4_ykzyn94plgzgh4v_vwhzrh0000gn/T/opencode/evals-run}"
CASES="${EVAL_CASES_DIR:-$HERE/cases}"
MODEL="${CLAUDE_MODEL:-opus}"
EFFORT="${CLAUDE_EFFORT:-medium}"
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

if [ -z "${EVAL_CLAUDE_CMD:-}" ]; then
  command -v claude >/dev/null || { echo "claude not on PATH" >&2; exit 2; }
fi

field() { python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$1" "$2"; }

expand_home() {
  # shellcheck disable=SC2088  # matching the literal "~/" prefix is the whole point
  case "$1" in
    "~/"*) printf '%s/%s\n' "$HOME" "${1#??}" ;;
    "\$HOME/"*) printf '%s/%s\n' "$HOME" "${1#??????}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

# The reviewer's instructions live in the OpenCode agent file; take its body
# (everything after the second frontmatter fence) so both harnesses get the same
# text. The read-only tool list comes from the policy, so it matches the agent
# bin/sync-harness renders for Claude Code: built-in tools plus the Roslynk read
# surface, never the writing tools.
RULES="$(awk 'BEGIN { n = 0 } /^---$/ { n++; next } n >= 2 { print }' "$HERE/../agents/review-deep.md")"
[ -n "$RULES" ] || { echo "could not read agents/review-deep.md" >&2; exit 2; }

POLICY_TOOLS="$(python3 - "$HERE/../policy/permissions.json" <<'PY'
import json, sys
spec = json.load(open(sys.argv[1]))["readonly_agents"]
print(",".join(spec["tools"]))
print(",".join(spec["tools"] + [f"mcp__roslynk__{t}" for t in spec["roslynk_read_tools"]]))
PY
)"
BUILTINS="$(printf '%s\n' "$POLICY_TOOLS" | sed -n 1p)"
ALLOWED="$(printf '%s\n' "$POLICY_TOOLS" | sed -n 2p)"
[ -n "$BUILTINS" ] && [ -n "$ALLOWED" ] || { echo "could not read policy/permissions.json readonly_agents" >&2; exit 2; }

for cfg in "$CASES"/*/case.json; do
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

WORK="$WORK_ROOT/${EVAL_RUN_ID:-$(date +%Y%m%d-%H%M%S)}-claude-$$"
mkdir -p "$WORK/co" "$WORK/results"
printf '%s\n' "claude-code/$MODEL#$EFFORT" > "$WORK/model"

mark_failed() {
  mkdir -p "$WORK/results/$id"
  printf '%s\n' "$1" > "$WORK/results/$id/FAILED"
  FAILED=1
}

# Split the JSON envelope into the final report and a cost line. A non-JSON
# result is a failed harness run, not an empty review: keep the raw text in the
# .txt so a human can read what happened, and let mark_failed gate the score.
extract_result() {
  python3 - "$1" "$2" <<'PY'
import json, sys
raw, out = sys.argv[1], sys.argv[2]
try:
    with open(raw, encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
except (OSError, ValueError) as exc:
    sys.stderr.write(f"claude output is not one JSON object: {exc}\n")
    sys.exit(1)
text = data.get("result")
if not isinstance(text, str) or not text.strip():
    sys.stderr.write("claude JSON has no non-empty result\n")
    sys.exit(1)
with open(out, "w", encoding="utf-8") as handle:
    handle.write(text.rstrip("\n") + "\n")
cost = data.get("total_cost_usd")
turns = data.get("num_turns")
print(f"{float(cost or 0):.4f} {int(turns or 0)}")
PY
}

for dir in "$CASES"/*/; do
  id="$(basename "$dir")"
  if [ -n "$ONLY" ] && [ "$ONLY" != "$id" ]; then continue; fi

  cfg="$dir/case.json"
  artifact="$(field "$cfg" artifact)"; [ -n "$artifact" ] || artifact=change
  tier="$(field "$cfg" tier)"
  [ -n "$tier" ] || { echo "missing tier: $id ($cfg)" >&2; exit 2; }

  if [ "$artifact" = "plan" ]; then
    if [ -n "$ONLY" ]; then
      echo "error: $id is a plan case; run it with ./run.sh -a verifier -c $id" >&2
      exit 2
    fi
    continue
  fi

  # Same selection rules as run.sh's change cases: -c wins over the tier filter,
  # and a bare run covers every change case.
  if [ -z "$ONLY" ] && [ -n "$TIER" ] && [ "$tier" != "$TIER" ]; then continue; fi

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

  patch="$(field "$cfg" patch)"; [ -n "$patch" ] || patch=change.patch
  if ! git -C "$co" apply "$dir$patch"; then
    echo "apply failed: $id" >&2
    mark_failed "apply failed"
    continue
  fi
  git -C "$co" add -A

  prompt="Review the uncommitted changes in this repository. The artifact is a CHANGE. The diff is provided below; you have no shell and cannot run git.

--- STATUS ---
$(git -C "$co" status --short)
--- DIFF (staged + unstaged vs HEAD, including new files) ---
$(git -C "$co" diff HEAD)
--- END DIFF ---"
  claim="$(field "$cfg" claim)"
  if [ -n "$claim" ]; then prompt="$prompt The author describes it as: ${claim}"; fi
  prompt="$prompt Do not launch subagents. Do not modify any file in the repository. Report your findings directly in your final message, in the severity format from your instructions, with file and line references."

  mkdir -p "$WORK/results/$id"
  stem="$(printf '%s' "claude-code-$MODEL-$EFFORT" | tr '#/' '__')"
  out="$WORK/results/$id/$stem.txt"
  raw="$WORK/results/$id/$stem.json"
  start=$(date +%s)
  if [ -n "${EVAL_CLAUDE_CMD:-}" ]; then
    ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" "$EVAL_CLAUDE_CMD" "$prompt" ) > "$raw" 2>&1
  else
    ( cd "$co" && perl -e 'alarm shift; exec @ARGV' "$CASE_TIMEOUT" \
        claude -p "$prompt" \
          --model "$MODEL" \
          --effort "$EFFORT" \
          --append-system-prompt "$RULES" \
          --tools "$BUILTINS" \
          --allowedTools "$ALLOWED" \
          --permission-mode dontAsk \
          --output-format json \
          --no-session-persistence ) > "$raw" 2>&1
  fi
  rc=$?
  end=$(date +%s)

  cost_line="$(extract_result "$raw" "$out")"
  if [ -z "$cost_line" ]; then
    cp "$raw" "$out"
    mark_failed "claude output was not a JSON result (exit $rc)"
    cost_line="0.0000 0"
  elif [ "$rc" -ne 0 ]; then
    mark_failed "claude exit $rc"
  fi
  cost="${cost_line%% *}"
  turns="${cost_line##* }"

  printf '\n[eval] exit=%s case=%s artifact=%s tier=%s harness=claude-code model=%s#%s cost_usd=%s turns=%s seconds=%s\n' \
    "$rc" "$id" "$artifact" "$tier" "$MODEL" "$EFFORT" "$cost" "$turns" "$((end-start))" >> "$out"
  printf '  %-32s %-6s %-4s %-14s %4ss  $%-7s exit=%s\n' \
    "$id" "$artifact" "$tier" "claude-code" "$((end-start))" "$cost" "$rc"
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
