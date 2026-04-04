"""Cross-claw event pipeline — makes the fleet self-orchestrating.

When one claw produces output, it can trigger actions in other claws.
Events are stored in Supabase and picked up by the target claw's next run.

Event flow:
  Media hero uploaded  → Herald: draft announcement post
  Scout alpha detected → Herald: draft opportunity post
  Forge NFT minted     → Herald: announce mint + social queue
  Scribe blog ready    → Herald: thread it + distribute
  Media classified     → Forge: check if NFT-worthy
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.events")

# Event type → what it triggers
EVENT_TRIGGERS: dict[str, dict[str, Any]] = {
    "media.hero_uploaded": {
        "target_claw": "herald",
        "action": "draft_announcement",
        "description": "New hero-tier art uploaded — draft social post",
    },
    "media.batch_complete": {
        "target_claw": "herald",
        "action": "draft_pipeline_summary",
        "description": "Pipeline batch complete — summarize results",
    },
    "forge.nft_minted": {
        "target_claw": "herald",
        "action": "announce_mint",
        "description": "NFT minted on-chain — announce across platforms",
    },
    "forge.collection_complete": {
        "target_claw": "herald",
        "action": "launch_campaign",
        "description": "NFT collection complete — launch marketing campaign",
    },
    "scout.alpha_detected": {
        "target_claw": "herald",
        "action": "draft_alpha_response",
        "description": "High-value opportunity detected — draft response",
    },
    "scout.competitor_launch": {
        "target_claw": "scribe",
        "action": "draft_comparison",
        "description": "Competitor launched something — draft analysis",
    },
    "scribe.blog_ready": {
        "target_claw": "herald",
        "action": "thread_and_distribute",
        "description": "Blog post ready — create thread + cross-post",
    },
    "media.hero_classified": {
        "target_claw": "forge",
        "action": "evaluate_for_nft",
        "description": "Hero image classified — evaluate for NFT collection",
    },
}


def emit_event(
    supabase: Any,
    event_type: str,
    source_claw: str,
    payload: dict[str, Any],
) -> bool:
    """Emit a cross-claw event to Supabase.

    Events are stored in the claw_events table and picked up by
    the target claw's event watcher.
    """
    trigger = EVENT_TRIGGERS.get(event_type)
    if not trigger:
        logger.debug("Unknown event type: %s (no trigger configured)", event_type)
        return False

    event = {
        "event_type": event_type,
        "source_claw": source_claw,
        "target_claw": trigger["target_claw"],
        "action": trigger["action"],
        "payload": payload,
        "status": "pending",
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        supabase.table("claw_events").insert(event).execute()
        logger.info(
            "Event emitted: %s → %s.%s",
            event_type, trigger["target_claw"], trigger["action"],
        )
        return True
    except Exception as exc:
        logger.warning("Failed to emit event %s: %s", event_type, exc)
        return False


def consume_events(
    supabase: Any,
    claw_name: str,
    limit: int = 10,
) -> list[dict]:
    """Consume pending events targeted at this claw.

    Returns the events and marks them as 'processing'.
    """
    try:
        resp = (
            supabase.table("claw_events")
            .select("*")
            .eq("target_claw", claw_name)
            .eq("status", "pending")
            .order("emitted_at")
            .limit(limit)
            .execute()
        )
        events = resp.data or []

        # Mark as processing
        for event in events:
            supabase.table("claw_events").update(
                {"status": "processing"}
            ).eq("id", event["id"]).execute()

        if events:
            logger.info("Consumed %d events for %s", len(events), claw_name)
        return events
    except Exception as exc:
        logger.warning("Failed to consume events for %s: %s", claw_name, exc)
        return []


def complete_event(supabase: Any, event_id: str, result: dict | None = None) -> None:
    """Mark an event as completed."""
    try:
        supabase.table("claw_events").update({
            "status": "completed",
            "result": result or {},
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", event_id).execute()
    except Exception as exc:
        logger.warning("Failed to complete event %s: %s", event_id, exc)


def fail_event(supabase: Any, event_id: str, error: str) -> None:
    """Mark an event as failed."""
    try:
        supabase.table("claw_events").update({
            "status": "failed",
            "result": {"error": error},
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", event_id).execute()
    except Exception as exc:
        logger.warning("Failed to fail event %s: %s", event_id, exc)


# ---------------------------------------------------------------------------
# Event emission helpers — called from skills after key actions
# ---------------------------------------------------------------------------

def on_hero_uploaded(supabase: Any, asset_id: str, guardian: str, storage_url: str) -> None:
    """Trigger when a hero-tier image is uploaded."""
    emit_event(supabase, "media.hero_uploaded", "media", {
        "asset_id": asset_id,
        "guardian": guardian,
        "storage_url": storage_url,
    })


def on_nft_minted(supabase: Any, nft_id: str, token_id: int, tx_hash: str, chain: str) -> None:
    """Trigger when an NFT is minted."""
    emit_event(supabase, "forge.nft_minted", "forge", {
        "nft_id": nft_id,
        "token_id": token_id,
        "tx_hash": tx_hash,
        "chain": chain,
    })


def on_alpha_detected(supabase: Any, signal_id: str, priority: str, content: str) -> None:
    """Trigger when Scout detects a high-value opportunity."""
    emit_event(supabase, "scout.alpha_detected", "scout", {
        "signal_id": signal_id,
        "priority": priority,
        "content": content[:500],
    })


def on_blog_ready(supabase: Any, title: str, slug: str, excerpt: str) -> None:
    """Trigger when Scribe finishes a blog draft."""
    emit_event(supabase, "scribe.blog_ready", "scribe", {
        "title": title,
        "slug": slug,
        "excerpt": excerpt,
    })
