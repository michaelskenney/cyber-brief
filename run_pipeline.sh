#!/bin/bash
set -eo pipefail
cd "$(dirname "$0")"

export DATE=$(date -u '+%Y-%m-%d')
LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline-$DATE.log"

# Load .env for email credentials
set -a
source .env
set +a

# Ensure we're on the main branch — the pipeline must commit and push to main
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "WARNING: Not on main branch (on '$CURRENT_BRANCH'). Switching to main."
    git checkout main
fi

# Portable timeout wrapper (macOS lacks GNU timeout)
run_with_timeout() {
    local secs=$1; shift
    "$@" &
    local cmd_pid=$!
    ( sleep "$secs" && kill "$cmd_pid" 2>/dev/null ) &
    local watchdog_pid=$!
    if wait "$cmd_pid" 2>/dev/null; then
        kill "$watchdog_pid" 2>/dev/null
        wait "$watchdog_pid" 2>/dev/null
        return 0
    else
        local rc=$?
        kill "$watchdog_pid" 2>/dev/null
        wait "$watchdog_pid" 2>/dev/null
        if [ $rc -eq 137 ] || [ $rc -eq 143 ]; then
            echo "ERROR: Command timed out after ${secs}s"
        fi
        return $rc
    fi
}

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

# Guard against stale/hung pipeline from a previous run.
# Launchd won't start a new instance while the old one is still running.
PIDFILE="data/logs/pipeline.pid"
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ERROR: Previous pipeline run (PID $OLD_PID) is still running. Killing it."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$OLD_PID" 2>/dev/null || true
    fi
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

echo "=== Stage 1: Fetch (Exa) ==="
run_with_timeout 300 python3 fetch.py --date "$DATE"

echo "=== Stage 2: Analyze (Claude Code) ==="
run_with_timeout 600 claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob

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
lines.append("https://michaelskenney.github.io/cyber-brief/")
print("\n".join(lines))
PYEOF
)

send_email "Cyber Brief — $INCIDENT_COUNT incidents ($DATE)" "$EMAIL_BODY"
