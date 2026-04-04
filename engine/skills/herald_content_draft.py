"""herald-content-draft skill: AI-generate social media content drafts.

Takes trend signals and hero assets, generates platform-specific content
drafts using Gemini with the FrankX brand voice.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.herald-content-draft")

DRAFT_PROMPT = """You are a social media strategist for Arcanea — an AI-powered creative universe.

{voice_guidelines}

Generate a {platform} post about: {topic}

Context: {context}

Requirements for {platform}:
- Twitter/X: Max 280 chars, punchy, 2-3 hashtags, NO thread — single tweet
- LinkedIn: Professional, 150-300 words, thought leadership, minimal hashtags
- Discord: Community-oriented, friendly, include call-to-action
- Farcaster: Crypto-native, concise, technical but accessible

Respond ONLY as JSON:
{{"content": "the post text", "hashtags": ["tag1"], "cta": "call to action or empty", "suggested_image": "description of image to pair or empty"}}"""


def run(config: dict[str, Any], supabase: Any, gemini_model: Any = None) -> dict[str, Any]:
    """Generate content drafts from trend signals and scheduled topics."""
    content_cfg = config.get("content", {})
    voice = content_cfg.get("voice_guidelines", "")
    platforms = config.get("platforms", {})
    templates = content_cfg.get("thread_templates", [])

    if gemini_model is None:
        logger.warning("Gemini not available — skipping content generation")
        return {"drafts_created": 0}

    # Get recent high-engagement signals
    resp = (
        supabase.table("campaign_signals")
        .select("id, platform, content, query, signal_type, engagement_score")
        .eq("status", "new")
        .order("engagement_score", desc=True)
        .limit(10)
        .execute()
    )
    signals = resp.data or []

    # Also get hero assets for visual content
    hero_resp = (
        supabase.table("asset_metadata")
        .select("id, guardian, element, storage_url, quality_score")
        .eq("quality_tier", "hero")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    heroes = hero_resp.data or []

    drafts_created = 0
    active_platforms = [p for p, cfg in platforms.items() if cfg.get("enabled")]

    # Generate drafts for top signals
    for signal in signals[:5]:
        for platform in active_platforms:
            prompt = DRAFT_PROMPT.format(
                voice_guidelines=voice,
                platform=platform,
                topic=signal.get("query", "Arcanea update"),
                context=signal.get("content", "")[:500],
            )

            try:
                response = gemini_model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    text = "\n".join(lines).strip()

                draft_data = json.loads(text)

                draft = {
                    "platform": platform,
                    "content_text": draft_data.get("content", ""),
                    "hashtags": draft_data.get("hashtags", []),
                    "signal_id": signal.get("id"),
                    "status": "draft",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                # Attach hero image if available
                if heroes:
                    hero = heroes[drafts_created % len(heroes)]
                    draft["media_urls"] = [hero.get("storage_url", "")]

                supabase.table("social_queue").insert(draft).execute()
                drafts_created += 1
            except Exception as exc:
                logger.warning("Draft generation failed for %s/%s: %s", platform, signal.get("query"), exc)

        # Mark signal as processed
        try:
            supabase.table("campaign_signals").update({"status": "processed"}).eq("id", signal["id"]).execute()
        except Exception:
            pass

    logger.info("Created %d content drafts", drafts_created)
    return {"drafts_created": drafts_created}
