#!/bin/bash
set -eo pipefail
cd "$(dirname "$0")"

export DATE=$(date -u '+%Y-%m-%d')
LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline-$DATE.log"

# Load secrets from macOS Keychain
export GMAIL_USER=$(security find-generic-password -s cyber-brief -a GMAIL_USER -w)
export GMAIL_APP_PASSWORD=$(security find-generic-password -s cyber-brief -a GMAIL_APP_PASSWORD -w)
export NOTIFY_EMAIL=$(security find-generic-password -s cyber-brief -a NOTIFY_EMAIL -w)

# Ensure we're on the main branch — the pipeline must commit and push to main
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "WARNING: Not on main branch (on '$CURRENT_BRANCH'). Switching to main."
    git checkout main
fi

# Send email notification via Gmail SMTP
send_email() {
    EMAIL_SUBJECT="$1" EMAIL_BODY="$2" python3 -c "
import smtplib, os
from email.mime.text import MIMEText
msg = MIMEText(os.environ['EMAIL_BODY'])
msg['Subject'] = os.environ['EMAIL_SUBJECT']
msg['From'] = os.environ['GMAIL_USER']
msg['To'] = os.environ['NOTIFY_EMAIL']
with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
    s.login(os.environ['GMAIL_USER'], os.environ['GMAIL_APP_PASSWORD'])
    s.send_message(msg)
" 2>/dev/null || echo "WARNING: email notification failed"
}

# Notify on failure (trap fires before set -e exits)
notify_failure() {
    send_email "Cyber Brief FAILED — $DATE" "Pipeline failed. Check log: $LOG_FILE"
}
trap notify_failure ERR

# Tee all output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Pipeline started: $DATE ==="

echo "=== Stage 1: Fetch (Exa) ==="
python3 fetch.py --date "$DATE"

echo "=== Stage 2: Analyze (Claude Code) ==="
# Pinned to Sonnet 4.6: Opus 4.7 is currently blocked by Anthropic's AUP
# classifier on this workload (cyber threat intel). Revisit once the Cyber
# Verification Program application is approved.
claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --model claude-sonnet-4-6 --allowedTools Read,Write,Edit,Glob

# Stamp accurate generated_at timestamp (Claude Code may use a rounded time)
python3 -c "
import json
from datetime import datetime, timezone
path = 'docs/data/brief.json'
with open(path) as f:
    data = json.load(f)
data['generated_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f'  generated_at stamped: {data[\"generated_at\"]}')
"

echo "=== Stage 3: Publish ==="
./publish.sh

echo "=== Cleanup: remove raw data older than 30 days ==="
find data/raw -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true

echo "=== Pipeline complete ==="

# Clear the ERR trap — publish succeeded, email failures should not trigger a
# misleading "pipeline failed" notification.
trap - ERR

# Build success email with incident summary
INCIDENT_COUNT=$(python3 -c "import json; print(json.load(open('docs/data/brief.json'))['incident_count'])" 2>/dev/null || echo "?")

EMAIL_BODY=$(python3 << 'PYEOF'
import json, os
date = os.environ.get("DATE", "unknown")
with open("docs/data/brief.json") as f:
    data = json.load(f)
incidents = data.get("incidents", [])
count = data.get("incident_count", len(incidents))
lines = [f"Cyber Brief — {count} incidents for {date}", ""]
for i, inc in enumerate(incidents, 1):
    sev = inc.get("severity", "").upper()
    victim = inc.get("victim", "Unknown")
    lines.append(f"  {i}. [{sev}] {victim}")
lines.append("")
lines.append("View full dashboard:")
lines.append("https://cyber-brief.pages.dev/")
print("\n".join(lines))
PYEOF
)

send_email "Cyber Brief — $INCIDENT_COUNT incidents ($DATE)" "$EMAIL_BODY"
