#!/bin/bash
# Sourceable macOS Keychain secret loader for the cyber-brief pipeline.
#
# Bash analog of keychain.py (which serves the Python side). Reads ONE required
# secret from the login Keychain and FAILS LOUDLY if the item is missing or empty.
#
# Why this exists — the root-cause lesson:
#   run_pipeline.sh used `export VAR=$(security find-generic-password ...)`.
#   `export VAR=$(cmd)` returns the exit status of the `export` builtin — always 0
#   — NOT the exit status of the command substitution. So a missing Keychain item
#   silently produced an EMPTY value instead of aborting, and `claude` then fell
#   back to interactive credentials. That masked a never-installed
#   CLAUDE_CODE_OAUTH_TOKEN for months until the borrowed interactive login lapsed.
#
#   The fix is twofold: (1) this helper returns a real non-zero status the caller
#   can see, and (2) callers must use a BARE assignment — `VAR=$(require_secret X)`
#   — never `export VAR=$(require_secret X)`, so set -e / `|| exit` can act on it.
#
# Usage:
#   source "$(dirname "$0")/secrets.sh"
#   GMAIL_USER=$(require_secret GMAIL_USER); export GMAIL_USER   # bare, then export
#
# Configurable via env (defaults are the production values; overridden by tests):
#   SECRET_SERVICE  keychain service name          (default: cyber-brief)
#   SECURITY_BIN    path to the `security` binary   (default: security)

require_secret() {
    local account="$1"
    local service="${SECRET_SERVICE:-cyber-brief}"
    local bin="${SECURITY_BIN:-security}"
    local value

    # Bare assignment inside the function: `value=$(...)` takes the command
    # substitution's real exit status, so the `if !` below actually sees a miss.
    if ! value=$("$bin" find-generic-password -s "$service" -a "$account" -w 2>/dev/null); then
        echo "FATAL: Keychain secret '$service/$account' not found." >&2
        echo "       Add it with:  security add-generic-password -s $service -a $account -w" >&2
        if [ "$account" = "CLAUDE_CODE_OAUTH_TOKEN" ]; then
            echo "       Generate the value first with:  claude setup-token" >&2
            echo "       (a subscription-billed OAuth token — NOT an ANTHROPIC_API_KEY," >&2
            echo "        which would switch Stage 2 onto metered pay-as-you-go billing)." >&2
        fi
        return 1
    fi

    if [ -z "$value" ]; then
        echo "FATAL: Keychain secret '$service/$account' exists but is empty." >&2
        return 1
    fi

    printf '%s' "$value"
}
