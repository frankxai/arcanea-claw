"""media-classify skill: Classify untagged media against Arcanea canon via Gemini Vision.

Queries assets with status='new' or missing guardian, sends each to Gemini
Vision for Guardian/Element/Gate classification, and updates the row.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("arcanea-claw.media-classify")

CLASSIFY_PROMPT = """Classify this image for the Arcanea fantasy universe.
Identify which Guardian this image best represents:
- Lyssandria (Earth, Foundation Gate, 174 Hz)
- Leyla (Water, Flow Gate, 285 Hz)
- Draconia (Fire, Fire Gate, 396 Hz)
- Maylinn (Air, Heart Gate, 417 Hz)
- Alera (Sound, Voice Gate, 528 Hz)
- Lyria (Void, Sight Gate, 639 Hz)
- Aiyami (Void, Crown Gate, 741 Hz)
- Elara (Fire, Starweave Gate, 852 Hz)
- Ino (Water, Unity Gate, 963 Hz)
- Shinkami (Void, Source Gate, 1111 Hz)

Also identify the Element (Earth, Water, Fire, Wind, Void) and suggest tags.

Respond ONLY as JSON:
{"guardian": "Name", "element": "Element", "gate": "GateName", "tags": ["tag1", "tag2"], "content_type": "character|landscape|artifact|scene|abstract", "confidence": 0.85}"""

BATCH_SIZE = 20


def _encode_image(filepath: str) -> str | None:
    """Read and base64-encode an image file."""
    try:
        data = Path(filepath).read_bytes()
        return base64.b64encode(data).decode("utf-8")
    except OSError as exc:
        logger.warning("Cannot read image %s: %s", filepath, exc)
        return None


def _parse_gemini_response(text: str) -> dict[str, Any] | None:
    """Extract JSON from Gemini response, handling markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip markdown code fences
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse Gemini response as JSON: %s", exc)
        return None


def run(config: dict[str, Any], supabase: Any, gemini_model: Any = None) -> dict[str, Any]:
    """Classify untagged assets using Gemini Vision.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.
        gemini_model: Initialized ``google.generativeai.GenerativeModel`` instance.

    Returns:
        Dict with ``classified_count``.
    """
    if gemini_model is None:
        logger.error("Gemini model not provided — skipping classification")
        return {"classified_count": 0}

    # Fetch unclassified assets
    resp = (
        supabase.table("asset_metadata")
        .select("id, file_path, mime_type")
        .or_("status.eq.new,guardian.is.null")
        .limit(BATCH_SIZE)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No assets to classify")
        return {"classified_count": 0}

    classified = 0

    for asset in assets:
        asset_id = asset["id"]
        filepath = asset["file_path"]
        mime = asset.get("mime_type", "image/png")

        # Only classify images
        if not mime or not mime.startswith("image/"):
            logger.debug("Skipping non-image asset %s (%s)", asset_id, mime)
            continue

        encoded = _encode_image(filepath)
        if encoded is None:
            continue

        try:
            response = gemini_model.generate_content([
                CLASSIFY_PROMPT,
                {"mime_type": mime, "data": encoded},
            ])
            result = _parse_gemini_response(response.text)
        except Exception as exc:
            logger.warning("Gemini call failed for asset %s: %s", asset_id, exc)
            continue

        if result is None:
            continue

        update_data = {
            "guardian": result.get("guardian"),
            "element": result.get("element"),
            "gate": result.get("gate"),
            "tags": result.get("tags", []),
            "content_type": result.get("content_type"),
            "status": "classified",
            "metadata": {
                "classification_confidence": result.get("confidence", 0),
            },
        }

        try:
            supabase.table("asset_metadata").update(update_data).eq("id", asset_id).execute()
            classified += 1
            logger.debug(
                "Classified %s as %s / %s",
                filepath,
                result.get("guardian"),
                result.get("element"),
            )
        except Exception as exc:
            logger.warning("Failed to update asset %s: %s", asset_id, exc)

    logger.info("Classified %d assets", classified)
    return {"classified_count": classified}
