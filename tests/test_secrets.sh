#!/bin/bash
# Tests for secrets.sh — the require_secret Keychain loader used by run_pipeline.sh.
#
# These tests inject a FAKE `security` binary (SECURITY_BIN) so no real Keychain
# access happens. The fake's behaviour is driven by the requested account name:
#   PRESENT                 -> prints a value, exit 0
#   EMPTY                   -> prints nothing, exit 0   (item exists but is empty)
#   anything else / MISSING -> exit 44 (errSecItemNotFound, like a real miss)
#
# Why this exists: run_pipeline.sh used `export VAR=$(security ...)`, which masks
# a lookup failure because `export` always returns 0. That silently turned a
# never-installed CLAUDE_CODE_OAUTH_TOKEN into an empty value for months. These
# tests pin the loud-failure contract so the regression can't return.
#
# Run: bash tests/test_secrets.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

# --- tiny assert helpers (same style as test_analyze.sh) --------------------
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
assert_eq() { # $1=actual $2=expected $3=msg
    if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (got '$1', want '$2')"; fi
}
assert_contains() { # $1=haystack-file $2=needle $3=msg
    if grep -q -- "$2" "$1"; then ok "$3"; else bad "$3 (missing '$2')"; fi
}

# --- harness: a fake `security` binary --------------------------------------
TMP="$(mktemp -d)"
FAKE="$TMP/security"
cat > "$FAKE" <<'FAKE'
#!/bin/bash
# Parse the -a <account> argument; ignore -s/-w (we only branch on account).
account=""
while [ $# -gt 0 ]; do
    if [ "$1" = "-a" ]; then account="$2"; shift 2; continue; fi
    shift
done
case "$account" in
    PRESENT) printf 'secret-value-123\n'; exit 0 ;;
    EMPTY)   printf '';                   exit 0 ;;
    *) echo "security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain." >&2
       exit 44 ;;
esac
FAKE
chmod +x "$FAKE"

# shellcheck source=/dev/null
source "$REPO_ROOT/secrets.sh"
export SECURITY_BIN="$FAKE"
export SECRET_SERVICE="cyber-brief"

echo "== secrets.sh (require_secret) tests =="

# Case 1: present secret → value on stdout, exit 0
out="$(require_secret PRESENT 2>/dev/null)"; rc=$?
assert_eq "$rc" "0" "present secret exits 0"
assert_eq "$out" "secret-value-123" "present secret returns its value"

# Case 2: missing secret → exit 1 with a loud FATAL diagnostic (NOT masked)
err="$TMP/err2"; require_secret MISSING >/dev/null 2>"$err"; rc=$?
assert_eq "$rc" "1" "missing secret exits 1 (failure is not masked)"
assert_contains "$err" "FATAL" "missing secret prints a FATAL line"
assert_contains "$err" "not found" "missing secret explains it was not found"

# Case 3: item exists but is empty → treated as failure
err="$TMP/err3"; require_secret EMPTY >/dev/null 2>"$err"; rc=$?
assert_eq "$rc" "1" "empty secret exits 1"
assert_contains "$err" "empty" "empty secret explains the emptiness"

# Case 4: missing token → actionable hint (setup-token, not an API key)
err="$TMP/err4"; require_secret CLAUDE_CODE_OAUTH_TOKEN >/dev/null 2>"$err"; rc=$?
assert_eq "$rc" "1" "missing token exits 1"
assert_contains "$err" "claude setup-token" "token hint points at 'claude setup-token'"
assert_contains "$err" "ANTHROPIC_API_KEY" "token hint warns off the metered API key (billing)"

# Case 5: regression guard for the ROOT CAUSE. `export VAR=$(...)` masks the
# failure (returns export's own 0); a bare `VAR=$(...)` propagates it. run_pipeline
# must use the bare form so set -e / `|| exit` can see the real exit code.
export FOO="$(require_secret MISSING 2>/dev/null)"; export_rc=$?
assert_eq "$export_rc" "0" "export VAR=\$(...) MASKS failure — the historical trap to avoid"
BAR="$(require_secret MISSING 2>/dev/null)"; bare_rc=$?
assert_eq "$bare_rc" "1" "bare VAR=\$(...) propagates failure — the safe pattern"

echo
echo "== $PASS passed, $FAIL failed =="
rm -rf "$TMP"
[ "$FAIL" -eq 0 ]
