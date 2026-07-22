#!/bin/bash
# Stage 2: Analyze fetched content with Claude Code, with retry + model fallback.
#
# Why this exists: Anthropic's AUP classifier intermittently (and sometimes for
# a sustained stretch) blocks a given model on this cyber-intel workload with a
# "violative cyber content" error, which makes `claude -p` exit non-zero. A
# single unguarded call meant one block killed the whole pipeline run.
#
# Escalation ladder (first success wins):
#   1. default model (Opus) — preferred; auto-recovers for free if a block lifts
#   2. retry default once    — absorbs one-off / probabilistic trips
#   3. Sonnet 4.6 fallback   — known-good path for this workload (verified 2026-06-07)
#
# A successful attempt must BOTH exit 0 AND leave a valid brief.json (parseable,
# incident_count > 0). The validation gate catches a clean-exit-but-bad-write so
# it also escalates instead of silently publishing an empty brief.
#
# Configurable via env (defaults are the production values):
#   CLAUDE_BIN   path to the claude binary            (default: claude)
#   PROMPT_FILE  analysis prompt template             (default: analyze_prompt.md)
#   BRIEF_PATH   output JSON to validate              (default: docs/data/brief.json)
#   RETRY_SLEEP  seconds to wait between attempts     (default: 5)
# Requires: DATE (YYYY-MM-DD).
set -uo pipefail
cd "$(dirname "$0")"

: "${DATE:?DATE must be set (YYYY-MM-DD)}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
PROMPT_FILE="${PROMPT_FILE:-analyze_prompt.md}"
BRIEF_PATH="${BRIEF_PATH:-docs/data/brief.json}"
RETRY_SLEEP="${RETRY_SLEEP:-5}"

PROMPT="$(sed "s/{{DATE}}/$DATE/g" "$PROMPT_FILE")"

# A usable brief is parseable JSON with at least one incident.
validate_brief() {
    python3 -c "
import json, sys
try:
    d = json.load(open('$BRIEF_PATH'))
except Exception as e:
    print('  brief.json invalid: %s' % e); sys.exit(1)
sys.exit(0 if d.get('incident_count') and d.get('incidents') else 1)
"
}

# run_attempt LABEL [MODEL_FLAG...]
run_attempt() {
    local label="$1"; shift
    echo "  Stage 2 attempt: $label"
    if "$CLAUDE_BIN" -p "$PROMPT" "$@" --allowedTools Read,Write,Edit,Glob; then
        if validate_brief; then
            echo "  Stage 2 succeeded: $label"
            return 0
        fi
        echo "  Stage 2 exited 0 but brief.json failed validation: $label"
    else
        echo "  Stage 2 command failed: $label"
    fi
    return 1
}

run_attempt "default model (Opus)"                                  && exit 0
sleep "$RETRY_SLEEP"
run_attempt "default model retry"                                   && exit 0
sleep "$RETRY_SLEEP"
run_attempt "Sonnet 4.6 fallback" --model claude-sonnet-4-6         && exit 0

echo "  Stage 2 FAILED on all attempts (Opus, retry, Sonnet 4.6 fallback)."
exit 1
