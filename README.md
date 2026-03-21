# Cyber Threat Daily Brief

Automated cyber threat intelligence dashboard that refreshes every 12 hours.
Runs locally on macOS via a staged pipeline, with GitHub Pages serving the dashboard.

## How it works

```
sources.json (approved source list)
     |
     v
  fetch.py             <-- Exa REST API fetches raw content per source
     |
     v
  data/raw/{date}/     <-- Raw articles saved locally (one JSON per source)
     |
     v
  Claude Code          <-- Reads raw content + analyze_prompt.md, writes brief.json
     |
     v
  publish.sh           <-- git commit + push to GitHub
     |
     v
  GitHub Pages         <-- docs/index.html reads brief.json, renders dashboard
```

The pipeline is orchestrated by `run_pipeline.sh` and scheduled via macOS `launchd` to run every 12 hours.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/michaelskenney/cyber-brief.git
cd cyber-brief
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

```bash
cp .env.example .env
# Edit .env and add your Exa API key
```

You need an [Exa API key](https://exa.ai/) for the fetch stage. Claude Code handles its own authentication (no Anthropic API key needed).

### 4. Enable GitHub Pages

1. Go to your repo > **Settings** > **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / folder: `/docs`
4. Click **Save**

### 5. Run the pipeline manually

```bash
./run_pipeline.sh
```

This fetches content from all approved sources, analyzes it with Claude Code, and pushes the results to GitHub Pages.

### 6. Set up scheduled runs (optional)

Install the launchd plist for automatic 12-hour runs:

```bash
cp com.cyberbrief.refresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cyberbrief.refresh.plist
```

## Running individual stages

```bash
# Fetch only (saves to data/raw/{date}/)
python3 fetch.py

# Fetch for a specific date
python3 fetch.py --date 2026-03-20

# Analyze only (requires raw data from a prior fetch)
DATE=$(date -u '+%Y-%m-%d')
claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob

# Publish only (commit + push brief.json)
./publish.sh

# Serve the dashboard locally
cd docs && python3 -m http.server 8080
```

## Files

```
cyber-brief/
├── fetch.py                        # Stage 1: Exa content retrieval
├── analyze_prompt.md               # Stage 2: Claude Code analysis prompt
├── publish.sh                      # Stage 3: git commit + push
├── run_pipeline.sh                 # Pipeline wrapper (chains all stages)
├── sources.json                    # Approved source list (single source of truth)
├── requirements.txt                # Python dependencies
├── .env.example                    # API key template
├── generate_brief.py               # Legacy: Anthropic API fallback (GitHub Actions)
├── tests/
|   └── test_fetch.py               # Unit tests for fetch.py
├── data/
|   ├── raw/{date}/                 # Raw fetched content (local only, gitignored)
|   └── logs/                       # Pipeline logs (local only, gitignored)
├── docs/
|   ├── index.html                  # Dashboard frontend (GitHub Pages)
|   └── data/
|       ├── brief.json              # Generated incident data
|       └── usage_log.jsonl         # Per-run usage tracking
├── .github/workflows/
|   └── refresh_brief.yml           # Manual-trigger fallback (GitHub Actions)
└── com.cyberbrief.refresh.plist    # macOS launchd schedule
```

## GitHub Actions fallback

The old `generate_brief.py` (Anthropic API + web search) is kept as a manual fallback. If your Mac is offline, you can trigger it from the GitHub Actions tab. It requires an `ANTHROPIC_API_KEY` GitHub secret.

## Approved source list

Sources are defined in `sources.json`. The pipeline fetches content exclusively from these domains:

**Industry / Threat Intelligence** -- crowdstrike.com, cloud.google.com (Mandiant), unit42.paloaltonetworks.com, microsoft.com (MSTIC), blog.talosintelligence.com, recordedfuture.com, darkreading.com, krebsonsecurity.com

**Government (US)** -- cisa.gov, ic3.gov, justice.gov, home.treasury.gov (OFAC), fincen.gov, nsa.gov

**Government (Allied)** -- ncsc.gov.uk, cyber.gov.au (ACSC), enisa.europa.eu

**News** -- reuters.com, bloomberg.com, therecord.media

**Regulatory** -- efts.sec.gov (EDGAR 8-K Item 1.05), sec.gov, dfs.ny.gov

**Trusted Voices** -- risky.biz, isc.sans.edu, cyberscoop.com

## Tests

```bash
python3 -m pytest tests/ -v
```
