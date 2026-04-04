"""nft-ipfs-pin skill: Pin NFT images and metadata to IPFS via Pinata.

Uploads the composed image and metadata JSON to IPFS, updates the metadata
with the correct IPFS URIs (ipfs:// protocol), and stores CIDs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.nft-ipfs-pin")


def _pin_file_to_pinata(file_path: str, name: str, jwt: str) -> str | None:
    """Pin a file to IPFS via Pinata. Returns the CID (IPFS hash)."""
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"

    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                files={"file": (Path(file_path).name, f)},
                data={"pinataMetadata": json.dumps({"name": name})},
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=120,
            )
        resp.raise_for_status()
        return resp.json().get("IpfsHash")
    except Exception as exc:
        logger.warning("Pinata file upload failed for %s: %s", file_path, exc)
        return None


def _pin_json_to_pinata(data: dict, name: str, jwt: str) -> str | None:
    """Pin JSON metadata to IPFS via Pinata. Returns the CID."""
    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"

    try:
        resp = requests.post(
            url,
            json={
                "pinataContent": data,
                "pinataMetadata": {"name": name},
            },
            headers={
                "Authorization": f"Bearer {jwt}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("IpfsHash")
    except Exception as exc:
        logger.warning("Pinata JSON upload failed for %s: %s", name, exc)
        return None


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Pin NFT images and metadata to IPFS."""
    ipfs_cfg = config.get("ipfs", {})
    jwt = os.environ.get("PINATA_JWT", ipfs_cfg.get("pinata_jwt", ""))
    gateway = ipfs_cfg.get("gateway", "https://gateway.pinata.cloud/ipfs/")

    if not jwt:
        logger.error("PINATA_JWT not set — cannot pin to IPFS")
        return {"pinned_count": 0}

    resp = (
        supabase.table("nft_assets")
        .select("id, token_id, collection_id, composed_image_path, metadata_json, metadata_path")
        .eq("status", "metadata_ready")
        .limit(50)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No NFTs to pin to IPFS")
        return {"pinned_count": 0}

    pinned = 0

    for asset in assets:
        asset_id = asset["id"]
        token_id = asset.get("token_id", 0)
        collection_id = asset.get("collection_id", "default")
        image_path = asset.get("composed_image_path", "")
        metadata = asset.get("metadata_json", {})

        # 1. Pin image
        image_cid = None
        if image_path and Path(image_path).exists():
            image_cid = _pin_file_to_pinata(
                image_path,
                f"{collection_id}-{token_id}-image",
                jwt,
            )

        if image_cid is None:
            logger.warning("Failed to pin image for NFT %s", asset_id)
            continue

        # 2. Update metadata with IPFS image URI
        metadata["image"] = f"ipfs://{image_cid}"

        # 3. Pin metadata JSON
        metadata_cid = _pin_json_to_pinata(
            metadata,
            f"{collection_id}-{token_id}-metadata",
            jwt,
        )

        if metadata_cid is None:
            logger.warning("Failed to pin metadata for NFT %s", asset_id)
            continue

        # 4. Update database
        try:
            supabase.table("nft_assets").update({
                "image_cid": image_cid,
                "image_ipfs_url": f"ipfs://{image_cid}",
                "image_gateway_url": f"{gateway}{image_cid}",
                "metadata_cid": metadata_cid,
                "metadata_ipfs_url": f"ipfs://{metadata_cid}",
                "token_uri": f"ipfs://{metadata_cid}",
                "metadata_json": metadata,
                "status": "pinned",
            }).eq("id", asset_id).execute()
            pinned += 1
            logger.debug("Pinned NFT %s: image=%s metadata=%s", token_id, image_cid, metadata_cid)
        except Exception as exc:
            logger.warning("Failed to update NFT %s after pin: %s", asset_id, exc)

    logger.info("Pinned %d NFTs to IPFS", pinned)
    return {"pinned_count": pinned}
