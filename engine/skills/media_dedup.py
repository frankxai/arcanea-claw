"""media-dedup skill: Detect and reject duplicate media files by content hash.

Groups assets by file_hash, keeps the best (highest quality_score or earliest
created_at), and marks the rest as rejected with a 'duplicate' tag.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger("arcanea-claw.media-dedup")


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Find and reject duplicate assets.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.

    Returns:
        Dict with ``duplicates_found``.
    """
    # Fetch all non-rejected assets with their hashes
    resp = (
        supabase.table("asset_metadata")
        .select("id, file_hash, quality_score, created_at, tags, status")
        .neq("status", "rejected")
        .order("created_at", desc=False)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No assets to check for duplicates")
        return {"duplicates_found": 0}

    # Group by file_hash
    hash_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for asset in assets:
        fhash = asset.get("file_hash")
        if fhash:
            hash_groups[fhash].append(asset)

    duplicates_found = 0

    for fhash, group in hash_groups.items():
        if len(group) < 2:
            continue

        # Sort: highest quality_score first, then earliest created_at
        group.sort(
            key=lambda a: (
                -(a.get("quality_score") or 0),
                a.get("created_at", ""),
            )
        )

        # Keep the first (best), mark the rest as duplicates
        keeper = group[0]
        rejects = group[1:]

        for dup in rejects:
            existing_tags = dup.get("tags") or []
            if "duplicate" not in existing_tags:
                existing_tags.append("duplicate")

            try:
                supabase.table("asset_metadata").update({
                    "status": "rejected",
                    "tags": existing_tags,
                    "metadata": {
                        "duplicate_of": keeper["id"],
                        "rejected_reason": "duplicate_hash",
                    },
                }).eq("id", dup["id"]).execute()
                duplicates_found += 1
            except Exception as exc:
                logger.warning(
                    "Failed to reject duplicate %s: %s", dup["id"], exc
                )

    logger.info(
        "Found %d duplicates across %d unique hashes",
        duplicates_found,
        len([g for g in hash_groups.values() if len(g) > 1]),
    )
    return {"duplicates_found": duplicates_found}
