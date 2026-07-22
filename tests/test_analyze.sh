#!/bin/bash
# Tests for analyze.sh — the resilient Stage 2 wrapper.
#
# These tests inject a FAKE `claude` binary (CLAUDE_BIN) so no real API calls
# are made. The fake's behaviour is driven by env vars:
#   FAKE_OPUS         = block | ok    (how the default/Opus model responds)
#   FAKE_SONNET       = block | ok    (how the --model claude-sonnet-4-6 call responds)
#   FAKE_OPUS_WRITE   = valid | empty (what an "ok" Opus call writes to brief.json)
#   FAKE_SONNET_WRITE = valid | empty (what an "ok" Sonnet call writes to brief.json)
# A "block" simulates the Anthropic AUP classifier rejection (non-zero exit).
#
# Run: bash tests/test_analyze.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

# --- tiny assert helpers ----------------------------------------------------
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

assert_eq() { # $1=actual $2=expected $3=msg
    if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (got '$1', want '$2')"; fi
}
assert_contains() { # $1=haystack-file $2=needle $3=msg
    if grep -q -- "$2" "$1"; then ok "$3"; else bad "$3 (missing '$2')"; fi
}
assert_not_contains() { # $1=haystack-file $2=needle $3=msg
    if grep -q -- "$2" "$1"; then bad "$3 (unexpected '$2')"; else ok "$3"; fi
}

# --- harness: build an isolated workdir with a fake claude ------------------
make_workdir() {
    local dir; dir="$(mktemp -d)"
    cp "$REPO_ROOT/analyze.sh" "$dir/analyze.sh" 2>/dev/null || true
    # minimal prompt file with the {{DATE}} placeholder analyze.sh substitutes
    printf 'Analyze for {{DATE}} and write docs/data/brief.json\n' > "$dir/analyze_prompt.md"
    # fake claude binary
    cat > "$dir/fake_claude" <<'FAKE'
#!/bin/bash
# Decide which model is being exercised from the args.
model="opus"
for a in "$@"; do
    [ "$a" = "claude-sonnet-4-6" ] && model="sonnet"
done
if [ "$model" = "sonnet" ]; then
    result="${FAKE_SONNET:-ok}"; write="${FAKE_SONNET_WRITE:-valid}"
else
    result="${FAKE_OPUS:-ok}"; write="${FAKE_OPUS_WRITE:-valid}"
fi

if [ "$result" = "block" ]; then
    echo "API Error: ... violate our Usage Policy ... violative cyber content ..." >&2
    exit 3
fi

# "ok" → write the brief and exit 0
if [ "$write" = "empty" ]; then
    printf '{"generated_at":"x","incident_count":0,"incidents":[]}\n' > "$BRIEF_PATH"
else
    printf '{"generated_at":"x","incident_count":1,"incidents":[{"id":"1","victim":"Acme"}]}\n' > "$BRIEF_PATH"
fi
exit 0
FAKE
    chmod +x "$dir/fake_claude"
    echo "$dir"
}

# run_case: prints exit code; writes combined output to $OUT_FILE
run_case() {
    local dir="$1"
    ( cd "$dir" \
        && DATE=2026-06-07 \
           CLAUDE_BIN="$dir/fake_claude" \
           BRIEF_PATH="$dir/brief.json" \
           PROMPT_FILE="$dir/analyze_prompt.md" \
           RETRY_SLEEP=0 \
           bash "$dir/analyze.sh" >"$OUT_FILE" 2>&1 )
    echo $?
}

echo "== analyze.sh tests =="

# Case 1: Opus blocked, Sonnet works → overall success via fallback
d="$(make_workdir)"; OUT_FILE="$d/out.log"
rc="$(FAKE_OPUS=block FAKE_SONNET=ok run_case "$d")"
assert_eq "$rc" "0" "opus-blocked/sonnet-ok exits 0"
assert_contains "$OUT_FILE" "Sonnet 4.6 fallback" "reaches Sonnet fallback attempt"
assert_eq "$(python3 -c "import json;print(json.load(open('$d/brief.json'))['incident_count'])")" "1" "brief written by fallback"

# Case 2: Opus succeeds on first try → no fallback used
d="$(make_workdir)"; OUT_FILE="$d/out.log"
rc="$(FAKE_OPUS=ok FAKE_SONNET=ok run_case "$d")"
assert_eq "$rc" "0" "opus-ok-first-try exits 0"
assert_not_contains "$OUT_FILE" "Sonnet 4.6 fallback" "does not reach fallback when Opus works"

# Case 3: every attempt blocked → overall failure (non-zero exit)
d="$(make_workdir)"; OUT_FILE="$d/out.log"
rc="$(FAKE_OPUS=block FAKE_SONNET=block run_case "$d")"
assert_eq "$rc" "1" "all-blocked exits non-zero"
assert_contains "$OUT_FILE" "FAILED on all attempts" "reports total failure"

# Case 4: Opus exits 0 but writes an empty brief → validation forces fallback to Sonnet
d="$(make_workdir)"; OUT_FILE="$d/out.log"
rc="$(FAKE_OPUS=ok FAKE_OPUS_WRITE=empty FAKE_SONNET=ok FAKE_SONNET_WRITE=valid run_case "$d")"
assert_eq "$rc" "0" "exit0-but-empty-brief still recovers via fallback"
assert_contains "$OUT_FILE" "Sonnet 4.6 fallback" "validation gate escalates past clean-exit empty brief"

echo
echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
