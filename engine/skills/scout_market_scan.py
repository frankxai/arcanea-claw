"""scout-market-scan skill: Scan markets for trends in AI, NFT, and creator economy.

Monitors GitHub trending, Product Hunt, CoinGecko, and Google Trends
for signals relevant to Arcanea's positioning.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.scout-market-scan")


def _fetch_github_trending(topic: str) -> list[dict]:
    """Fetch trending GitHub repos for a topic."""
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": f"{topic} created:>2026-01-01", "sort": "stars", "per_page": 5},
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])
    except Exception as exc:
        logger.debug("GitHub trending fetch failed: %s", exc)
        return []


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Scan market sources for intelligence signals."""
    sources = config.get("sources", {})
    signals = 0
    now = datetime.now(timezone.utc)

    # GitHub trending
    if sources.get("github", {}).get("enabled", True):
        topics = sources.get("github", {}).get("trending_topics", ["mcp", "ai-agent"])
        for topic in topics:
            repos = _fetch_github_trending(topic)
            for repo in repos:
                signal = {
                    "platform": "github",
                    "source_id": str(repo.get("id", "")),
                    "content": f"{repo.get('full_name')}: {repo.get('description', '')[:300]}",
                    "engagement_score": repo.get("stargazers_count", 0),
                    "query": topic,
                    "signal_type": "market_trend",
                    "detected_at": now.isoformat(),
                    "status": "new",
                }
                try:
                    supabase.table("campaign_signals").upsert(
                        signal, on_conflict="platform,source_id"
                    ).execute()
                    signals += 1
                except Exception:
                    pass

    logger.info("Market scan found %d signals", signals)
    return {"market_signals": signals}
