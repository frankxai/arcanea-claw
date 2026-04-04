"""herald-schedule skill: Schedule approved content for optimal posting times.

Moves approved drafts into scheduled status with platform-optimal timing.
Respects daily post limits per platform.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.herald-schedule")

# Optimal posting windows (UTC) by platform
OPTIMAL_HOURS = {
    "twitter": [14, 17, 20],     # 2pm, 5pm, 8pm UTC (US morning/afternoon)
    "linkedin": [13, 16],         # 1pm, 4pm UTC (US business hours)
    "discord": [15, 19, 22],      # Afternoon/evening
    "farcaster": [14, 18],        # Crypto-native hours
}


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Schedule approved drafts for posting."""
    platforms = config.get("platforms", {})

    # Get approved content
    resp = (
        supabase.table("social_queue")
        .select("id, platform, content_text, status")
        .in_("status", ["approved", "thread_ready"])
        .order("created_at")
        .execute()
    )
    items = resp.data or []

    if not items:
        logger.info("No approved content to schedule")
        return {"scheduled_count": 0}

    scheduled = 0
    now = datetime.now(timezone.utc)

    # Count today's posts per platform
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for platform_name, platform_cfg in platforms.items():
        if not platform_cfg.get("enabled"):
            continue

        max_daily = platform_cfg.get("max_daily_posts", 5)
        platform_items = [i for i in items if i["platform"] == platform_name]

        # Check existing scheduled/published today
        existing = (
            supabase.table("social_queue")
            .select("id", count="exact")
            .eq("platform", platform_name)
            .in_("status", ["scheduled", "published"])
            .gte("scheduled_at", today_start.isoformat())
            .execute()
        )
        today_count = existing.count or 0
        remaining_slots = max_daily - today_count

        if remaining_slots <= 0:
            logger.info("Platform %s: daily limit reached (%d)", platform_name, max_daily)
            continue

        # Schedule items into optimal time slots
        hours = OPTIMAL_HOURS.get(platform_name, [14, 18])
        slot_idx = today_count  # start from next available slot

        for item in platform_items[:remaining_slots]:
            hour = hours[slot_idx % len(hours)]
            scheduled_time = now.replace(hour=hour, minute=0, second=0)
            if scheduled_time <= now:
                scheduled_time += timedelta(days=1)

            try:
                supabase.table("social_queue").update({
                    "scheduled_at": scheduled_time.isoformat(),
                    "status": "scheduled",
                }).eq("id", item["id"]).execute()
                scheduled += 1
                slot_idx += 1
            except Exception as exc:
                logger.warning("Failed to schedule %s: %s", item["id"], exc)

    logger.info("Scheduled %d posts", scheduled)
    return {"scheduled_count": scheduled}
