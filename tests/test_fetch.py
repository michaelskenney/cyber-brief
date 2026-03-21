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
