"""taste-score skill: Score processed media on 5 aesthetic dimensions via Gemini Vision.

Evaluates Canon Alignment, Design Compliance, Emotional Impact, Technical Fit,
and Uniqueness (each 0-20) for a total 0-100 score, then assigns quality tiers.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("arcanea-claw.taste-score")

SCORE_PROMPT = """Score this image for the Arcanea fantasy universe on 5 dimensions (each 0-20):

1. Canon Alignment — Does it match Arcanea's aesthetic? Fantasy, mythological, elemental themes?
2. Design Compliance — Composition, color palette, professional quality?
3. Emotional Impact — Does it evoke wonder, power, mystery?
4. Technical Fit — Resolution, clarity, suitable for web hero/gallery use?
5. Uniqueness — Distinct from typical AI art? Has character and originality?

Respond ONLY as JSON:
{"canon_alignment": 0, "design_compliance": 0, "emotional_impact": 0, "technical_fit": 0, "uniqueness": 0, "total": 0, "tier": "hero|gallery|thumbnail|reject"}"""

BATCH_SIZE = 15

TIER_THRESHOLDS = {
    "hero": 80,
    "gallery": 60,
    "thumbnail": 40,
}


def _compute_tier(total: int) -> str:
    """Map a total score (0-100) to a quality tier string."""
    if total >= TIER_THRESHOLDS["hero"]:
        return "hero"
    if total >= TIER_THRESHOLDS["gallery"]:
        return "gallery"
    if total >= TIER_THRESHOLDS["thumbnail"]:
        return "thumbnail"
    return "reject"


def _encode_image(filepath: str) -> str | None:
    """Read and base64-encode an image file."""
    try:
        return base64.b64encode(Path(filepath).read_bytes()).decode("utf-8")
    except OSError as exc:
        logger.warning("Cannot read image %s: %s", filepath, exc)
        return None


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
        logger.warning("Failed to parse scoring response: %s", exc)
        return None


def run(config: dict[str, Any], supabase: Any, gemini_model: Any = None) -> dict[str, Any]:
    """Score processed assets using Gemini Vision.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.
        gemini_model: Initialized Gemini GenerativeModel instance.

    Returns:
        Dict with ``scored_count`` and ``hero_count``.
    """
    if gemini_model is None:
        logger.error("Gemini model not provided — skipping scoring")
        return {"scored_count": 0, "hero_count": 0}

    resp = (
        supabase.table("asset_metadata")
        .select("id, file_path, mime_type, metadata")
        .eq("status", "processed")
        .eq("quality_score", 0)
        .limit(BATCH_SIZE)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No assets to score")
        return {"scored_count": 0, "hero_count": 0}

    scored = 0
    hero_count = 0

    for asset in assets:
        asset_id = asset["id"]
        mime = asset.get("mime_type", "image/png")

        # Prefer the base processed variant if available
        variant_paths = (asset.get("metadata") or {}).get("variant_paths", {})
        filepath = variant_paths.get("base", asset["file_path"])

        encoded = _encode_image(filepath)
        if encoded is None:
            continue

        try:
            response = gemini_model.generate_content([
                SCORE_PROMPT,
                {"mime_type": mime, "data": encoded},
            ])
            result = _parse_response(response.text)
        except Exception as exc:
            logger.warning("Gemini scoring failed for asset %s: %s", asset_id, exc)
            continue

        if result is None:
            continue

        # Calculate and validate total
        dimensions = [
            result.get("canon_alignment", 0),
            result.get("design_compliance", 0),
            result.get("emotional_impact", 0),
            result.get("technical_fit", 0),
            result.get("uniqueness", 0),
        ]
        total = sum(int(d) for d in dimensions)
        total = max(0, min(100, total))  # clamp to 0-100
        tier = _compute_tier(total)

        # Merge scoring details into existing metadata
        existing_meta = asset.get("metadata") or {}
        existing_meta["taste_scores"] = {
            "canon_alignment": result.get("canon_alignment", 0),
            "design_compliance": result.get("design_compliance", 0),
            "emotional_impact": result.get("emotional_impact", 0),
            "technical_fit": result.get("technical_fit", 0),
            "uniqueness": result.get("uniqueness", 0),
        }

        try:
            supabase.table("asset_metadata").update({
                "quality_score": total,
                "quality_tier": tier,
                "status": "scored",
                "metadata": existing_meta,
            }).eq("id", asset_id).execute()
            scored += 1
            if tier == "hero":
                hero_count += 1
            logger.debug("Scored %s: %d (%s)", filepath, total, tier)
        except Exception as exc:
            logger.warning("Failed to update score for %s: %s", asset_id, exc)

    logger.info("Scored %d assets (%d hero-tier)", scored, hero_count)
    return {"scored_count": scored, "hero_count": hero_count}
