# CLAUDE.md — Cyber Threat Daily Brief
## Context handoff for Claude Code

This file captures decisions, constraints, and design choices for this project.
Read this before making any changes.

---

## What this project is

An automated cyber threat intelligence dashboard that:
- Runs a 3-stage pipeline every 12 hours via macOS launchd
- Stage 1: `fetch.py` pulls raw content from 26 approved sources via the Exa REST API
- Stage 2: Claude Code CLI analyzes the raw content and writes structured JSON
- Stage 3: `publish.sh` commits and pushes to GitHub
- A static GitHub Pages frontend reads the JSON and renders a filterable table
- No server, no database, no manual intervention after setup

---

## Project file structure

```
cyber-brief/
├── CLAUDE.md                              ← this file
├── README.md                              ← user-facing setup instructions
├── fetch.py                               ← Stage 1: Exa content retrieval
├── analyze_prompt.md                      ← Stage 2: Claude Code analysis prompt
├── publish.sh                             ← Stage 3: git commit + push
├── run_pipeline.sh                        ← Pipeline wrapper (chains all stages)
├── sources.json                           ← Approved source list (single source of truth)
├── requirements.txt                       ← Python dependencies (requests, python-dotenv, pytest)
├── .env.example                           ← API key template
├── com.cyberbrief.refresh.plist           ← macOS launchd schedule (noon + midnight)
├── generate_brief.py                      ← Legacy: Anthropic API fallback (manual GH Actions)
├── tests/
│   └── test_fetch.py                      ← Unit tests for fetch.py
├── data/
│   ├── raw/{date}/                        ← Raw fetched content (local only, gitignored)
│   └── logs/                              ← Pipeline logs (local only, gitignored)
├── docs/
│   ├── index.html                         ← Dashboard frontend (GitHub Pages)
│   └── data/
│       ├── brief.json                     ← Generated incident data
│       └── usage_log.jsonl                ← Per-run usage tracking
└── .github/workflows/
    └── refresh_brief.yml                  ← Manual-trigger fallback only (not scheduled)
```

---

## Pipeline architecture

### Stage 1: Fetch (`fetch.py`)
- Uses the **Exa REST API** to search each approved source domain
- Searches last 48 hours first; expands to 14 days if fewer than 2 results
- Caps at 5 articles per source, 1500 words per article, 120K total words
- Writes one JSON file per source to `data/raw/{date}/`
- Writes `_fetch_summary.json` with success/failure counts
- Requires `EXA_API_KEY` in `.env` (also `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `NOTIFY_EMAIL` for notifications)
- Retries once on transient HTTP errors (429, 5xx)
- Fails the pipeline if fewer than half the sources succeed

### Stage 2: Analyze (Claude Code CLI)
- `run_pipeline.sh` invokes: `claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob`
- Claude Code reads the raw content from `data/raw/{date}/`, applies attacker naming rules, deduplicates, and writes `docs/data/brief.json`
- Also appends a usage record to `docs/data/usage_log.jsonl`
- After Claude Code finishes, the pipeline stamps an accurate `generated_at` timestamp

### Stage 3: Publish (`publish.sh`)
- Stages `docs/data/brief.json` and `docs/data/usage_log.jsonl`
- Commits with message `chore: refresh cyber brief {date}`
- Pulls with rebase, then pushes to `origin main`
- Aborts rebase on conflict and exits with error

### Orchestration (`run_pipeline.sh`)
- Chains all three stages sequentially
- Loads `.env` for API keys and email credentials
- Logs all output to `data/logs/pipeline-{date}.log`
- Sends email notification on success (incident count + dashboard link) or failure (log path)
- Cleans up raw data older than 30 days

### Email notifications
- Uses Gmail SMTP (SSL on port 465) with an app password
- Credentials stored in `.env`: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `NOTIFY_EMAIL`
- Success email: subject includes incident count and date
- Failure email: triggered via ERR trap, includes log file path

### Scheduling
- **Primary:** macOS launchd via `com.cyberbrief.refresh.plist` — runs at noon and midnight local time
- **Important:** Use `launchctl bootstrap gui/$(id -u)` to register the job (not the deprecated `launchctl load`)
- **Fallback:** GitHub Actions workflow (`refresh_brief.yml`) — manual trigger only, uses the legacy `generate_brief.py` with the Anthropic API + web search tool. Requires `ANTHROPIC_API_KEY` GitHub secret.

---

## The 26 agreed intelligence sources

Defined in `sources.json` (single source of truth). Do not add or remove
without explicit user approval.

### Industry / Threat Intelligence
- crowdstrike.com/blog
- cloud.google.com/blog/topics/threat-intelligence  (Google / Mandiant)
- unit42.paloaltonetworks.com
- microsoft.com/en-us/security/blog  (MSTIC)
- blog.talosintelligence.com  (Cisco Talos)
- recordedfuture.com/research
- darkreading.com
- krebsonsecurity.com

### Government & Regulatory (US)
- cisa.gov/news-events/cybersecurity-advisories
- ic3.gov  (FBI)
- justice.gov/news  (DOJ — filter for cyber/indictments)
- home.treasury.gov/news  (OFAC sanctions)
- fincen.gov/resources/advisories
- nsa.gov/Press-Room/Cybersecurity-Advisories-Guidance

### Government & Regulatory (Allied)
- ncsc.gov.uk/news  (UK)
- cyber.gov.au/about-us/news  (Australia — ACSC)
- enisa.europa.eu/news  (EU)

### Regulatory (Financial / SEC)
- efts.sec.gov  (EDGAR 8-K Item 1.05 — public company material breach disclosures)
- sec.gov/litigation  (SEC enforcement actions)
- dfs.ny.gov/enforcement  (NYDFS consent orders — lagging signal, high detail)

### News
- reuters.com/technology/cybersecurity
- bloomberg.com/technology
- therecord.media  (The Record by Recorded Future)

### Trusted Voices / Open Source
- risky.biz  (Risky Business)
- isc.sans.edu  (SANS Internet Storm Center)
- cyberscoop.com

---

## Table column specification

The frontend table has exactly these 8 columns in this order:

| Column | Notes |
|---|---|
| Date | Display string; sorted by `date_sort` field (YYYY-MM-DD) descending |
| Victim | Organization or sector name; color-coded by severity |
| Industry | Sector of the victim |
| Attacker | Plain executive language — see naming rules below |
| Motivation | Rendered as a colored chip |
| Attack vector | One concise sentence |
| Impact | One to two concise sentences |
| Ongoing | Y / N — rendered as red "Yes" or green "No" badge |

---

## Attacker naming rules — CRITICAL

The attacker field must use plain executive language only.

### NEVER use:
Fancy Bear, Cozy Bear, Sandworm, Lazarus Group, Kimsuky, APT28, APT29, APT41,
APT40, Volt Typhoon, Salt Typhoon, Silk Typhoon, MuddyWater, Seedworm,
Static Kitten, Handala Hack, Void Manticore, Laundry Bear, Void Blizzard,
Gamaredon, Turla, BlackCat, AlphV, TridentLocker, or any other vendor codename.

### ALWAYS use plain language like:
- "Russia — GRU military intelligence"
- "Russia — FSB intelligence service"
- "Russia — state-linked espionage group"
- "Iran — Ministry of Intelligence (MOIS)"
- "Iran — IRGC (Islamic Revolutionary Guard Corps)"
- "Iran — state-directed hacktivist proxies"
- "China — state-suspected espionage group"
- "China — PLA military intelligence"
- "North Korea — state-sponsored, financially motivated"
- "Criminal gang — ransomware"
- "Criminal gang — data extortion"
- "Unknown"
- "Unknown — criminal likely"

### attacker_origin field (used for color-coding in the frontend):
Must be one of: `russia` | `iran` | `china` | `north_korea` | `criminal` | `unknown`

### Attacker color key (in frontend):
- Russia → red (#f87171)
- Iran → orange (#fb923c)
- China → yellow (#facc15)
- North Korea → purple (#c084fc)
- Criminal gang → gray (#94a3b8)
- Unknown → dark gray (#64748b)

---

## Motivation field values

Must be exactly one of these strings (used for CSS chip class):
- `Financial`
- `Espionage`
- `Disruption`
- `IP theft`
- `Political`
- `Unclear`

---

## Severity field values

Must be exactly one of: `critical` | `high` | `medium` | `low`

Victim name color by severity:
- critical → #fca5a5 (red)
- high → #fdba74 (orange)
- medium → #fde68a (yellow)
- low → #93c5fd (blue)

---

## brief.json schema

```json
{
  "generated_at": "ISO-8601 UTC timestamp",
  "period_searched": "Human-readable e.g. March 15-17, 2026",
  "incident_count": 12,
  "incidents": [
    {
      "id": "1",
      "date": "Display string e.g. Mar 16 or Early Feb",
      "date_sort": "YYYY-MM-DD for sort order",
      "victim": "Organization or sector name",
      "industry": "Industry sector",
      "attacker": "Plain-language per naming rules above",
      "attacker_origin": "russia|iran|china|north_korea|criminal|unknown",
      "motivation": "Financial|Espionage|Disruption|IP theft|Political|Unclear",
      "vector": "One sentence on how the attack was carried out",
      "impact": "One to two sentences on what happened and known consequences",
      "ongoing": "Y|N",
      "severity": "critical|high|medium|low",
      "sources": ["source name or domain"]
    }
  ]
}
```

---

## Frontend (docs/index.html) — key behaviours

- Fetches `data/brief.json?t={timestamp}` on load (cache-busted)
- Re-fetches every 60 seconds passively — updates in place if new data is found
- Shows "Last refreshed" and "Next refresh" timestamps in the header
- Status dot: green = live, yellow/amber = data older than 13 hours
- Filter buttons: All / Critical / High / Medium / Low
- All HTML is generated from the JSON — no hardcoded incident data in the HTML

---

## Important context: SEC vs NYDFS reporting regimes

Key facts for any future work involving these sources:

**SEC (EDGAR Item 1.05 on Form 8-K):**
- Public companies must disclose material cyber incidents within 4 business days
- Reports ARE public — searchable via EDGAR full-text search
- Real-time signal — this is on the agreed source list
- URL: `efts.sec.gov/LATEST/search-index?q=%221.05%22`

**NYDFS (23 NYCRR Part 500):**
- NY-licensed banks, insurers, fintechs must notify DFS within 72 hours
- The 72-hour incident notifications are CONFIDENTIAL supervisory information
- NOT public — they sit with DFS and are not searchable
- What IS public: enforcement actions (consent orders, penalties) at dfs.ny.gov/enforcement
- These are lagging (months to years after the incident) but technically detailed
- This is on the agreed source list for that reason

---

## Style and tone conventions

- Dark theme: background #0f172a, surface #1e293b
- No external CSS frameworks — pure inline styles and a small `<style>` block
- No external JS frameworks in index.html — plain vanilla JS only
- Incident summaries: factual, no vendor marketing language
- Attacker field: always executive-readable (see naming rules above)
- Source attribution: show source domain/name under each victim name in smaller text
