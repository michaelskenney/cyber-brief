# CLAUDE.md — Cyber Threat Daily Brief
## Context handoff for Claude Code

This file captures the full history of decisions, constraints, and design choices
made during the development of this project in a Claude.ai conversation. Read this
before making any changes.

---

## What this project is

An automated cyber threat intelligence dashboard that:
- Runs a Python script every 12 hours via GitHub Actions
- The script calls the Anthropic API (with web search) to search 26 agreed sources
- Structures findings as JSON and commits them back to the repo
- A static GitHub Pages frontend reads the JSON and renders a filterable table
- No server, no database, no manual intervention after setup

Live URL (once deployed): `https://YOUR_ORG.github.io/cyber-brief/`

---

## Project file structure

```
cyber-brief/
├── CLAUDE.md                              ← this file
├── README.md                              ← user-facing setup instructions
├── generate_brief.py                      ← the agent script (runs in CI)
├── .github/
│   └── workflows/
│       └── refresh_brief.yml             ← GitHub Actions cron schedule
└── docs/                                  ← GitHub Pages root
    ├── index.html                         ← frontend (reads brief.json)
    └── data/
        └── brief.json                     ← auto-generated output, committed by CI
```

---

## The 26 agreed intelligence sources

These are fixed. The generator must search ONLY these sources. Do not add or remove
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

The user explicitly requested that all proprietary vendor threat-actor codenames
be removed. The attacker field must use plain executive language only.

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

## GitHub Actions schedule

Runs at 06:00 and 18:00 UTC daily (cron: `0 6,18 * * *`).
Can be triggered manually from the Actions tab for the first run.

The workflow:
1. Checks out the repo
2. Installs `anthropic` Python package
3. Runs `generate_brief.py`
4. Commits updated `docs/data/brief.json` back to main
5. Pushes

Required GitHub secret: `ANTHROPIC_API_KEY`

---

## generate_brief.py — how it works

- Uses the `anthropic` Python SDK
- Model: `claude-sonnet-4-20250514`
- Tool: `web_search_20250305` (server-side web search — works correctly in CI)
- Loops up to 20 iterations handling `tool_use` stop reasons
- Parses JSON from `<BRIEF>...</BRIEF>` tags in the response
- Falls back to bare JSON regex if tags are missing
- Sorts incidents by `date_sort` descending before writing
- Exits with code 1 on any error (causes the GitHub Action to fail visibly)

### Key discovery from development:
The `web_search_20250305` tool ONLY works server-side (in the Python script running
in CI). It does NOT work when called from inside a browser artifact/widget because:
1. The artifact sandbox blocks the CORS preflight triggered by additional headers
2. The tool-use loop requires the client to return `tool_result` messages, which
   the browser cannot do correctly in the artifact environment

This is why the architecture uses GitHub Actions rather than a client-side API call.

---

## Frontend (docs/index.html) — key behaviours

- Fetches `data/brief.json?t={timestamp}` on load (cache-busted)
- Re-fetches every 60 seconds passively — updates in place if new data is found
- Shows "Last refreshed" and "Next refresh" timestamps in the header
- Status dot: green = live, yellow/amber = data older than 13 hours
- Filter buttons: All / Critical / High / Medium / Low
- All HTML is generated from the JSON — no hardcoded incident data in the HTML

---

## What was discussed but NOT yet built

These are natural next enhancements the user may ask for:

1. **Email / Slack alerting** — notify when a Critical incident is detected
2. **Historical archive** — keep past briefs rather than overwriting brief.json
3. **Deduplication tracking** — prevent the same incident appearing across multiple runs
4. **SEC EDGAR integration** — direct polling of EDGAR for 8-K Item 1.05 filings
   (these are already on the agreed source list but could have dedicated parsing)
5. **NYDFS enforcement portal** — noted as a lagging but high-detail signal;
   consent orders are detailed post-mortems, not real-time alerts
6. **Severity threshold alerting** — e.g. send a push notification if a Critical
   incident involves the financial sector

---

## Important context: SEC vs NYDFS reporting regimes

This was discussed at length. Key facts for any future work:

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

## Source document

This project was developed in a Claude.ai conversation that also produced:
- `cyber_threat_sources.docx` — a Word document listing and describing all 26 sources,
  including a comparison table of SEC vs NYDFS disclosure regimes
- `cyber_brief_march17.html` — a static one-off brief from March 17, 2026 used
  to validate the table format and attacker naming conventions before automating

---

## Style and tone conventions

- Dark theme: background #0f172a, surface #1e293b
- No external CSS frameworks — pure inline styles and a small `<style>` block
- No external JS frameworks in index.html — plain vanilla JS only
- Incident summaries: factual, no vendor marketing language
- Attacker field: always executive-readable (see naming rules above)
- Source attribution: show source domain/name under each victim name in smaller text
