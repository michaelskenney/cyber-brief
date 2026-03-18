# Cyber Threat Daily Brief

Automated cyber threat intelligence dashboard that refreshes every 12 hours.
No server required — runs entirely on GitHub Actions + GitHub Pages.

## How it works

```
GitHub Actions (cron: every 12 hours)
        │
        ▼
  generate_brief.py
        │  calls Anthropic API with web_search tool
        │  Claude searches 26 agreed sources
        │  returns structured JSON
        │
        ▼
  docs/data/brief.json   ←── committed back to repo
        │
        ▼
  GitHub Pages (docs/index.html)
        │  fetches brief.json on load + every 60s
        │  renders live table with filters
        ▼
  Your browser
```

## Setup (one-time, ~5 minutes)

### 1. Fork or clone this repository

```bash
git clone https://github.com/YOUR_ORG/cyber-brief.git
cd cyber-brief
```

### 2. Add your Anthropic API key as a GitHub secret

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your Anthropic API key (`sk-ant-...`)

### 3. Enable GitHub Pages

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / folder: `/docs`
4. Click **Save**

Your site will be live at: `https://YOUR_ORG.github.io/cyber-brief/`

### 4. Trigger the first run manually

1. Go to **Actions** → **Refresh Cyber Threat Brief**
2. Click **Run workflow** → **Run workflow**
3. Wait ~60–90 seconds for it to complete
4. Reload your GitHub Pages URL

After the first run, the workflow will trigger automatically at 06:00 and 18:00 UTC every day.

## Customising the refresh schedule

Edit `.github/workflows/refresh_brief.yml`:

```yaml
schedule:
  - cron: '0 6,18 * * *'   # 06:00 and 18:00 UTC — change as needed
```

Cron syntax: `minute hour day month weekday`
- Every 6 hours: `0 */6 * * *`
- Every 12 hours: `0 */12 * * *`
- Weekdays at 07:00 UTC only: `0 7 * * 1-5`

## Local development

```bash
# Install dependency
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run the generator
python generate_brief.py

# Serve the frontend locally
cd docs && python -m http.server 8080
# Open http://localhost:8080
```

## Files

```
cyber-brief/
├── .github/
│   └── workflows/
│       └── refresh_brief.yml   # Scheduled GitHub Action
├── docs/
│   ├── index.html              # Frontend (served by GitHub Pages)
│   └── data/
│       └── brief.json          # Generated data (auto-updated by Action)
├── generate_brief.py           # Generator script
└── README.md
```

## Agreed source list

The generator searches exclusively across these 26 sources:

**Industry / Threat Intelligence**
- crowdstrike.com/blog
- cloud.google.com/blog/topics/threat-intelligence (Mandiant)
- unit42.paloaltonetworks.com
- microsoft.com/en-us/security/blog
- blog.talosintelligence.com
- recordedfuture.com/research
- darkreading.com
- krebsonsecurity.com

**Government**
- cisa.gov/news-events/cybersecurity-advisories
- ic3.gov
- justice.gov/news
- home.treasury.gov/news (OFAC)
- fincen.gov/resources/advisories
- nsa.gov/Press-Room/Cybersecurity-Advisories-Guidance
- ncsc.gov.uk/news
- cyber.gov.au/about-us/news (ACSC)
- enisa.europa.eu/news

**News**
- reuters.com/technology/cybersecurity
- bloomberg.com/technology
- therecord.media

**Regulatory**
- efts.sec.gov (EDGAR 8-K Item 1.05)
- sec.gov/litigation
- dfs.ny.gov/enforcement

**Trusted voices**
- risky.biz
- isc.sans.edu
- cyberscoop.com
