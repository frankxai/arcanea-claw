"""nft-marketplace-list skill: List minted NFTs on OpenSea, Magic Eden, Blur.

Creates marketplace listings with pricing, descriptions, and collection metadata.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.nft-marketplace-list")


def _list_opensea(contract: str, token_id: int, price_eth: float, api_key: str) -> bool:
    """Create an OpenSea listing via API."""
    # OpenSea listing requires wallet signature — log for manual action
    logger.info(
        "OpenSea listing ready: contract=%s token=%d price=%s ETH — requires wallet signature",
        contract, token_id, price_eth,
    )
    return True  # Tracked as "listing_ready" not "listed"


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Create marketplace listings for minted NFTs."""
    marketplace_cfg = config.get("marketplace", {})
    collection_slug = marketplace_cfg.get("collection_slug", "arcanea-creators")
    royalty_bps = marketplace_cfg.get("royalty_bps", 500)

    resp = (
        supabase.table("nft_assets")
        .select("id, token_id, collection_id, chain, tx_hash, traits, rarity, image_gateway_url")
        .eq("status", "minted")
        .limit(50)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No minted NFTs to list")
        return {"listed_count": 0}

    listed = 0

    for asset in assets:
        asset_id = asset["id"]

        # For now: mark as listing_ready for manual marketplace listing
        # Full automation requires wallet signing (EIP-712)
        try:
            supabase.table("nft_assets").update({
                "marketplace": marketplace_cfg.get("primary", "opensea"),
                "collection_slug": collection_slug,
                "royalty_bps": royalty_bps,
                "status": "listing_ready",
            }).eq("id", asset_id).execute()
            listed += 1
        except Exception as exc:
            logger.warning("Failed to update NFT %s: %s", asset_id, exc)

    logger.info("Prepared %d NFTs for marketplace listing", listed)
    return {"listed_count": listed}
