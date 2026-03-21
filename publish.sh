#!/bin/bash
set -e
cd "$(dirname "$0")"

# Abort any in-progress rebase on failure
trap 'git rebase --abort 2>/dev/null' ERR

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
git push origin main
