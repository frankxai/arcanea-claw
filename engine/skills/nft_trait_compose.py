"""nft-trait-compose skill: Layer-based trait composition for generative NFT collections.

Takes generated base images and applies trait overlays (backgrounds, accessories,
effects) based on rarity weights to produce final composited artwork.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger("arcanea-claw.nft-trait-compose")


def _weighted_choice(options: list[str], weights: dict[str, float], rarity: str) -> str:
    """Select a trait option weighted by rarity tier."""
    # Higher rarity = more access to rare traits
    tier_boost = {"common": 0, "uncommon": 0.1, "rare": 0.2, "epic": 0.3, "legendary": 0.5}
    boost = tier_boost.get(rarity, 0)

    # Simple weighted selection — later traits in list are "rarer"
    n = len(options)
    w = [1.0] * n
    for i in range(n):
        if i >= n * 0.7:  # top 30% are rare
            w[i] = 0.1 + boost
        elif i >= n * 0.4:  # middle 30% are uncommon
            w[i] = 0.3 + boost * 0.5

    total = sum(w)
    w = [x / total for x in w]
    return random.choices(options, weights=w, k=1)[0]


def _composite_layers(base_path: str, trait_layers: dict[str, str], output_path: Path) -> bool:
    """Composite trait overlay images onto the base image."""
    try:
        base = Image.open(base_path).convert("RGBA")

        for layer_name, layer_path in trait_layers.items():
            if not Path(layer_path).exists():
                continue
            overlay = Image.open(layer_path).convert("RGBA")
            overlay = overlay.resize(base.size, Image.LANCZOS)
            base = Image.alpha_composite(base, overlay)

        # Save final composite
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final = base.convert("RGB")
        final.save(str(output_path), format="PNG", quality=95)
        base.close()
        return True
    except Exception as exc:
        logger.warning("Compositing failed for %s: %s", base_path, exc)
        return False


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Compose traits onto generated NFT artwork.

    For each 'generated' NFT, assign traits based on rarity weights
    and composite overlay layers if available.
    """
    traits_cfg = config.get("traits", {})
    rarity_weights = traits_cfg.get("rarity_weights", {
        "common": 0.50, "uncommon": 0.25, "rare": 0.15, "epic": 0.07, "legendary": 0.03,
    })

    # Available trait pools
    backgrounds = traits_cfg.get("backgrounds", [])
    elements = traits_cfg.get("elements", [])
    accessories = traits_cfg.get("accessories", [])
    expressions = traits_cfg.get("expressions", [])

    resp = (
        supabase.table("nft_assets")
        .select("id, image_path, rarity, guardian, element, traits, token_id, collection_id")
        .eq("status", "generated")
        .limit(50)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No NFTs to compose traits for")
        return {"composed_count": 0}

    composed = 0

    for asset in assets:
        asset_id = asset["id"]
        rarity = asset.get("rarity", "common")
        existing_traits = asset.get("traits") or {}

        # Assign traits from pools
        composed_traits = {
            "background": _weighted_choice(backgrounds, rarity_weights, rarity) if backgrounds else "Default",
            "element_effect": _weighted_choice(elements, rarity_weights, rarity) if elements else asset.get("element", "Void"),
            "accessory": _weighted_choice(accessories, rarity_weights, rarity) if accessories else "None",
            "expression": _weighted_choice(expressions, rarity_weights, rarity) if expressions else "Neutral",
            "guardian": asset.get("guardian", "Unknown"),
            "rarity": rarity,
        }
        composed_traits.update(existing_traits)

        # For now, store traits without layer compositing
        # (layer compositing requires pre-made overlay PNGs per trait)
        output_dir = Path("/data/nft-composed")
        output_path = output_dir / f"{asset.get('collection_id', 'default')}" / f"{asset.get('token_id', asset_id)}.png"

        image_path = asset.get("image_path", "")
        final_path = image_path  # default: use generated image as-is

        # If overlay layers exist, composite them
        layer_dir = Path("/data/nft-layers")
        if layer_dir.exists():
            layers = {}
            for trait_name, trait_value in composed_traits.items():
                layer_file = layer_dir / trait_name / f"{trait_value}.png"
                if layer_file.exists():
                    layers[trait_name] = str(layer_file)

            if layers and image_path:
                if _composite_layers(image_path, layers, output_path):
                    final_path = str(output_path)

        try:
            supabase.table("nft_assets").update({
                "traits": composed_traits,
                "composed_image_path": final_path,
                "status": "composed",
            }).eq("id", asset_id).execute()
            composed += 1
        except Exception as exc:
            logger.warning("Failed to update NFT %s traits: %s", asset_id, exc)

    logger.info("Composed traits for %d NFTs", composed)
    return {"composed_count": composed}
