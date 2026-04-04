"""
ArcaneaClaw — Supabase client and DB helpers.

Provides all database operations for the agent lifecycle:
registration, heartbeat, asset tracking, and publish pipeline.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("arcanea-claw.db")

_client: Optional[Client] = None


def get_client() -> Client:
    """Return singleton Supabase client, initialized from env vars."""
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------

def register_agent(agent_id: str, agent_name: str, metadata: dict | None = None) -> dict:
    """Register or update this agent in agent_registry on startup."""
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "agent_type": "arcanea-claw",
        "status": "online",
        "last_heartbeat": now,
        "config": metadata or {},
    }
    result = (
        client.table("agent_registry")
        .upsert(payload, on_conflict="agent_id")
        .execute()
    )
    logger.info("Agent registered: %s", agent_id)
    return result.data


def heartbeat(agent_id: str, stats: dict | None = None) -> None:
    """Update last_heartbeat timestamp and optional stats."""
    client = get_client()
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {"last_heartbeat": now}
    if stats:
        payload["config"] = stats
    client.table("agent_registry").update(payload).eq("agent_id", agent_id).execute()
    logger.debug("Heartbeat sent: %s", agent_id)


def update_agent_status(agent_id: str, status: str) -> None:
    """Set agent status (online, processing, offline, error)."""
    client = get_client()
    client.table("agent_registry").update({"status": status}).eq(
        "agent_id", agent_id
    ).execute()
    logger.info("Agent %s status -> %s", agent_id, status)


# ---------------------------------------------------------------------------
# Asset CRUD
# ---------------------------------------------------------------------------

def insert_asset(asset: dict) -> dict:
    """Insert a new asset record. Returns the inserted row."""
    client = get_client()
    result = client.table("asset_metadata").insert(asset).execute()
    return result.data[0] if result.data else {}


def update_asset(asset_id: str, updates: dict) -> dict:
    """Update fields on an existing asset."""
    client = get_client()
    result = (
        client.table("asset_metadata").update(updates).eq("id", asset_id).execute()
    )
    return result.data[0] if result.data else {}


def get_unclassified_assets(limit: int = 50) -> list[dict]:
    """Fetch assets that have not been classified yet."""
    client = get_client()
    result = (
        client.table("asset_metadata")
        .select("*")
        .is_("classified_at", "null")
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_unprocessed_assets(limit: int = 50) -> list[dict]:
    """Fetch assets that are classified but not yet processed into variants."""
    client = get_client()
    result = (
        client.table("asset_metadata")
        .select("*")
        .not_.is_("classified_at", "null")
        .is_("processed_at", "null")
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_unscored_assets(limit: int = 50) -> list[dict]:
    """Fetch assets that are processed but have no TASTE score."""
    client = get_client()
    result = (
        client.table("asset_metadata")
        .select("*")
        .not_.is_("processed_at", "null")
        .is_("taste_score", "null")
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_approved_for_upload(threshold: int = 60, limit: int = 50) -> list[dict]:
    """Fetch scored assets above threshold that haven't been uploaded."""
    client = get_client()
    result = (
        client.table("asset_metadata")
        .select("*")
        .gte("taste_score", threshold)
        .is_("uploaded_at", "null")
        .limit(limit)
        .execute()
    )
    return result.data or []


# ---------------------------------------------------------------------------
# Social & publish pipeline
# ---------------------------------------------------------------------------

def insert_social_queue(entry: dict) -> dict:
    """Add an item to the social_queue for cross-posting."""
    client = get_client()
    result = client.table("social_queue").insert(entry).execute()
    return result.data[0] if result.data else {}


def insert_publish_pipeline(entry: dict) -> dict:
    """Add an item to the publish_pipeline for final distribution."""
    client = get_client()
    result = client.table("publish_pipeline").insert(entry).execute()
    return result.data[0] if result.data else {}
