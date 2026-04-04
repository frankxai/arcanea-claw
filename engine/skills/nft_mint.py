"""nft-mint skill: Mint NFTs on-chain via Thirdweb or Crossmint.

Takes pinned assets with IPFS metadata URIs and mints them to the configured
blockchain (Base, Ethereum, Polygon). Supports batch minting.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.nft-mint")


def _mint_thirdweb(
    contract_address: str,
    token_uri: str,
    recipient: str,
    secret_key: str,
    chain: str = "base",
) -> dict | None:
    """Mint a single NFT via Thirdweb Engine API."""
    url = f"https://engine.thirdweb.com/contract/{chain}/{contract_address}/erc721/mint-to"

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            json={
                "receiver": recipient,
                "metadata": token_uri,  # IPFS URI
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "tx_hash": data.get("result", {}).get("transactionHash", ""),
            "queue_id": data.get("result", {}).get("queueId", ""),
        }
    except Exception as exc:
        logger.warning("Thirdweb mint failed: %s", exc)
        return None


def _mint_crossmint(
    collection_id: str,
    token_uri: str,
    recipient: str,
    api_key: str,
) -> dict | None:
    """Mint via Crossmint (no-code, credit card + crypto)."""
    url = f"https://www.crossmint.com/api/2022-06-09/collections/{collection_id}/nfts"

    try:
        resp = requests.post(
            url,
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json={
                "recipient": f"email:{recipient}" if "@" in recipient else recipient,
                "metadata": {"metadataUri": token_uri},
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "mint_id": data.get("id", ""),
            "action_id": data.get("actionId", ""),
            "on_chain": data.get("onChain", {}),
        }
    except Exception as exc:
        logger.warning("Crossmint mint failed: %s", exc)
        return None


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Mint pinned NFTs on-chain."""
    mint_cfg = config.get("mint", {})
    provider = mint_cfg.get("provider", "thirdweb")
    chain = mint_cfg.get("chain", "base")
    contract_address = os.environ.get("NFT_CONTRACT_ADDRESS", mint_cfg.get("contract_address", ""))
    recipient = os.environ.get("NFT_RECIPIENT", "")

    resp = (
        supabase.table("nft_assets")
        .select("id, token_id, collection_id, token_uri, metadata_ipfs_url")
        .eq("status", "pinned")
        .limit(20)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No NFTs to mint")
        return {"minted_count": 0}

    if not contract_address:
        logger.warning("NFT_CONTRACT_ADDRESS not set — skipping minting")
        return {"minted_count": 0, "skipped": "no_contract"}

    minted = 0

    for asset in assets:
        asset_id = asset["id"]
        token_uri = asset.get("token_uri") or asset.get("metadata_ipfs_url", "")

        result = None
        if provider == "thirdweb":
            # HIGH-03: NEVER fall back to config YAML for secrets
            secret = os.environ.get("THIRDWEB_SECRET_KEY", "")
            if secret:
                result = _mint_thirdweb(contract_address, token_uri, recipient, secret, chain)
        elif provider == "crossmint":
            api_key = os.environ.get("CROSSMINT_API_KEY", "")
            if api_key:
                result = _mint_crossmint(asset.get("collection_id", ""), token_uri, recipient, api_key)

        if result is None:
            logger.warning("Minting failed for NFT %s", asset_id)
            continue

        try:
            supabase.table("nft_assets").update({
                "tx_hash": result.get("tx_hash", ""),
                "mint_provider": provider,
                "chain": chain,
                "status": "minted",
            }).eq("id", asset_id).execute()
            minted += 1
        except Exception as exc:
            logger.warning("Failed to update NFT %s after mint: %s", asset_id, exc)

    logger.info("Minted %d NFTs via %s on %s", minted, provider, chain)
    return {"minted_count": minted}
