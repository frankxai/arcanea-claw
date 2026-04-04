"""herald-cross-post skill: Publish scheduled content to social platforms.

Picks up scheduled posts whose time has arrived and publishes them via
platform APIs. Updates status to 'published' with the post URL.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.herald-cross-post")


def _post_to_discord(webhook_url: str, content: str, image_url: str | None = None) -> str | None:
    """Post to Discord via webhook. Returns message ID."""
    payload: dict[str, Any] = {"content": content}
    if image_url:
        payload["embeds"] = [{"image": {"url": image_url}}]

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get("id", "posted")
    except Exception as exc:
        logger.warning("Discord post failed: %s", exc)
        return None


def _post_to_twitter(content: str, bearer_token: str) -> str | None:
    """Post to Twitter/X via API v2. Returns tweet ID."""
    if not bearer_token:
        return None

    try:
        resp = requests.post(
            "https://api.twitter.com/2/tweets",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            },
            json={"text": content},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("id")
    except Exception as exc:
        logger.warning("Twitter post failed: %s", exc)
        return None


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Publish scheduled content that's due."""
    platforms = config.get("platforms", {})
    now = datetime.now(timezone.utc)

    resp = (
        supabase.table("social_queue")
        .select("id, platform, content_text, media_urls, hashtags, scheduled_at")
        .eq("status", "scheduled")
        .lte("scheduled_at", now.isoformat())
        .limit(20)
        .execute()
    )
    items = resp.data or []

    if not items:
        logger.info("No scheduled posts due for publishing")
        return {"published_count": 0}

    published = 0

    for item in items:
        item_id = item["id"]
        platform = item["platform"]
        content = item.get("content_text", "")
        media_urls = item.get("media_urls", [])
        hashtags = item.get("hashtags", [])

        # Append hashtags
        if hashtags:
            tag_str = " ".join(f"#{t}" for t in hashtags[:5])
            if len(content) + len(tag_str) + 1 <= 280 or platform != "twitter":
                content = f"{content}\n\n{tag_str}"

        post_id = None
        post_url = None

        if platform == "discord":
            webhook = os.environ.get("DISCORD_ANNOUNCE_WEBHOOK", "")
            if webhook:
                post_id = _post_to_discord(webhook, content, media_urls[0] if media_urls else None)
                post_url = f"discord://posted/{post_id}" if post_id else None

        elif platform == "twitter":
            bearer = os.environ.get("TWITTER_BEARER_TOKEN", "")
            post_id = _post_to_twitter(content, bearer)
            post_url = f"https://twitter.com/i/web/status/{post_id}" if post_id else None

        elif platform == "linkedin":
            # LinkedIn requires OAuth2 — log for manual posting
            logger.info("LinkedIn post ready (manual): %s", content[:100])
            post_id = "manual_pending"

        if post_id:
            try:
                supabase.table("social_queue").update({
                    "status": "published",
                    "published_at": now.isoformat(),
                    "published_url": post_url or "",
                }).eq("id", item_id).execute()
                published += 1
            except Exception as exc:
                logger.warning("Failed to update post %s: %s", item_id, exc)
        else:
            try:
                supabase.table("social_queue").update({
                    "status": "failed",
                    "error_message": f"Publishing to {platform} failed",
                }).eq("id", item_id).execute()
            except Exception:
                pass

    logger.info("Published %d posts", published)
    return {"published_count": published}
