"""herald-trend-scan skill: Monitor social platforms for relevant conversations and trends.

Scans Twitter/X, Reddit, and Discord for mentions, keywords, and trending topics
relevant to Arcanea. Stores signals in campaign_signals table.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.herald-trend-scan")


def _search_twitter(query: str, bearer_token: str, max_results: int = 20) -> list[dict]:
    """Search recent tweets via Twitter API v2."""
    if not bearer_token:
        return []

    url = "https://api.twitter.com/2/tweets/search/recent"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {bearer_token}"},
            params={
                "query": f"{query} -is:retweet lang:en",
                "max_results": min(max_results, 100),
                "tweet.fields": "created_at,public_metrics,author_id",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as exc:
        logger.warning("Twitter search failed for '%s': %s", query, exc)
        return []


def _search_reddit(subreddit: str, query: str, limit: int = 10) -> list[dict]:
    """Search Reddit posts via JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    try:
        resp = requests.get(
            url,
            params={"q": query, "sort": "new", "limit": limit, "t": "day"},
            headers={"User-Agent": "ArcaneaClaw/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("children", [])
        return [p.get("data", {}) for p in posts]
    except Exception as exc:
        logger.warning("Reddit search failed for r/%s: %s", subreddit, exc)
        return []


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Scan social platforms for trends and mentions."""
    platforms = config.get("platforms", {})
    signals_found = 0

    # Twitter/X scan
    twitter_cfg = platforms.get("twitter", {})
    if twitter_cfg.get("enabled"):
        bearer = os.environ.get("TWITTER_BEARER_TOKEN", "")
        queries = ["arcanea", "AI world building", "creator economy AI", "AI fantasy universe"]

        for query in queries:
            tweets = _search_twitter(query, bearer, max_results=10)
            for tweet in tweets:
                metrics = tweet.get("public_metrics", {})
                engagement = (
                    metrics.get("like_count", 0) +
                    metrics.get("retweet_count", 0) * 3 +
                    metrics.get("reply_count", 0) * 2
                )

                signal = {
                    "platform": "twitter",
                    "source_id": tweet.get("id", ""),
                    "content": tweet.get("text", "")[:500],
                    "engagement_score": engagement,
                    "query": query,
                    "signal_type": "mention" if "arcanea" in query.lower() else "trend",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "status": "new",
                }

                try:
                    supabase.table("campaign_signals").upsert(
                        signal, on_conflict="platform,source_id"
                    ).execute()
                    signals_found += 1
                except Exception as exc:
                    logger.debug("Signal insert failed: %s", exc)

    # Reddit scan
    reddit_subreddits = ["aiArt", "worldbuilding", "CreatorEconomy"]
    for sub in reddit_subreddits:
        posts = _search_reddit(sub, "AI art OR world building OR creator", limit=5)
        for post in posts:
            signal = {
                "platform": "reddit",
                "source_id": post.get("id", ""),
                "content": f"{post.get('title', '')} | {post.get('selftext', '')[:300]}",
                "engagement_score": post.get("score", 0),
                "query": f"r/{sub}",
                "signal_type": "trend",
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "status": "new",
            }

            try:
                supabase.table("campaign_signals").upsert(
                    signal, on_conflict="platform,source_id"
                ).execute()
                signals_found += 1
            except Exception as exc:
                logger.debug("Signal insert failed: %s", exc)

    logger.info("Found %d social signals", signals_found)
    return {"signals_found": signals_found}
