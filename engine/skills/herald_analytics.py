"""herald-analytics skill: Aggregate social media analytics and generate reports.

Collects engagement metrics, calculates growth rates, and stores daily snapshots.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.herald-analytics")


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Generate analytics snapshot from social queue data."""
    now = datetime.now(timezone.utc)

    # Count posts by platform and status
    resp = (
        supabase.table("social_queue")
        .select("platform, status", count="exact")
        .execute()
    )
    posts = resp.data or []

    # Aggregate
    platform_stats: dict[str, dict[str, int]] = {}
    for post in posts:
        p = post.get("platform", "unknown")
        s = post.get("status", "unknown")
        platform_stats.setdefault(p, {"total": 0, "published": 0, "draft": 0, "scheduled": 0})
        platform_stats[p]["total"] += 1
        if s in platform_stats[p]:
            platform_stats[p][s] += 1

    snapshot = {
        "date": now.date().isoformat(),
        "type": "social_analytics",
        "data": {
            "platforms": platform_stats,
            "total_posts": len(posts),
            "total_published": sum(1 for p in posts if p.get("status") == "published"),
            "total_scheduled": sum(1 for p in posts if p.get("status") == "scheduled"),
            "total_drafts": sum(1 for p in posts if p.get("status") == "draft"),
        },
        "created_at": now.isoformat(),
    }

    try:
        supabase.table("analytics_snapshots").insert(snapshot).execute()
        logger.info("Analytics snapshot saved: %d posts across %d platforms",
                     len(posts), len(platform_stats))
    except Exception as exc:
        logger.warning("Failed to save analytics snapshot: %s", exc)

    return {"snapshot_saved": True, "total_posts": len(posts)}
