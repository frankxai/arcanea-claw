"""media-upload skill: Upload scored media to Vercel Blob or Supabase Storage.

Routes assets by quality tier:
- hero (80+) -> Vercel Blob via Node subprocess
- gallery (60-79) -> Supabase Storage 'arcanea-gallery' bucket
- thumbnail (40-59) -> Supabase Storage 'thumbnails' bucket
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("arcanea-claw.media-upload")

# Tier to storage bucket mapping for Supabase
SUPABASE_BUCKETS: dict[str, str] = {
    "gallery": "arcanea-gallery",
    "thumbnail": "thumbnails",
}


def _upload_to_vercel_blob(filepath: str, guardian: str) -> str | None:
    """Upload a file to Vercel Blob using a Node helper script.

    Returns the public URL on success, None on failure.
    """
    script_path = Path(__file__).parent.parent / "helpers" / "vercel-upload.mjs"
    if not script_path.exists():
        logger.warning(
            "Vercel upload helper not found at %s — falling back to Supabase",
            script_path,
        )
        return None

    try:
        result = subprocess.run(
            ["node", str(script_path), filepath, guardian],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("url")
        else:
            logger.warning("Vercel upload failed: %s", result.stderr)
            return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
        logger.warning("Vercel upload error: %s", exc)
        return None


def _upload_to_supabase_storage(
    supabase: Any,
    filepath: str,
    bucket: str,
    guardian: str,
) -> str | None:
    """Upload a file to a Supabase Storage bucket.

    Returns the public URL on success, None on failure.
    """
    file_path = Path(filepath)
    if not file_path.exists():
        logger.warning("File not found for upload: %s", filepath)
        return None

    storage_path = f"{guardian}/{file_path.name}"
    content_type = "image/webp"

    try:
        with open(file_path, "rb") as f:
            supabase.storage.from_(bucket).upload(
                storage_path,
                f.read(),
                {"content-type": content_type},
            )
        # Get public URL
        public_url = supabase.storage.from_(bucket).get_public_url(storage_path)
        return public_url
    except Exception as exc:
        logger.warning("Supabase upload failed (%s/%s): %s", bucket, storage_path, exc)
        return None


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Upload scored assets to appropriate storage backends.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.

    Returns:
        Dict with ``uploaded_count``.
    """
    resp = (
        supabase.table("asset_metadata")
        .select("id, file_path, guardian, quality_tier, metadata")
        .eq("status", "scored")
        .in_("quality_tier", ["hero", "gallery", "thumbnail"])
        .limit(50)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No assets to upload")
        return {"uploaded_count": 0}

    uploaded = 0

    for asset in assets:
        asset_id = asset["id"]
        tier = asset["quality_tier"]
        guardian = asset.get("guardian", "unclassified") or "unclassified"
        variant_paths = (asset.get("metadata") or {}).get("variant_paths", {})

        # Select the appropriate variant for upload
        if tier == "hero":
            upload_file = variant_paths.get("hero", variant_paths.get("base", asset["file_path"]))
        elif tier == "gallery":
            upload_file = variant_paths.get("gallery", variant_paths.get("base", asset["file_path"]))
        else:
            upload_file = variant_paths.get("thumbnail", variant_paths.get("base", asset["file_path"]))

        # Also upload thumbnail for all tiers
        thumb_file = variant_paths.get("thumbnail")

        storage_url: str | None = None
        thumbnail_url: str | None = None

        # Upload main asset
        if tier == "hero":
            storage_url = _upload_to_vercel_blob(upload_file, guardian)
            # Fallback to Supabase if Vercel upload fails
            if storage_url is None:
                storage_url = _upload_to_supabase_storage(
                    supabase, upload_file, "arcanea-gallery", guardian
                )
        else:
            bucket = SUPABASE_BUCKETS.get(tier, "arcanea-gallery")
            storage_url = _upload_to_supabase_storage(
                supabase, upload_file, bucket, guardian
            )

        # Upload thumbnail
        if thumb_file:
            thumbnail_url = _upload_to_supabase_storage(
                supabase, thumb_file, "thumbnails", guardian
            )

        if storage_url is None:
            logger.warning("All upload methods failed for asset %s", asset_id)
            continue

        # Update asset metadata
        try:
            supabase.table("asset_metadata").update({
                "storage_url": storage_url,
                "thumbnail_url": thumbnail_url,
                "storage_tier": tier,
                "status": "uploaded",
            }).eq("id", asset_id).execute()
            uploaded += 1
            logger.debug("Uploaded %s to %s (%s)", upload_file, tier, storage_url[:80])
        except Exception as exc:
            logger.warning("Failed to update asset %s after upload: %s", asset_id, exc)

    logger.info("Uploaded %d assets", uploaded)
    return {"uploaded_count": uploaded}
