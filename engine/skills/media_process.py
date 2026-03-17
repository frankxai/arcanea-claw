"""media-process skill: Convert classified media to WebP and generate size variants.

Produces production-ready WebP files organized by guardian in the staging
directory, with named variants for hero, gallery, social, and thumbnail use.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger("arcanea-claw.media-process")

# Default variants if config is missing
DEFAULT_VARIANTS: dict[str, tuple[int, int]] = {
    "hero": (1920, 1080),
    "gallery": (1200, 800),
    "social_square": (1080, 1080),
    "social_story": (1080, 1920),
    "social_wide": (1200, 628),
    "thumbnail": (320, 320),
}


def _resize_contain(img: Image.Image, max_dim: int) -> Image.Image:
    """Resize image so the longest side is at most max_dim, preserving ratio."""
    w, h = img.size
    if max(w, h) <= max_dim:
        return img.copy()
    scale = max_dim / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return img.resize((new_w, new_h), Image.LANCZOS)


def _resize_cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize to cover the target dimensions, then center-crop."""
    w, h = img.size
    target_ratio = target_w / target_h
    img_ratio = w / h

    if img_ratio > target_ratio:
        # Image is wider — fit height, crop width
        new_h = target_h
        new_w = int(target_h * img_ratio)
    else:
        # Image is taller — fit width, crop height
        new_w = target_w
        new_h = int(target_w / img_ratio)

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Center crop
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _save_webp(img: Image.Image, path: Path, quality: int) -> None:
    """Save image as WebP, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path), format="WEBP", quality=quality)


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Process classified assets into WebP variants.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.

    Returns:
        Dict with ``processed_count``.
    """
    proc_cfg = config.get("process", {})
    staging_dir = Path(proc_cfg.get("staging_dir", "/data/staging"))
    webp_quality: int = proc_cfg.get("webp_quality", 85)
    max_dim: int = proc_cfg.get("max_dimension", 2400)

    # Build variant map from config or defaults
    raw_variants = proc_cfg.get("size_variants", {})
    variants: dict[str, tuple[int, int]] = {}
    for name, dims in (raw_variants or DEFAULT_VARIANTS).items():
        if isinstance(dims, (list, tuple)) and len(dims) == 2:
            variants[name] = (int(dims[0]), int(dims[1]))
        else:
            variants[name] = DEFAULT_VARIANTS.get(name, (1200, 800))

    # Fetch classified but unprocessed assets
    resp = (
        supabase.table("asset_metadata")
        .select("id, file_path, file_name, guardian")
        .eq("status", "classified")
        .limit(50)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No assets to process")
        return {"processed_count": 0}

    processed = 0

    for asset in assets:
        asset_id = asset["id"]
        filepath = Path(asset["file_path"])
        guardian = asset.get("guardian", "unclassified") or "unclassified"
        stem = filepath.stem

        if not filepath.exists():
            logger.warning("Source file missing: %s", filepath)
            continue

        try:
            img = Image.open(filepath)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
        except Exception as exc:
            logger.warning("Cannot open image %s: %s", filepath, exc)
            continue

        variant_paths: dict[str, str] = {}

        # Base WebP (constrained to max_dim)
        try:
            base = _resize_contain(img, max_dim)
            base_path = staging_dir / guardian / "base" / f"{stem}.webp"
            _save_webp(base, base_path, webp_quality)
            variant_paths["base"] = str(base_path)
        except Exception as exc:
            logger.warning("Failed base conversion for %s: %s", filepath, exc)
            continue

        # Named variants
        for variant_name, (tw, th) in variants.items():
            try:
                variant_img = _resize_cover_crop(img, tw, th)
                variant_path = staging_dir / guardian / variant_name / f"{stem}.webp"
                _save_webp(variant_img, variant_path, webp_quality)
                variant_paths[variant_name] = str(variant_path)
            except Exception as exc:
                logger.warning(
                    "Failed variant %s for %s: %s", variant_name, filepath, exc
                )

        # Update asset_metadata
        try:
            supabase.table("asset_metadata").update({
                "status": "processed",
                "metadata": {"variant_paths": variant_paths},
            }).eq("id", asset_id).execute()
            processed += 1
        except Exception as exc:
            logger.warning("Failed to update asset %s: %s", asset_id, exc)

        img.close()

    logger.info("Processed %d assets into WebP variants", processed)
    return {"processed_count": processed}
