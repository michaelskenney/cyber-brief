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
    """Truncate text to max_words, preserving whole words.

    The total word count of the returned string (including the '[truncated]'
    marker) will never exceed max_words.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    # Reserve one slot for the '[truncated]' marker so the total stays ≤ max_words
    return " ".join(words[: max_words - 1]) + " [truncated]"


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

    # Retry once on transient failures; skip date-range expansion if we retried
    retried = False
    if response.status_code in (429, 500, 502, 503, 504):
        time.sleep(2)
        response = requests.post(EXA_API_URL, headers=headers, json=body, timeout=30)
        retried = True

    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])

    # If fewer than 2 results (and we haven't already retried), expand to 14 days
    if len(results) < 2 and not retried:
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

    # Extract article content
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


def fetch_all(sources, date, api_key, output_dir):
    """Fetch articles from all sources, write output files, return summary."""
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
        for fail in summary["failures"]:
            print(f"  - {fail['source_id']}: {fail['error']}")

    min_required = len(sources) // 2
    if summary["succeeded"] < min_required:
        print(f"ERROR: Only {summary['succeeded']}/{len(sources)} sources succeeded (need {min_required}+)")
        sys.exit(1)


if __name__ == "__main__":
    main()
