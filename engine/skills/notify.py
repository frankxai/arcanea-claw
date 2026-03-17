"""notify skill: Send pipeline run summary via configured webhook channels.

Collects stats from all pipeline steps, formats a summary, and delivers it
to Discord, Slack, or generic webhook endpoints. Also updates agent_registry.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.notify")


def _format_message(stats: dict[str, Any]) -> str:
    """Format pipeline stats into a human-readable summary."""
    hero_count = stats.get("hero_count", 0)
    hero_suffix = f" ({hero_count} hero-tier!)" if hero_count else ""

    lines = [
        "**ArcaneaClaw Pipeline Complete**",
        f"- {stats.get('new_files_count', 0)} new files scanned",
        f"- {stats.get('classified_count', 0)} classified (Guardian assigned)",
        f"- {stats.get('duplicates_found', 0)} duplicates removed",
        f"- {stats.get('processed_count', 0)} processed (WebP + variants)",
        f"- {stats.get('scored_count', 0)} scored{hero_suffix}",
        f"- {stats.get('uploaded_count', 0)} uploaded to storage",
        f"- {stats.get('posts_queued', 0)} social posts drafted",
        "",
        f"_Next run in 15 minutes._ | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    return "\n".join(lines)


def _send_discord(webhook_url: str, message: str) -> bool:
    """Send a message to a Discord webhook."""
    try:
        resp = requests.post(
            webhook_url,
            json={"content": message},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Discord notification failed: %s", exc)
        return False


def _send_slack(webhook_url: str, message: str) -> bool:
    """Send a message to a Slack incoming webhook."""
    # Convert markdown bold to Slack bold
    slack_message = message.replace("**", "*")
    try:
        resp = requests.post(
            webhook_url,
            json={"text": slack_message},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Slack notification failed: %s", exc)
        return False


def _send_generic_webhook(webhook_url: str, message: str, stats: dict[str, Any]) -> bool:
    """Send pipeline stats to a generic webhook as JSON."""
    try:
        resp = requests.post(
            webhook_url,
            json={
                "message": message,
                "stats": stats,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": "arcanea-claw",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Webhook notification failed: %s", exc)
        return False


def _update_agent_registry(supabase: Any, stats: dict[str, Any]) -> None:
    """Update agent_registry with total items processed."""
    total = sum(
        stats.get(k, 0) for k in [
            "new_files_count", "classified_count", "processed_count",
            "scored_count", "uploaded_count", "posts_queued",
        ]
    )
    try:
        supabase.table("agent_registry").update({
            "items_processed": total,
            "last_active": datetime.now(timezone.utc).isoformat(),
        }).eq("agent_id", "arcanea-claw-primary").execute()
    except Exception as exc:
        logger.warning("Failed to update agent_registry: %s", exc)


def run(
    config: dict[str, Any],
    supabase: Any,
    pipeline_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send pipeline summary notifications.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.
        pipeline_stats: Aggregated stats from all pipeline steps.

    Returns:
        Dict with ``notifications_sent``.
    """
    stats = pipeline_stats or {}
    notify_cfg = config.get("notify", {})

    if not notify_cfg.get("enabled", True):
        logger.info("Notifications disabled")
        return {"notifications_sent": 0}

    message = _format_message(stats)
    channels = notify_cfg.get("channels", [])
    sent = 0

    for channel in channels:
        channel_type = channel.get("type", "webhook")
        raw_url = channel.get("url", "")

        # Resolve environment variable references like ${NOTIFY_WEBHOOK_URL}
        if raw_url.startswith("${") and raw_url.endswith("}"):
            env_var = raw_url[2:-1]
            url = os.environ.get(env_var, "")
        else:
            url = raw_url

        if not url:
            logger.warning("No URL configured for %s channel", channel_type)
            continue

        success = False
        if channel_type == "discord":
            success = _send_discord(url, message)
        elif channel_type == "slack":
            success = _send_slack(url, message)
        else:
            success = _send_generic_webhook(url, message, stats)

        if success:
            sent += 1

    # Update agent registry
    _update_agent_registry(supabase, stats)

    logger.info("Sent %d/%d notifications", sent, len(channels))
    return {"notifications_sent": sent}
