"""nft-rarity-score skill: Calculate rarity scores for NFT collections.

Analyzes trait distribution across the collection and computes statistical
rarity scores. Uses the standard 1/(trait_count/total) formula.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Any

logger = logging.getLogger("arcanea-claw.nft-rarity-score")


def _calculate_rarity_score(traits: dict[str, str], trait_counts: dict[str, Counter], total: int) -> float:
    """Calculate rarity score as sum of 1/(frequency) for each trait."""
    score = 0.0
    for trait_type, trait_value in traits.items():
        if trait_type in ("rarity",):  # skip meta-traits
            continue
        count = trait_counts.get(trait_type, Counter()).get(str(trait_value), total)
        if count > 0:
            score += 1.0 / (count / total)
    return round(score, 2)


def _rank_to_tier(rank: int, total: int) -> str:
    """Convert rank to display tier."""
    pct = rank / total if total > 0 else 1.0
    if pct <= 0.01:
        return "Mythic"
    elif pct <= 0.05:
        return "Legendary"
    elif pct <= 0.15:
        return "Epic"
    elif pct <= 0.35:
        return "Rare"
    elif pct <= 0.65:
        return "Uncommon"
    return "Common"


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Calculate and assign rarity scores across collections."""
    # Get all NFTs in collections that have composited traits
    resp = (
        supabase.table("nft_assets")
        .select("id, token_id, collection_id, traits")
        .in_("status", ["composed", "metadata_ready", "pinned", "minted", "listing_ready"])
        .order("collection_id")
        .execute()
    )
    all_assets = resp.data or []

    if not all_assets:
        logger.info("No NFTs to score rarity for")
        return {"scored_count": 0}

    # Group by collection
    collections: dict[str, list[dict]] = {}
    for asset in all_assets:
        cid = asset.get("collection_id", "default")
        collections.setdefault(cid, []).append(asset)

    scored = 0

    for collection_id, assets in collections.items():
        total = len(assets)
        if total < 2:
            continue

        # Build trait frequency counters
        trait_counts: dict[str, Counter] = {}
        for asset in assets:
            traits = asset.get("traits") or {}
            for trait_type, trait_value in traits.items():
                if trait_type == "rarity":
                    continue
                trait_counts.setdefault(trait_type, Counter())[str(trait_value)] += 1

        # Calculate scores
        scored_assets: list[tuple[str, float]] = []
        for asset in assets:
            traits = asset.get("traits") or {}
            score = _calculate_rarity_score(traits, trait_counts, total)
            scored_assets.append((asset["id"], score))

        # Sort by score (descending = rarer)
        scored_assets.sort(key=lambda x: x[1], reverse=True)

        # Assign ranks and update
        for rank, (asset_id, score) in enumerate(scored_assets, 1):
            tier = _rank_to_tier(rank, total)
            try:
                supabase.table("nft_assets").update({
                    "rarity_score": score,
                    "rarity_rank": rank,
                    "rarity_tier": tier,
                }).eq("id", asset_id).execute()
                scored += 1
            except Exception as exc:
                logger.warning("Failed to update rarity for %s: %s", asset_id, exc)

        logger.info(
            "Collection %s: scored %d NFTs (top rarity: %.1f)",
            collection_id, len(scored_assets),
            scored_assets[0][1] if scored_assets else 0,
        )

    return {"scored_count": scored}
