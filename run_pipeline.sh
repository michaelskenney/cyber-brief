#!/bin/bash
set -eo pipefail
cd "$(dirname "$0")"

DATE=$(date -u '+%Y-%m-%d')
LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline-$DATE.log"

# Tee all output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Pipeline started: $DATE ==="

echo "=== Stage 1: Fetch (Exa) ==="
python3 fetch.py --date "$DATE"

echo "=== Stage 2: Analyze (Claude Code) ==="
claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob

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
