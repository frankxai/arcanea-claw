"""social-prep skill: Generate social media queue entries for hero-tier artwork.

Creates draft entries for Instagram, LinkedIn, X, and YouTube with
platform-appropriate variants and AI-generated captions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("arcanea-claw.social-prep")

PLATFORMS: dict[str, dict[str, str]] = {
    "instagram": {
        "variant": "social_square",
        "aspect": "1:1",
    },
    "linkedin": {
        "variant": "social_wide",
        "aspect": "1.91:1",
    },
    "x": {
        "variant": "hero",
        "aspect": "16:9",
    },
    "youtube": {
        "variant": "hero",
        "aspect": "16:9",
    },
}

CAPTION_PROMPT_TEMPLATE = """Write a social media caption for this Arcanea artwork.

Guardian: {guardian}
Element: {element}
Gate: {gate}
Platform: {platform}
Content type: {content_type}

Guidelines:
- For Instagram: mystical, evocative, include 8-12 hashtags (#Arcanea #FantasyArt #{guardian} #{element} etc.)
- For LinkedIn: professional, highlight the creative process and AI-art innovation
- For X: concise and impactful, max 280 chars, 2-3 hashtags
- For YouTube: descriptive, SEO-friendly thumbnail description

Keep it mystical but accessible. Never use slop words (unleash, unlock, harness, journey).

Respond ONLY as JSON:
{{"caption": "The caption text", "hashtags": ["tag1", "tag2"]}}"""


def _parse_response(text: str) -> dict[str, Any] | None:
    """Extract JSON from Gemini response."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse caption response: %s", exc)
        return None


def _generate_caption(
    gemini_model: Any,
    guardian: str,
    element: str,
    gate: str,
    content_type: str,
    platform: str,
) -> dict[str, Any] | None:
    """Generate a platform-specific caption using Gemini."""
    prompt = CAPTION_PROMPT_TEMPLATE.format(
        guardian=guardian,
        element=element,
        gate=gate or "Unknown",
        content_type=content_type or "artwork",
        platform=platform,
    )
    try:
        response = gemini_model.generate_content(prompt)
        return _parse_response(response.text)
    except Exception as exc:
        logger.warning("Caption generation failed for %s/%s: %s", platform, guardian, exc)
        return None


def run(
    config: dict[str, Any],
    supabase: Any,
    gemini_model: Any = None,
) -> dict[str, Any]:
    """Create social media queue entries for hero-tier assets.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.
        gemini_model: Initialized Gemini GenerativeModel instance.

    Returns:
        Dict with ``posts_queued``.
    """
    # Fetch hero-tier scored assets that haven't been social-prepped yet
    resp = (
        supabase.table("asset_metadata")
        .select("id, file_path, guardian, element, gate, content_type, metadata, storage_url")
        .eq("quality_tier", "hero")
        .in_("status", ["scored", "uploaded"])
        .limit(20)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No hero-tier assets for social prep")
        return {"posts_queued": 0}

    posts_queued = 0

    for asset in assets:
        asset_id = asset["id"]
        guardian = asset.get("guardian", "Arcanea")
        element = asset.get("element", "")
        gate = asset.get("gate", "")
        content_type = asset.get("content_type", "artwork")
        variant_paths = (asset.get("metadata") or {}).get("variant_paths", {})
        storage_url = asset.get("storage_url", "")

        for platform, platform_cfg in PLATFORMS.items():
            variant_key = platform_cfg["variant"]
            image_path = variant_paths.get(variant_key, variant_paths.get("base", asset["file_path"]))

            # Generate caption
            caption_data: dict[str, Any] = {}
            if gemini_model is not None:
                result = _generate_caption(
                    gemini_model, guardian, element, gate, content_type, platform
                )
                if result:
                    caption_data = result

            queue_entry = {
                "asset_id": asset_id,
                "platform": platform,
                "image_path": image_path,
                "storage_url": storage_url,
                "caption": caption_data.get("caption", f"{guardian} — {element} Guardian of Arcanea"),
                "hashtags": caption_data.get("hashtags", ["Arcanea", "FantasyArt", guardian]),
                "aspect_ratio": platform_cfg["aspect"],
                "guardian": guardian,
                "element": element,
                "status": "draft",
            }

            try:
                supabase.table("social_queue").insert(queue_entry).execute()
                posts_queued += 1
            except Exception as exc:
                logger.warning(
                    "Failed to queue %s post for asset %s: %s",
                    platform, asset_id, exc,
                )

    logger.info("Queued %d social posts", posts_queued)
    return {"posts_queued": posts_queued}
