#!/bin/bash
set -e
cd "$(dirname "$0")"

# Abort any in-progress rebase on failure
trap 'git rebase --abort 2>/dev/null' ERR

# Verify we're on main — pipeline should never publish from another branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "ERROR: publish.sh must run on the main branch (currently on '$CURRENT_BRANCH')"
    exit 1
fi

git add docs/data/brief.json docs/data/usage_log.jsonl
if git diff --staged --quiet; then
    echo "No changes to commit"
    exit 0
fi
git commit -m "chore: refresh cyber brief $(date -u '+%Y-%m-%d %H:%M UTC')"
git pull --rebase origin main || {
    echo "ERROR: rebase failed (likely merge conflict). Aborting."
    git rebase --abort
    exit 1
}

# Push with retry (up to 4 attempts with exponential backoff)
PUSH_OK=0
for ATTEMPT in 1 2 3 4; do
    if git push origin main; then
        PUSH_OK=1
        break
    fi
    DELAY=$((2 ** ATTEMPT))
    echo "Push attempt $ATTEMPT failed. Retrying in ${DELAY}s..."
    sleep "$DELAY"
done

if [ "$PUSH_OK" -ne 1 ]; then
    echo "ERROR: git push failed after 4 attempts"
    exit 1
fi
