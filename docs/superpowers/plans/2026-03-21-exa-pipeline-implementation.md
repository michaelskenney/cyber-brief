# Exa Pipeline Rearchitecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace monolithic Sonnet+web_search with a staged pipeline: Exa fetches raw content from approved sources, Claude Code analyzes it, publish script pushes to GitHub Pages. Roll out in phases starting with 3 sources.

**Architecture:** Three discrete scripts — `fetch.py` (Exa REST API), Claude Code via `analyze_prompt.md`, `publish.sh` (git push) — chained by `run_pipeline.sh`. Content saved locally in `data/raw/{date}/`, final `brief.json` pushed to GitHub Pages.

**Tech Stack:** Python 3.11, `requests`, `python-dotenv`, Exa REST API, Claude Code CLI, bash, launchd

**Spec:** `docs/superpowers/specs/2026-03-20-exa-pipeline-rearchitecture-design.md`

---

## Phased Rollout Strategy

| Phase | Sources | Goal |
|-------|---------|------|
| 1 | 3 (crowdstrike, cisa, therecord) | Build and validate full pipeline end-to-end |
| 2 | 10 | Add sources across all categories, validate at scale |
| 3 | 26 (all) | Full source list, schedule via launchd |

Phase 1 is fully detailed below. Phases 2 and 3 are expansion tasks at the end.

---

## Phase 1: Core Pipeline with 3 Sources

### Task 1: Project scaffolding and configuration

**Files:**
- Create: `sources.json`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `requirements.txt`

- [ ] **Step 1: Create `sources.json` with 3 pilot sources**

```json
[
  {
    "id": "crowdstrike",
    "domain": "crowdstrike.com/blog",
    "category": "Industry / Threat Intelligence"
  },
  {
    "id": "cisa",
    "domain": "cisa.gov/news-events/cybersecurity-advisories",
    "category": "Government"
  },
  {
    "id": "therecord",
    "domain": "therecord.media",
    "category": "News"
  }
]
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
data/raw/
data/logs/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Create `.env.example`**

```
EXA_API_KEY=your-exa-api-key-here
```

- [ ] **Step 4: Create `requirements.txt`**

```
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=7.0.0
```

- [ ] **Step 5: Create `.env` with real API key**

Copy `.env.example` to `.env` and add your actual Exa API key. This file is gitignored.

- [ ] **Step 6: Install dependencies**

Run: `pip install -r requirements.txt`

- [ ] **Step 7: Commit scaffolding**

```bash
git add sources.json .gitignore .env.example requirements.txt
git commit -m "feat: add project scaffolding for Exa pipeline"
```

---

### Task 2: `fetch.py` — Exa search for a single source

**Files:**
- Create: `fetch.py`
- Create: `tests/test_fetch.py`

- [ ] **Step 1: Write the failing test for single-source fetch**

Create `tests/__init__.py` (empty) and `tests/test_fetch.py`:

```python
"""Tests for fetch.py — Exa content retrieval."""
import json
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest
import requests


def make_exa_response(results):
    """Build a mock Exa /search response."""
    return {
        "requestId": "test-123",
        "results": results,
        "searchType": "auto",
        "costDollars": 0.001,
    }


def make_exa_result(title, url, text, published_date="2026-03-20T12:00:00Z"):
    """Build a single Exa search result."""
    return {
        "title": title,
        "url": url,
        "publishedDate": published_date,
        "text": text,
        "author": None,
        "id": "doc-abc",
    }


class TestFetchSingleSource:
    """Test fetching articles from a single source via Exa."""

    @patch("fetch.requests.post")
    def test_fetch_source_returns_articles(self, mock_post, tmp_path):
        from fetch import fetch_source

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = make_exa_response([
            make_exa_result(
                "New Threat Advisory",
                "https://crowdstrike.com/blog/advisory-1",
                "A new ransomware variant has been discovered targeting...",
            )
        ])
        mock_post.return_value = mock_response

        source = {"id": "crowdstrike", "domain": "crowdstrike.com/blog", "category": "Industry"}
        result = fetch_source(source, date="2026-03-20", api_key="test-key")

        assert result["source_id"] == "crowdstrike"
        assert result["article_count"] == 1
        assert result["articles"][0]["title"] == "New Threat Advisory"
        assert len(result["articles"][0]["content"]) > 0

        # Verify Exa API was called correctly
        call_args = mock_post.call_args
        body = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        assert "crowdstrike.com/blog" in body.get("includeDomains", [])

    @patch("fetch.requests.post")
    def test_fetch_source_caps_articles_at_5(self, mock_post, tmp_path):
        """Local safety cap — Exa's numResults already limits, but we cap locally too."""
        from fetch import fetch_source

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = make_exa_response([
            make_exa_result(f"Article {i}", f"https://example.com/{i}", f"Content {i}")
            for i in range(8)
        ])
        mock_post.return_value = mock_response

        source = {"id": "test", "domain": "example.com", "category": "Test"}
        result = fetch_source(source, date="2026-03-20", api_key="test-key")

        assert result["article_count"] <= 5

    @patch("fetch.requests.post")
    def test_fetch_source_expands_to_14_days_when_few_results(self, mock_post, tmp_path):
        """If <2 results from 48h search, re-search with 14-day window."""
        from fetch import fetch_source

        # First call: 1 result (< 2 threshold). Second call: 3 results.
        resp_few = MagicMock()
        resp_few.status_code = 200
        resp_few.json.return_value = make_exa_response([
            make_exa_result("Only one", "https://example.com/1", "Content")
        ])
        resp_many = MagicMock()
        resp_many.status_code = 200
        resp_many.json.return_value = make_exa_response([
            make_exa_result(f"Article {i}", f"https://example.com/{i}", f"Content {i}")
            for i in range(3)
        ])
        mock_post.side_effect = [resp_few, resp_many]

        source = {"id": "test", "domain": "example.com", "category": "Test"}
        result = fetch_source(source, date="2026-03-20", api_key="test-key")

        # Should have made 2 API calls
        assert mock_post.call_count == 2
        # Second call should have an earlier startPublishedDate (14 days back)
        second_call_body = mock_post.call_args_list[1][1]["json"]
        assert "startPublishedDate" in second_call_body
        # Should return the 3 results from the expanded search
        assert result["article_count"] == 3

    @patch("fetch.requests.post")
    def test_fetch_source_retries_on_transient_failure(self, mock_post, tmp_path):
        """429/5xx triggers a single retry after 2s backoff."""
        from fetch import fetch_source

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.raise_for_status.side_effect = requests.exceptions.HTTPError("429")
        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = make_exa_response([
            make_exa_result("After retry", "https://example.com/1", "Content")
        ])
        mock_post.side_effect = [resp_429, resp_ok]

        source = {"id": "test", "domain": "example.com", "category": "Test"}
        with patch("fetch.time.sleep"):  # skip the actual 2s wait
            result = fetch_source(source, date="2026-03-20", api_key="test-key")

        assert mock_post.call_count == 2
        assert result["article_count"] == 1

    @patch("fetch.requests.post")
    def test_fetch_source_truncates_long_articles(self, mock_post, tmp_path):
        from fetch import fetch_source, MAX_WORDS_PER_ARTICLE

        long_text = " ".join(["word"] * 3000)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = make_exa_response([
            make_exa_result("Long Article", "https://example.com/long", long_text)
        ])
        mock_post.return_value = mock_response

        source = {"id": "test", "domain": "example.com", "category": "Test"}
        result = fetch_source(source, date="2026-03-20", api_key="test-key")

        word_count = len(result["articles"][0]["content"].split())
        assert word_count <= MAX_WORDS_PER_ARTICLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/msk/cc/cyber && python -m pytest tests/test_fetch.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'fetch')

- [ ] **Step 3: Implement `fetch_source` in `fetch.py`**

```python
"""
fetch.py — Stage 1: Fetch raw content from approved sources via Exa REST API.

Usage:
    python fetch.py                    # fetch for today's date
    python fetch.py --date 2026-03-20  # fetch for a specific date
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

EXA_API_URL = "https://api.exa.ai/search"
MAX_ARTICLES_PER_SOURCE = 5
MAX_WORDS_PER_ARTICLE = 1500
MAX_TOTAL_WORDS = 120000


def truncate_text(text, max_words):
    """Truncate text to max_words, preserving whole words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " [truncated]"


def fetch_source(source, date, api_key):
    """Fetch articles from a single source via Exa /search endpoint.

    Args:
        source: dict with id, domain, category
        date: str YYYY-MM-DD
        api_key: Exa API key

    Returns:
        dict with source_id, domain, fetched_at, article_count, articles
    """
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    # Search last 48 hours first
    end_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_48h = (end_date - timedelta(hours=48)).isoformat()

    body = {
        "query": "cyber attack breach ransomware vulnerability advisory",
        "type": "auto",
        "numResults": MAX_ARTICLES_PER_SOURCE,
        "includeDomains": [source["domain"]],
        "startPublishedDate": start_48h,
        "contents": {"text": True},
    }

    response = requests.post(EXA_API_URL, headers=headers, json=body, timeout=30)

    # Retry once on transient failures
    if response.status_code in (429, 500, 502, 503, 504):
        time.sleep(2)
        response = requests.post(EXA_API_URL, headers=headers, json=body, timeout=30)

    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])

    # If fewer than 2 results, expand to 14 days
    if len(results) < 2:
        start_14d = (end_date - timedelta(days=14)).isoformat()
        body["startPublishedDate"] = start_14d
        response = requests.post(EXA_API_URL, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

    # If still no results after expanding date range, treat as failure
    if not results:
        raise ValueError(f"Exa returned 0 results for {source['domain']}")

    # Cap at MAX_ARTICLES_PER_SOURCE
    results = results[:MAX_ARTICLES_PER_SOURCE]

    # Extract article content — use /contents fallback if text is missing
    # (Exa /search with contents.text usually returns inline text, but
    # some pages may return empty text. A /contents fallback can be added
    # later if this proves to be a common issue in practice.)
    articles = []
    for r in results:
        text = r.get("text", "") or ""
        if not text.strip():
            continue  # skip results with no content
        articles.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "published_date": r.get("publishedDate", ""),
            "content": truncate_text(text, MAX_WORDS_PER_ARTICLE),
        })

    if not articles:
        raise ValueError(f"Exa returned results but no readable content for {source['domain']}")

    return {
        "source_id": source["id"],
        "domain": source["domain"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "articles": articles,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/msk/cc/cyber && python -m pytest tests/test_fetch.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add fetch.py tests/__init__.py tests/test_fetch.py
git commit -m "feat: add fetch_source function with Exa API integration"
```

---

### Task 3: `fetch.py` — Full pipeline with multi-source, summary, and CLI

**Files:**
- Modify: `fetch.py`
- Modify: `tests/test_fetch.py`

- [ ] **Step 1: Write failing tests for multi-source fetch and file output**

Add to `tests/test_fetch.py`:

```python
class TestFetchAll:
    """Test fetching from all sources and writing output files."""

    @patch("fetch.fetch_source")
    def test_fetch_all_writes_files(self, mock_fetch, tmp_path):
        from fetch import fetch_all

        mock_fetch.return_value = {
            "source_id": "crowdstrike",
            "domain": "crowdstrike.com/blog",
            "fetched_at": "2026-03-20T06:00:00+00:00",
            "article_count": 1,
            "articles": [{"title": "Test", "url": "https://x.com", "published_date": "", "content": "text"}],
        }

        sources = [
            {"id": "crowdstrike", "domain": "crowdstrike.com/blog", "category": "Industry"},
            {"id": "cisa", "domain": "cisa.gov", "category": "Government"},
        ]

        summary = fetch_all(sources, date="2026-03-20", api_key="test", output_dir=str(tmp_path))

        # Check source files were written
        assert (tmp_path / "crowdstrike.json").exists()
        assert (tmp_path / "cisa.json").exists()

        # Check summary
        assert summary["total_sources"] == 2
        assert summary["succeeded"] == 2
        assert (tmp_path / "_fetch_summary.json").exists()

    @patch("fetch.fetch_source")
    def test_fetch_all_handles_source_failure(self, mock_fetch, tmp_path):
        from fetch import fetch_all

        def side_effect(source, date, api_key):
            if source["id"] == "broken":
                raise Exception("Exa API error")
            return {
                "source_id": source["id"],
                "domain": source["domain"],
                "fetched_at": "2026-03-20T06:00:00+00:00",
                "article_count": 1,
                "articles": [{"title": "Test", "url": "https://x.com", "published_date": "", "content": "text"}],
            }

        mock_fetch.side_effect = side_effect

        sources = [
            {"id": "good", "domain": "good.com", "category": "Test"},
            {"id": "broken", "domain": "broken.com", "category": "Test"},
        ]

        summary = fetch_all(sources, date="2026-03-20", api_key="test", output_dir=str(tmp_path))

        assert summary["succeeded"] == 1
        assert summary["failed"] == 1
        assert len(summary["failures"]) == 1
        assert summary["failures"][0]["source_id"] == "broken"

    @patch("fetch.fetch_source")
    def test_fetch_all_enforces_total_word_budget(self, mock_fetch, tmp_path):
        from fetch import fetch_all, MAX_TOTAL_WORDS

        def side_effect(source, date, api_key):
            # Each source returns a huge article
            big_text = " ".join(["word"] * 50000)
            return {
                "source_id": source["id"],
                "domain": source["domain"],
                "fetched_at": "2026-03-20T06:00:00+00:00",
                "article_count": 1,
                "articles": [{"title": "Big", "url": "https://x.com", "published_date": "2026-03-20", "content": big_text}],
            }

        mock_fetch.side_effect = side_effect

        sources = [{"id": f"s{i}", "domain": f"s{i}.com", "category": "Test"} for i in range(5)]

        summary = fetch_all(sources, date="2026-03-20", api_key="test", output_dir=str(tmp_path))

        # Count total words across all written source files
        total_words = 0
        for f in tmp_path.glob("*.json"):
            if f.name == "_fetch_summary.json":
                continue
            data = json.loads(f.read_text())
            for article in data["articles"]:
                total_words += len(article["content"].split())

        assert total_words <= MAX_TOTAL_WORDS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/msk/cc/cyber && python -m pytest tests/test_fetch.py::TestFetchAll -v`
Expected: FAIL (ImportError: cannot import name 'fetch_all' from 'fetch')

- [ ] **Step 3: Implement `fetch_all` and CLI in `fetch.py`**

Add to the bottom of `fetch.py`:

```python
def fetch_all(sources, date, api_key, output_dir):
    """Fetch articles from all sources, write output files, return summary.

    Args:
        sources: list of source dicts
        date: str YYYY-MM-DD
        api_key: Exa API key
        output_dir: directory to write output files

    Returns:
        summary dict
    """
    os.makedirs(output_dir, exist_ok=True)

    results = []
    failures = []
    total_words = 0

    for source in sources:
        try:
            print(f"  Fetching {source['id']}...")
            result = fetch_source(source, date, api_key)

            # Enforce total word budget
            source_words = sum(len(a["content"].split()) for a in result["articles"])
            if total_words + source_words > MAX_TOTAL_WORDS:
                # Trim articles to fit budget
                remaining = MAX_TOTAL_WORDS - total_words
                trimmed_articles = []
                for article in result["articles"]:
                    article_words = len(article["content"].split())
                    if remaining <= 0:
                        break
                    if article_words > remaining:
                        article["content"] = truncate_text(article["content"], remaining)
                        article_words = remaining
                    trimmed_articles.append(article)
                    remaining -= article_words
                result["articles"] = trimmed_articles
                result["article_count"] = len(trimmed_articles)
                source_words = sum(len(a["content"].split()) for a in trimmed_articles)

            total_words += source_words

            # Write source file
            output_path = os.path.join(output_dir, f"{source['id']}.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            results.append(result)
            print(f"    {result['article_count']} articles, {source_words:,} words")

        except Exception as e:
            print(f"    FAILED: {e}")
            failures.append({"source_id": source["id"], "error": str(e)})

    total_articles = sum(r["article_count"] for r in results)

    summary = {
        "date": date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_sources": len(sources),
        "succeeded": len(results),
        "failed": len(failures),
        "total_articles": total_articles,
        "total_words": total_words,
        "failures": failures,
    }

    # Write summary
    summary_path = os.path.join(output_dir, "_fetch_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Fetch cyber threat content via Exa API")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        help="Date for this fetch run (YYYY-MM-DD, default: today UTC)")
    args = parser.parse_args()

    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        print("ERROR: EXA_API_KEY not set. Add it to .env or environment.", file=sys.stderr)
        sys.exit(1)

    # Load sources
    sources_path = os.path.join(os.path.dirname(__file__), "sources.json")
    with open(sources_path, "r") as f:
        sources = json.load(f)

    output_dir = os.path.join(os.path.dirname(__file__), "data", "raw", args.date)

    print(f"Fetching {len(sources)} sources for {args.date}...")
    summary = fetch_all(sources, args.date, api_key, output_dir)

    print(f"\nFetch complete: {summary['succeeded']}/{summary['total_sources']} sources, "
          f"{summary['total_articles']} articles, {summary['total_words']:,} words")

    if summary["failures"]:
        print("Failures:")
        for f in summary["failures"]:
            print(f"  - {f['source_id']}: {f['error']}")

    # Exit 1 if less than half succeeded
    min_required = len(sources) // 2
    if summary["succeeded"] < min_required:
        print(f"ERROR: Only {summary['succeeded']}/{len(sources)} sources succeeded (need {min_required}+)")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `cd /Users/msk/cc/cyber && python -m pytest tests/test_fetch.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add fetch.py tests/test_fetch.py
git commit -m "feat: add fetch_all with multi-source support, word budget, and CLI"
```

---

### Task 4: Live integration test with Exa

**Files:**
- No new files — manual validation

This task validates that the Exa API actually works with your key and the 3 pilot sources before building the rest of the pipeline.

- [ ] **Step 1: Run fetch.py against the 3 pilot sources**

Run: `cd /Users/msk/cc/cyber && python fetch.py`

Expected:
- Creates `data/raw/{today's date}/` directory
- Writes `crowdstrike.json`, `cisa.json`, `therecord.json`, and `_fetch_summary.json`
- At least 2 of 3 sources succeed
- Articles contain real content (not empty strings)

- [ ] **Step 2: Inspect the output**

Run: `cat data/raw/$(date -u '+%Y-%m-%d')/_fetch_summary.json | python -m json.tool`

Verify:
- `succeeded` >= 2
- `total_articles` > 0
- Article content looks like real cyber threat articles

- [ ] **Step 3: Spot-check a source file**

Run: `cat data/raw/$(date -u '+%Y-%m-%d')/therecord.json | python -m json.tool | head -30`

Verify:
- Articles have titles, URLs, and content
- Content is actual article text, not HTML or errors

- [ ] **Step 4: Note any issues**

If a source fails, check whether the domain in `sources.json` is correct for Exa's `includeDomains` filter. Exa uses domain matching — `crowdstrike.com/blog` may need to be just `crowdstrike.com`. Adjust `sources.json` if needed and re-run.

- [ ] **Step 5: Commit any source adjustments**

```bash
git add sources.json
git commit -m "fix: adjust source domains for Exa compatibility"
```

(Skip this step if no changes were needed.)

---

### Task 5: `analyze_prompt.md` — Claude Code analysis prompt

**Files:**
- Create: `analyze_prompt.md`

- [ ] **Step 1: Create `analyze_prompt.md`**

```markdown
Today is {{DATE}}.

Read the fetch summary and all source files in `data/raw/{{DATE}}/` to understand what content was retrieved.

Then analyze all articles for reportable cyber incidents. For each incident:

1. **Deduplicate** — if multiple sources cover the same incident, merge into one entry
2. **Apply attacker naming rules** — NEVER use vendor codenames (Fancy Bear, Lazarus Group, APT28, Volt Typhoon, etc.). ALWAYS use plain executive language:
   - "Russia — GRU military intelligence"
   - "Russia — FSB intelligence service"
   - "China — state-suspected espionage group"
   - "North Korea — state-sponsored, financially motivated"
   - "Criminal gang — ransomware"
   - "Unknown"
   (See CLAUDE.md for the full naming rules)
3. **Assign severity** — `critical`, `high`, `medium`, or `low`
4. **Assign motivation** — exactly one of: `Financial`, `Espionage`, `Disruption`, `IP theft`, `Political`, `Unclear`
5. **Assign attacker_origin** — exactly one of: `russia`, `iran`, `china`, `north_korea`, `criminal`, `unknown`
6. **Determine ongoing status** — `Y` or `N`

Write the result to `docs/data/brief.json` using this exact schema:

```json
{
  "generated_at": "ISO-8601 UTC timestamp",
  "period_searched": "Human-readable date range, e.g. March 19-21, 2026",
  "incident_count": 0,
  "incidents": [
    {
      "id": "1",
      "date": "Display date, e.g. Mar 20",
      "date_sort": "YYYY-MM-DD",
      "victim": "Organization or sector name",
      "industry": "Industry sector",
      "attacker": "Plain-language attacker description",
      "attacker_origin": "russia|iran|china|north_korea|criminal|unknown",
      "motivation": "Financial|Espionage|Disruption|IP theft|Political|Unclear",
      "vector": "How the attack was carried out — one concise sentence",
      "impact": "What happened — one to two concise sentences",
      "ongoing": "Y|N",
      "severity": "critical|high|medium|low",
      "sources": ["source domain or name"]
    }
  ]
}
```

Sort incidents by `date_sort` descending (most recent first). Set `incident_count` to the length of the incidents array. Set `generated_at` to the current UTC time.

After writing `brief.json`, append a single JSON line to `docs/data/usage_log.jsonl` with this format:

```json
{"timestamp": "ISO-8601", "date": "{{DATE}}", "pipeline": "exa+claude-code", "sources_fetched": N, "sources_failed": N, "total_articles": N, "incident_count": N, "model": "claude-opus-4-6"}
```

Read the `_fetch_summary.json` to get the sources_fetched, sources_failed, and total_articles values.
```

- [ ] **Step 2: Commit**

```bash
git add analyze_prompt.md
git commit -m "feat: add Claude Code analysis prompt for threat brief generation"
```

---

### Task 6: Test the analysis stage manually

**Files:**
- No new files — manual validation

This task validates that Claude Code produces valid `brief.json` from the raw content fetched in Task 4.

- [ ] **Step 1: Run Claude Code with the analysis prompt**

Run:
```bash
cd /Users/msk/cc/cyber
DATE=$(date -u '+%Y-%m-%d')
claude -p "$(sed "s/{{DATE}}/$DATE/g" analyze_prompt.md)" --allowedTools Read,Write,Edit,Glob
```

Expected: Claude Code reads the raw files, analyzes them, and writes `docs/data/brief.json`.

- [ ] **Step 2: Validate brief.json schema**

Run: `cat docs/data/brief.json | python -m json.tool`

Verify:
- Has `generated_at`, `period_searched`, `incident_count`, `incidents` fields
- Each incident has all required fields
- `attacker_origin` values are from the allowed set
- `motivation` values are from the allowed set
- `severity` values are from the allowed set
- No vendor codenames in `attacker` fields (no "Fancy Bear", "APT28", etc.)
- `date_sort` is in YYYY-MM-DD format
- Incidents are sorted by `date_sort` descending

- [ ] **Step 3: Validate usage_log.jsonl**

Run: `tail -1 docs/data/usage_log.jsonl | python -m json.tool`

Verify: Entry has `timestamp`, `date`, `pipeline`, `sources_fetched`, `incident_count` fields.

- [ ] **Step 4: Test the dashboard locally**

Run: `cd /Users/msk/cc/cyber/docs && python -m http.server 8080`

Open http://localhost:8080 in a browser. Verify:
- Table renders with incidents
- Severity filters work
- Attacker colors are correct
- "Last refreshed" timestamp is recent

- [ ] **Step 5: Note any prompt adjustments needed**

If `brief.json` output has issues (wrong format, vendor codenames, etc.), adjust `analyze_prompt.md` and re-run. Commit any changes:

```bash
git add analyze_prompt.md
git commit -m "fix: refine analysis prompt based on test output"
```

---

### Task 7: `publish.sh` and `run_pipeline.sh`

**Files:**
- Create: `publish.sh`
- Create: `run_pipeline.sh`

- [ ] **Step 1: Create `publish.sh`**

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

- [ ] **Step 2: Create `run_pipeline.sh`**

```bash
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

echo "=== Stage 3: Publish ==="
./publish.sh

echo "=== Cleanup: remove raw data older than 30 days ==="
find data/raw -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true

echo "=== Pipeline complete ==="
```

- [ ] **Step 3: Make scripts executable**

Run: `chmod +x publish.sh run_pipeline.sh`

- [ ] **Step 4: Test `publish.sh` with no changes**

Run: `./publish.sh`
Expected: "No changes to commit" (since we haven't changed brief.json since last push)

- [ ] **Step 5: Commit**

```bash
git add publish.sh run_pipeline.sh
git commit -m "feat: add publish.sh and run_pipeline.sh pipeline wrapper"
```

---

### Task 8: End-to-end pipeline test

**Files:**
- No new files — full pipeline validation

- [ ] **Step 1: Run the full pipeline**

Run: `cd /Users/msk/cc/cyber && ./run_pipeline.sh`

Expected output flow:
1. Stage 1: Fetches 3 sources, reports article counts
2. Stage 2: Claude Code analyzes and writes `brief.json`
3. Stage 3: Commits and pushes to GitHub

- [ ] **Step 2: Verify GitHub Pages updated**

Check your GitHub Pages URL. The dashboard should show fresh incidents.

- [ ] **Step 3: Verify usage_log.jsonl has the new entry**

Run: `tail -1 docs/data/usage_log.jsonl | python -m json.tool`

- [ ] **Step 4: Commit any fixes**

If any adjustments were needed during the e2e test, commit them now.

---

### Task 9: Demote GitHub Actions to manual-only fallback

Do this now to avoid race conditions between the cron schedule and local pipeline runs during Phase 2-3 testing.

**Files:**
- Modify: `.github/workflows/refresh_brief.yml`

- [ ] **Step 1: Remove cron schedule from workflow**

Edit `.github/workflows/refresh_brief.yml`: remove the `schedule` block, keeping only `workflow_dispatch`.

```yaml
name: Refresh Cyber Threat Brief

on:
  workflow_dispatch:
    # Manual trigger only — primary pipeline runs locally via launchd

jobs:
  generate:
    # ... rest unchanged
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/refresh_brief.yml
git commit -m "chore: demote GitHub Actions to manual-only fallback"
git push origin main
```

---

## Phase 2: Expand to 10 Sources

### Task 10: Add 7 more sources across categories

**Files:**
- Modify: `sources.json`

- [ ] **Step 1: Update `sources.json` to 10 sources**

Add sources from each category to validate breadth:

```json
[
  {"id": "crowdstrike", "domain": "crowdstrike.com/blog", "category": "Industry / Threat Intelligence"},
  {"id": "cisa", "domain": "cisa.gov/news-events/cybersecurity-advisories", "category": "Government"},
  {"id": "therecord", "domain": "therecord.media", "category": "News"},
  {"id": "unit42", "domain": "unit42.paloaltonetworks.com", "category": "Industry / Threat Intelligence"},
  {"id": "mstic", "domain": "microsoft.com/en-us/security/blog", "category": "Industry / Threat Intelligence"},
  {"id": "krebsonsecurity", "domain": "krebsonsecurity.com", "category": "Industry / Threat Intelligence"},
  {"id": "doj", "domain": "justice.gov/news", "category": "Government"},
  {"id": "ncsc", "domain": "ncsc.gov.uk/news", "category": "Government (Allied)"},
  {"id": "reuters", "domain": "reuters.com/technology/cybersecurity", "category": "News"},
  {"id": "cyberscoop", "domain": "cyberscoop.com", "category": "Trusted Voices"}
]
```

- [ ] **Step 2: Run fetch only**

Run: `python fetch.py`

Verify: At least 7 of 10 sources succeed. Check `_fetch_summary.json` for any domain issues.

- [ ] **Step 3: Fix any domain issues**

Some Exa `includeDomains` may need adjustment (e.g., subdomain vs full path). Fix and re-run.

- [ ] **Step 4: Run full pipeline**

Run: `./run_pipeline.sh`

Verify: Dashboard shows incidents from a wider range of sources.

- [ ] **Step 5: Commit**

```bash
git add sources.json
git commit -m "feat: expand to 10 sources across all categories"
```

---

## Phase 3: Full Source List and Scheduling

### Task 11: Expand to all 26 sources

**Files:**
- Modify: `sources.json`

- [ ] **Step 1: Update `sources.json` with all 26 sources**

Add the remaining 16 sources:

```json
[
  {"id": "crowdstrike", "domain": "crowdstrike.com/blog", "category": "Industry / Threat Intelligence"},
  {"id": "mandiant", "domain": "cloud.google.com/blog/topics/threat-intelligence", "category": "Industry / Threat Intelligence"},
  {"id": "unit42", "domain": "unit42.paloaltonetworks.com", "category": "Industry / Threat Intelligence"},
  {"id": "mstic", "domain": "microsoft.com/en-us/security/blog", "category": "Industry / Threat Intelligence"},
  {"id": "talos", "domain": "blog.talosintelligence.com", "category": "Industry / Threat Intelligence"},
  {"id": "recordedfuture", "domain": "recordedfuture.com/research", "category": "Industry / Threat Intelligence"},
  {"id": "darkreading", "domain": "darkreading.com", "category": "Industry / Threat Intelligence"},
  {"id": "krebsonsecurity", "domain": "krebsonsecurity.com", "category": "Industry / Threat Intelligence"},
  {"id": "cisa", "domain": "cisa.gov/news-events/cybersecurity-advisories", "category": "Government"},
  {"id": "ic3", "domain": "ic3.gov", "category": "Government"},
  {"id": "doj", "domain": "justice.gov/news", "category": "Government"},
  {"id": "treasury", "domain": "home.treasury.gov/news", "category": "Government"},
  {"id": "fincen", "domain": "fincen.gov/resources/advisories", "category": "Government"},
  {"id": "nsa", "domain": "nsa.gov/Press-Room/Cybersecurity-Advisories-Guidance", "category": "Government"},
  {"id": "ncsc", "domain": "ncsc.gov.uk/news", "category": "Government (Allied)"},
  {"id": "acsc", "domain": "cyber.gov.au/about-us/news", "category": "Government (Allied)"},
  {"id": "enisa", "domain": "enisa.europa.eu/news", "category": "Government (Allied)"},
  {"id": "reuters", "domain": "reuters.com/technology/cybersecurity", "category": "News"},
  {"id": "bloomberg", "domain": "bloomberg.com/technology", "category": "News"},
  {"id": "therecord", "domain": "therecord.media", "category": "News"},
  {"id": "sec_edgar", "domain": "efts.sec.gov", "category": "Regulatory"},
  {"id": "sec_litigation", "domain": "sec.gov/litigation", "category": "Regulatory"},
  {"id": "nydfs", "domain": "dfs.ny.gov/enforcement", "category": "Regulatory"},
  {"id": "riskybiz", "domain": "risky.biz", "category": "Trusted Voices"},
  {"id": "sans", "domain": "isc.sans.edu", "category": "Trusted Voices"},
  {"id": "cyberscoop", "domain": "cyberscoop.com", "category": "Trusted Voices"}
]
```

- [ ] **Step 2: Run fetch and review**

Run: `python fetch.py`

Review `_fetch_summary.json`. Expect some government/regulatory sources to return 0 results (they publish less frequently). That's fine — the pipeline handles it.

- [ ] **Step 3: Run full pipeline**

Run: `./run_pipeline.sh`

Verify dashboard shows comprehensive coverage.

- [ ] **Step 4: Commit**

```bash
git add sources.json
git commit -m "feat: expand to full 26-source approved list"
```

---

### Task 12: Set up launchd scheduling

**Files:**
- Create: `com.cyberbrief.refresh.plist`

- [ ] **Step 1: Find full paths for python3 and claude**

Run:
```bash
which python3
which claude
```

Note these paths — they go in the plist.

- [ ] **Step 2: Create the launchd plist**

Create `com.cyberbrief.refresh.plist` (replace paths with your actual `which` output):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cyberbrief.refresh</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/msk/cc/cyber/run_pipeline.sh</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>

    <key>StartInterval</key>
    <integer>43200</integer>

    <key>StandardOutPath</key>
    <string>/Users/msk/cc/cyber/data/logs/launchd-stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/msk/cc/cyber/data/logs/launchd-stderr.log</string>

    <key>WorkingDirectory</key>
    <string>/Users/msk/cc/cyber</string>
</dict>
</plist>
```

- [ ] **Step 3: Install and load the plist**

```bash
mkdir -p ~/Library/LaunchAgents
cp com.cyberbrief.refresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cyberbrief.refresh.plist
```

- [ ] **Step 4: Verify it's loaded**

Run: `launchctl list | grep cyberbrief`
Expected: Shows `com.cyberbrief.refresh` in the list

- [ ] **Step 5: Wait for first scheduled run or test manually**

To trigger immediately: `launchctl start com.cyberbrief.refresh`

Check logs: `cat data/logs/launchd-stdout.log`

- [ ] **Step 6: Commit**

```bash
git add com.cyberbrief.refresh.plist
git commit -m "feat: add launchd plist for 12-hour scheduled pipeline runs"
```

---

### Task 13: Final push and verification

- [ ] **Step 1: Push all commits**

```bash
git push origin main
```

- [ ] **Step 2: Verify GitHub Pages dashboard**

Check your live URL — dashboard should reflect the latest full-source run.

- [ ] **Step 3: Verify launchd is scheduled**

Run: `launchctl list | grep cyberbrief`

The pipeline will now run automatically every 12 hours from your Mac.
