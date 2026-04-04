"""scribe-newsletter-compose skill: Compose weekly newsletter from accumulated content.

Gathers the week's blog drafts, hero assets, social highlights, and lore drops
into a structured newsletter ready for email distribution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.scribe-newsletter-compose")


def run(
    config: dict[str, Any],
    supabase: Any,
    gemini_model: Any = None,
    pipeline_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose newsletter from week's content."""
    stats = pipeline_stats or {}
    blog_draft = stats.get("blog_draft", {})

    # Get recent hero images for newsletter
    hero_resp = (
        supabase.table("asset_metadata")
        .select("guardian, storage_url, quality_score")
        .eq("quality_tier", "hero")
        .order("created_at", desc=True)
        .limit(3)
        .execute()
    )
    heroes = hero_resp.data or []

    sections = {
        "hero_story": blog_draft.get("excerpt", "Another week of building in the Arcanea universe."),
        "shipped_this_week": f"{stats.get('commits_scanned', 0)} commits, {stats.get('drafts_created', 0)} content pieces",
        "featured_art": [
            {"guardian": h.get("guardian", ""), "url": h.get("storage_url", "")}
            for h in heroes
        ],
        "coming_next": "More updates soon.",
    }

    logger.info("Newsletter composed with %d sections", len(sections))
    return {"newsletter_composed": True, "sections": sections}
