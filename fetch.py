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
