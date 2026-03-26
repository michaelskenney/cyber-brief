# Cyber Threat Daily Brief

**Live dashboard:** [michaelskenney.github.io/cyber-brief](https://michaelskenney.github.io/cyber-brief/)

An automated cyber threat intelligence dashboard that aggregates incidents from 26 vetted sources every 12 hours. No server, no database — just a local pipeline and a static GitHub Pages frontend.

Built for security leaders who need a concise, filterable view of what happened overnight without logging into a dozen portals.

## How it works

```
sources.json (26 approved sources)
     │
     ▼
  fetch.py             ← Exa REST API pulls articles from each source domain
     │
     ▼
  data/raw/{date}/     ← Raw content saved locally (one JSON per source)
     │
     ▼
  Claude Code CLI      ← Reads raw content, deduplicates, writes structured brief.json
     │
     ▼
  publish.sh           ← git commit + push to GitHub
     │
     ▼
  GitHub Pages         ← docs/index.html reads brief.json, renders filterable dashboard
```

The pipeline runs via `run_pipeline.sh` and is scheduled through macOS `launchd` at noon and midnight daily.

## Dashboard features

- Dark-themed filterable table with 8 columns: Date, Victim, Industry, Attacker, Motivation, Attack Vector, Impact, Ongoing
- Severity filters: All / Critical / High / Medium / Low
- Color-coded attacker origins (Russia, Iran, China, North Korea, Criminal, Unknown)
- Motivation chips (Financial, Espionage, Disruption, IP Theft, Political, Unclear)
- Auto-refreshes every 60 seconds; status indicator shows data freshness
- Plain executive language — no vendor codenames or jargon

## Intelligence sources

Content is fetched exclusively from 26 approved domains defined in `sources.json`:

| Category | Sources |
|---|---|
| **Industry / Threat Intel** | CrowdStrike, Google/Mandiant, Unit 42, Microsoft MSTIC, Cisco Talos, Recorded Future, Dark Reading, Krebs on Security |
| **US Government** | CISA, FBI (IC3), DOJ, Treasury/OFAC, FinCEN, NSA |
| **Allied Government** | UK NCSC, Australia ACSC, EU ENISA |
| **Regulatory** | SEC EDGAR (8-K Item 1.05), SEC Enforcement, NYDFS Enforcement |
| **News** | Reuters, Bloomberg, The Record |
| **Trusted Voices** | Risky Business, SANS ISC, CyberScoop |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/michaelskenney/cyber-brief.git
cd cyber-brief
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add:

| Variable | Required | Purpose |
|---|---|---|
| `EXA_API_KEY` | Yes | [Exa API](https://exa.ai/) key for the fetch stage |
| `GMAIL_USER` | No | Gmail address for pipeline notifications |
| `GMAIL_APP_PASSWORD` | No | Gmail [app password](https://myaccount.google.com/apppasswords) |
| `NOTIFY_EMAIL` | No | Recipient for success/failure emails |

Claude Code handles its own authentication — no Anthropic API key needed for the primary pipeline.

### 3. Enable GitHub Pages

1. Go to your repo **Settings > Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / folder: `/docs`
4. Save

### 4. Run the pipeline

```bash
./run_pipeline.sh
```

This fetches from all sources, analyzes with Claude Code, and pushes results to GitHub Pages.

### 5. Schedule automatic runs (optional)

```bash
cp com.cyberbrief.refresh.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cyberbrief.refresh.plist
```

> Use `launchctl bootstrap` (not the deprecated `launchctl load`). To re-register after changes: `launchctl bootout gui/$(id -u)/com.cyberbrief.refresh` then bootstrap again.

## Running individual stages

```bash
# Fetch only
python3 fetch.py

# Fetch for a specific date
python3 fetch.py --date 2026-03-20

# Analyze only (requires raw data from a prior fetch)
DATE=$(date -u '+%Y-%m-%d')
claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob

# Publish only
./publish.sh

# Serve the dashboard locally
cd docs && python3 -m http.server 8080
```

## Project structure

```
cyber-brief/
├── fetch.py                        # Stage 1: Exa content retrieval
├── analyze_prompt.md               # Stage 2: Claude Code analysis prompt
├── publish.sh                      # Stage 3: git commit + push
├── run_pipeline.sh                 # Pipeline orchestrator
├── sources.json                    # Approved source list (single source of truth)
├── requirements.txt                # Python dependencies
├── .env.example                    # API key template
├── generate_brief.py               # Legacy: Anthropic API fallback (GitHub Actions)
├── tests/
│   └── test_fetch.py               # Unit tests for fetch.py
├── data/
│   ├── raw/{date}/                 # Raw fetched content (local, gitignored)
│   └── logs/                       # Pipeline logs (local, gitignored)
├── docs/
│   ├── index.html                  # Dashboard frontend (GitHub Pages)
│   └── data/
│       ├── brief.json              # Generated incident data
│       └── usage_log.jsonl         # Per-run usage tracking
├── .github/workflows/
│   └── refresh_brief.yml           # Manual-trigger fallback (GitHub Actions)
└── com.cyberbrief.refresh.plist    # macOS launchd schedule
```

## GitHub Actions fallback

The `generate_brief.py` script (Anthropic API + web search) is available as a manual fallback via GitHub Actions if the local pipeline is unavailable. Requires an `ANTHROPIC_API_KEY` GitHub secret.

## Tests

```bash
python3 -m pytest tests/ -v
```
