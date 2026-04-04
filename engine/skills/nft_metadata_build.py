"""nft-metadata-build skill: Generate ERC-721/1155 compliant metadata JSON.

Creates OpenSea-compatible metadata with attributes, image URIs (pre-IPFS),
and collection-level metadata. Follows the OpenSea metadata standard.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("arcanea-claw.nft-metadata-build")

RARITY_DISPLAY = {
    "common": {"boost_number": 1, "max_value": 5},
    "uncommon": {"boost_number": 2, "max_value": 5},
    "rare": {"boost_number": 3, "max_value": 5},
    "epic": {"boost_number": 4, "max_value": 5},
    "legendary": {"boost_number": 5, "max_value": 5},
}


def _build_attributes(traits: dict[str, Any], rarity: str) -> list[dict]:
    """Convert trait dict to OpenSea-compatible attributes array."""
    attributes = []

    for trait_type, value in traits.items():
        if trait_type == "rarity":
            # Rarity as a boost number for OpenSea ranking
            display = RARITY_DISPLAY.get(value, RARITY_DISPLAY["common"])
            attributes.append({
                "display_type": "boost_number",
                "trait_type": "Rarity Power",
                "value": display["boost_number"],
                "max_value": display["max_value"],
            })
            attributes.append({
                "trait_type": "Rarity",
                "value": value.capitalize(),
            })
        elif isinstance(value, (int, float)):
            attributes.append({
                "display_type": "number",
                "trait_type": trait_type.replace("_", " ").title(),
                "value": value,
            })
        else:
            attributes.append({
                "trait_type": trait_type.replace("_", " ").title(),
                "value": str(value),
            })

    return attributes


def _build_metadata(asset: dict, collection_name: str) -> dict:
    """Build ERC-721 compatible metadata JSON."""
    traits = asset.get("traits", {})
    rarity = asset.get("rarity", "common")
    guardian = traits.get("guardian", asset.get("guardian", "Unknown"))
    token_id = asset.get("token_id", 0)

    return {
        "name": f"{collection_name} #{token_id}",
        "description": (
            f"A {rarity} creator from the Arcanea universe. "
            f"Aligned with {guardian}, channeling the power of {traits.get('element_effect', 'the unknown')}. "
            f"Part of the {collection_name} collection."
        ),
        "image": "",  # Will be set after IPFS pin
        "external_url": f"https://arcanea.ai/nft/{token_id}",
        "attributes": _build_attributes(traits, rarity),
        "properties": {
            "collection": collection_name,
            "guardian": guardian,
            "element": traits.get("element_effect", ""),
            "created_by": "ArcaneaClaw Forge",
        },
    }


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Build metadata JSON for composed NFTs."""
    collections = config.get("collections", [])
    collection_map = {c["name"]: c for c in collections}

    resp = (
        supabase.table("nft_assets")
        .select("id, token_id, collection_id, traits, guardian, element, rarity, composed_image_path")
        .eq("status", "composed")
        .limit(100)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No NFTs to build metadata for")
        return {"metadata_count": 0}

    built = 0
    output_dir = Path("/data/nft-metadata")
    output_dir.mkdir(parents=True, exist_ok=True)

    for asset in assets:
        asset_id = asset["id"]
        collection_id = asset.get("collection_id", "default")
        token_id = asset.get("token_id", 0)

        # Find collection name
        collection_name = collection_id
        for c in collections:
            if c.get("name", "").lower().replace(" ", "-") == collection_id:
                collection_name = c["name"]
                break

        metadata = _build_metadata(asset, collection_name)

        # Write metadata JSON
        meta_dir = output_dir / collection_id
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / f"{token_id}.json"
        meta_path.write_text(json.dumps(metadata, indent=2))

        try:
            supabase.table("nft_assets").update({
                "metadata_json": metadata,
                "metadata_path": str(meta_path),
                "status": "metadata_ready",
            }).eq("id", asset_id).execute()
            built += 1
        except Exception as exc:
            logger.warning("Failed to update metadata for NFT %s: %s", asset_id, exc)

    logger.info("Built metadata for %d NFTs", built)
    return {"metadata_count": built}
