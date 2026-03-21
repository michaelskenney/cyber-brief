# Exa Pipeline Rearchitecture — Design Spec

**Date:** 2026-03-20
**Status:** Draft
**Goal:** Replace the monolithic Sonnet + web_search approach with a staged pipeline: Exa fetches raw content, Claude Code analyzes it, publish script pushes to GitHub Pages.

---

## Motivation

The current `generate_brief.py` uses Claude Sonnet with the built-in `web_search` tool in a single API call. This has several problems:

- **Cost opacity** — web search tokens dominate the bill but are hard to predict or control
- **Coupled concerns** — fetching and analysis happen in one black box
- **No raw data retention** — you can't re-analyze without re-fetching
- **Limited model choice** — locked to Sonnet because it drives the search loop

The new architecture separates fetching (Exa) from analysis (Claude Code / Opus), giving control, visibility, and a raw content archive.

---

## Architecture Overview

Three discrete stages, chained by a wrapper script:

```
sources.json
     │
     ▼
  fetch.py          ← Exa REST API (search + crawl per source)
     │
     ▼
  data/raw/{date}/  ← Raw content saved locally
     │
     ▼
  Claude Code       ← Reads raw content + analysis prompt, writes brief.json
     │
     ▼
  publish.sh        ← git commit + push to GitHub → GitHub Pages updates
```

---

## File Structure

```
cyber-brief/
├── fetch.py                        # Stage 1: Exa content retrieval
├── analyze_prompt.md               # Dedicated prompt file for Claude Code analysis
├── publish.sh                      # Stage 3: git commit + push
├── run_pipeline.sh                 # Wrapper that chains all stages
├── sources.json                    # The 26 approved sources (single source of truth)
├── .env                            # EXA_API_KEY (gitignored)
├── data/
│   ├── raw/
│   │   └── 2026-03-20/            # One folder per run date
│   │       ├── crowdstrike.json
│   │       ├── cisa.json
│   │       ├── _fetch_summary.json # Per-source success/fail status
│   │       └── ...
│   └── logs/                       # launchd stdout/stderr logs
├── docs/
│   ├── index.html                  # Frontend (unchanged)
│   └── data/
│       ├── brief.json              # Output (same schema as today)
│       └── usage_log.jsonl         # Token/usage tracking
├── .github/workflows/
│   └── refresh_brief.yml           # Kept as manual-trigger fallback only
└── com.cyberbrief.refresh.plist    # launchd schedule (~/Library/LaunchAgents/)
```

---

## Stage 1: `fetch.py`

**Purpose:** Iterate through `sources.json`, call Exa REST API for each source, save raw article content to `data/raw/{date}/`.

**Input:** `sources.json` — array of source objects:
```json
[
  {
    "id": "crowdstrike",
    "domain": "crowdstrike.com/blog",
    "category": "Industry / Threat Intelligence"
  }
]
```

**Exa API calls per source:**

Exa's REST API has two relevant endpoints:

1. **`POST /search`** — search with `include_domains` filter for the source domain. Request includes `contents: { text: true }` to return full article text inline (avoiding a separate crawl call). Date-limited via `start_published_date` to the last 48 hours, expanding to 14 days if fewer than 2 results. Search type: `"auto"`.
2. **`POST /contents`** (fallback only) — if `/search` returns URLs but truncated/missing text, call `/contents` with those URLs to get full page text. Most cases should be handled by step 1 alone.

Each article is capped at 1,500 words to control context window size. Maximum 5 articles per source. Single retry with 2-second backoff on transient failures (429, 5xx).

**Output per source** — `data/raw/{date}/{source_id}.json`:
```json
{
  "source_id": "crowdstrike",
  "domain": "crowdstrike.com/blog",
  "fetched_at": "2026-03-20T06:00:12+00:00",
  "article_count": 3,
  "articles": [
    {
      "title": "...",
      "url": "...",
      "published_date": "...",
      "content": "full article text"
    }
  ]
}
```

**Summary file** — `data/raw/{date}/_fetch_summary.json`:
```json
{
  "date": "2026-03-20",
  "fetched_at": "2026-03-20T06:01:45+00:00",
  "total_sources": 26,
  "succeeded": 24,
  "failed": 2,
  "total_articles": 87,
  "failures": [
    {"source_id": "ic3", "error": "Exa returned 0 results"}
  ]
}
```

**Error handling:**
- If Exa fails for a single source, log the error and continue to the next source.
- Exit code 0 if at least half the sources (13+) succeeded.
- Exit code 1 otherwise (stops the pipeline).

**Date handling:** `fetch.py` accepts an optional `--date YYYY-MM-DD` argument, defaulting to today's UTC date. This is passed by `run_pipeline.sh`.

**Dependencies:** `requests` for Exa REST API calls, `python-dotenv` for loading `.env`. `EXA_API_KEY` from environment or `.env` file.

---

## Stage 2: Claude Code Analysis

**Purpose:** Read raw content from `data/raw/{date}/`, apply threat intelligence analysis, produce `docs/data/brief.json`.

**Invocation:**
```bash
DATE=$(date -u '+%Y-%m-%d')
claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob
```

The wrapper script injects today's date into the prompt via `{{DATE}}` placeholder substitution.

**`analyze_prompt.md`** contains:
- `{{DATE}}` placeholder (replaced at invocation time with the current UTC date)
- Instructions to read all files in `data/raw/{{DATE}}/`
- The full analysis rules (attacker naming, severity, motivation, deduplication)
- The `brief.json` schema to output
- Instructions to write the result to `docs/data/brief.json`

The analysis rules currently live in `CLAUDE.md` and will be referenced or duplicated in the prompt file. Claude Code also reads `CLAUDE.md` automatically, so the attacker naming rules and schema are always in context.

**What Claude Code does:**
1. Reads `_fetch_summary.json` to understand what was fetched
2. Reads each source's raw JSON file
3. Identifies reportable incidents across all sources
4. Deduplicates (same incident covered by multiple sources → one entry)
5. Applies attacker naming rules (no vendor codenames)
6. Assigns severity, motivation, ongoing status
7. Writes `docs/data/brief.json` in the existing schema
8. Appends a usage entry to `docs/data/usage_log.jsonl`

**`usage_log.jsonl` entry schema:**
```json
{
  "timestamp": "2026-03-20T06:02:30+00:00",
  "date": "2026-03-20",
  "pipeline": "exa+claude-code",
  "sources_fetched": 24,
  "sources_failed": 2,
  "total_articles": 87,
  "incident_count": 11,
  "model": "claude-opus-4-6"
}
```

**`brief.json` schema** — identical to today, no changes:
```json
{
  "generated_at": "ISO-8601 UTC timestamp",
  "period_searched": "Human-readable e.g. March 18-20, 2026",
  "incident_count": 12,
  "incidents": [
    {
      "id": "1",
      "date": "Mar 19",
      "date_sort": "2026-03-19",
      "victim": "...",
      "industry": "...",
      "attacker": "Plain-language per CLAUDE.md naming rules",
      "attacker_origin": "russia|iran|china|north_korea|criminal|unknown",
      "motivation": "Financial|Espionage|Disruption|IP theft|Political|Unclear",
      "vector": "...",
      "impact": "...",
      "ongoing": "Y|N",
      "severity": "critical|high|medium|low",
      "sources": ["source name or domain"]
    }
  ]
}
```

**Context window consideration:** Opus has a 200K token context window. With per-source caps (5 articles, 1,500 words each), the theoretical maximum is 26 × 5 × 1,500 = ~195K words, which would exceed the window. To prevent this, `fetch.py` enforces a **hard total budget of 120K words (~160K tokens)** across all sources. Articles are included newest-first until the budget is reached; remaining articles are dropped. This leaves ~40K tokens of headroom for the analysis prompt, CLAUDE.md, and output. In practice, most sources return 1-3 articles, so typical runs use ~80-120K tokens total and the budget cap rarely triggers.

---

## Stage 3: `publish.sh`

**Purpose:** Commit and push `brief.json` and `usage_log.jsonl` to GitHub.

```bash
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
```

---

## Pipeline Wrapper: `run_pipeline.sh`

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"

DATE=$(date -u '+%Y-%m-%d')
LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"

echo "=== Pipeline started: $DATE ===" | tee -a "$LOG_DIR/pipeline-$DATE.log"

echo "=== Stage 1: Fetch (Exa) ==="
python3 fetch.py --date "$DATE"

echo "=== Stage 2: Analyze (Claude Code) ==="
claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob

echo "=== Stage 3: Publish ==="
./publish.sh

echo "=== Pipeline complete ==="
```

Note: `fetch.py` loads `EXA_API_KEY` from `.env` via `python-dotenv`, so the wrapper script does not need to `source .env`. For `launchd`, the plist should specify full paths to `python3` and `claude` since it runs in a minimal shell environment.

---

## Scheduling: `launchd`

Plist file: `com.cyberbrief.refresh.plist`, installed to `~/Library/LaunchAgents/`.

- Runs `run_pipeline.sh` every 12 hours
- `EXA_API_KEY` is loaded by `python-dotenv` in `fetch.py` — no shell-level env setup needed in the plist
- The plist must specify full paths to `python3` and `claude` (launchd runs in a minimal environment without shell profile)
- Logs stdout/stderr to `data/logs/pipeline-{date}.log`

---

## Secrets Management

- **`EXA_API_KEY`** — stored in `.env` file in the project root, gitignored
- **No `ANTHROPIC_API_KEY` needed** — Claude Code handles its own authentication
- `.env` is added to `.gitignore`

---

## GitHub Actions: Manual Fallback

Keep `refresh_brief.yml` but remove the cron schedule. Change to `workflow_dispatch` only. This provides a fallback if the Mac is offline — the old Sonnet + web_search approach still works via the existing `generate_brief.py`.

---

## What Does NOT Change

- **`docs/index.html`** — the frontend is untouched, it reads `brief.json` as before
- **`brief.json` schema** — identical to today
- **`generate_brief.py`** — kept as-is for the GitHub Actions fallback
- **Attacker naming rules, severity definitions, motivation values** — all unchanged

---

## Testing Strategy

**Unit tests for `fetch.py`:**
- Mock Exa API responses, verify correct output file structure
- Test error handling: single source failure, majority failure, Exa rate limit
- Test date-range expansion logic (48h → 14 days)

**Integration test for fetch stage:**
- Live Exa call against 2-3 sources, verify real output

**Analysis prompt validation:**
- Feed known raw content through Claude Code, verify `brief.json` output matches schema
- Verify attacker naming rules are enforced (no vendor codenames in output)
- Verify deduplication works (same incident from multiple sources → one entry)

**End-to-end pipeline test:**
- Run `run_pipeline.sh` manually, verify `brief.json` is produced and valid
- Verify `usage_log.jsonl` gets a new entry

**`publish.sh` test:**
- Verify it exits cleanly with no changes
- Verify it commits and pushes when `brief.json` has changed

---

## Migration Notes

- **`sources.json`** must be created by extracting the `AGREED_SOURCES` list from `generate_brief.py`. The list in `CLAUDE.md` remains as documentation; `sources.json` becomes the single source of truth for code.
- **`generate_brief.py`** is kept as-is for the GitHub Actions fallback. It continues to use its own hardcoded source list.
- **`data/raw/` retention:** Add a cleanup step to `run_pipeline.sh` that deletes raw data folders older than 30 days to prevent unbounded disk growth.
- **`.gitignore`** must be updated to include `.env` and `data/raw/` (raw content stays local only).

---

## Future Considerations (Not in Scope)

- Switching Claude Code analysis back to direct API calls for full automation
- Adding new sources to `sources.json`
- Email/Slack alerting on critical incidents
- Historical brief archive (keeping past `brief.json` files)
- Raw content deduplication across days
- Including fetch summary stats in `usage_log.jsonl` for remote visibility
