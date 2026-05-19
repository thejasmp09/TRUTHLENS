"""
Web search and fact-check lookup.
Uses DuckDuckGo (free, no API key) and Google Fact Check API (free).
"""

import logging

import requests
from ddgs import DDGS

logger = logging.getLogger(__name__)

# — DuckDuckGo search —

def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web via DuckDuckGo.
    Returns list of {"title", "url", "snippet"}.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
    except Exception:
        logger.exception("DuckDuckGo search failed for: %s", query)
        return []


def time_filtered_search(query: str, max_results: int = 5) -> list[dict]:
    """Search DuckDuckGo sorted by date (oldest first) to find origin."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, timelimit="m"))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
    except Exception:
        logger.exception("DuckDuckGo time-filtered search failed for: %s", query)
        return []


# — Google Fact Check API (free, no key required for ClaimSearch) —

FACT_CHECK_API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
# Set to False after the first 403/error so we stop hammering a dead endpoint
_fact_check_available: bool = True


def fact_check_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the Google Fact Check Tools API for existing fact-checks.
    Returns list of {"claim", "claimant", "rating", "url", "publisher"}.
    """
    global _fact_check_available
    if not _fact_check_available:
        return []
    try:
        resp = requests.get(
            FACT_CHECK_API,
            params={"query": query, "pageSize": max_results},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Fact Check API returned %d - disabling for this run", resp.status_code)
            _fact_check_available = False
            return []

        data = resp.json()
        results = []
        for claim in data.get("claims", []):
            for review in claim.get("claimReview", []):
                results.append(
                    {
                        "claim": claim.get("text", ""),
                        "claimant": claim.get("claimant", "Unknown"),
                        "rating": review.get("textualRating", "Unknown"),
                        "url": review.get("url", ""),
                        "publisher": review.get("publisher", {}).get("name", "Unknown"),
                    }
                )
        return results[:max_results]
    except Exception:
        logger.exception("Fact Check API search failed for: %s - disabling for this run", query) 
        _fact_check_available = False
        return []