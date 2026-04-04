"""Maestro — Cross-claw strategy orchestrator.

Maestro doesn't have skills. It has STRATEGIES — declarative YAML workflows
that define when claws should coordinate. Maestro watches claw_events and
triggers multi-claw sequences when conditions are met.

Strategies:
  "Gallery Refresh"  = 3+ heroes uploaded → Herald showcases top picks
  "Build Log"        = Scribe changelog ready → Herald creates thread
  "Alpha Response"   = Scout detects high-priority signal → Herald drafts response
  "NFT Launch"       = Forge collection complete → Herald campaign + Scout monitoring
  "Content Week"     = Monday 9am → Scribe drafts 5 posts → Herald schedules all week

Maestro is NOT a separate daemon. It's a strategy evaluator that runs inside
the event_loop of any claw (or as its own profile).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("arcanea-claw.maestro")


# ---------------------------------------------------------------------------
# Strategy schema
# ---------------------------------------------------------------------------

BUILTIN_STRATEGIES: list[dict[str, Any]] = [
    {
        "name": "gallery_refresh",
        "description": "When 3+ hero images are uploaded, Herald showcases top picks",
        "trigger": {
            "event_type": "media.hero_uploaded",
            "accumulate": 3,  # wait for N events before firing
            "window_seconds": 3600,  # within this time window
        },
        "actions": [
            {"skill": "herald_content_draft", "params": {"topic": "New gallery additions — fresh art from the Arcanea universe"}},
            {"skill": "herald_schedule", "params": {"platform": "twitter"}},
        ],
        "cooldown_seconds": 7200,  # don't fire more than once per 2h
    },
    {
        "name": "build_log_thread",
        "description": "When Scribe finishes a changelog, Herald turns it into a thread",
        "trigger": {
            "event_type": "scribe.blog_ready",
            "accumulate": 1,
        },
        "actions": [
            {"skill": "herald_thread_compose", "params": {"template": "build_log"}},
            {"skill": "herald_schedule", "params": {}},
        ],
        "cooldown_seconds": 86400,  # once per day max
    },
    {
        "name": "alpha_response",
        "description": "When Scout detects a high-priority signal, Herald drafts a response",
        "trigger": {
            "event_type": "scout.alpha_detected",
            "accumulate": 1,
            "conditions": {"priority": "critical"},
        },
        "actions": [
            {"skill": "herald_content_draft", "params": {"topic": "Responding to emerging opportunity"}},
        ],
        "cooldown_seconds": 3600,
    },
    {
        "name": "nft_announcement",
        "description": "When Forge mints NFTs, Herald announces across platforms",
        "trigger": {
            "event_type": "forge.nft_minted",
            "accumulate": 1,
        },
        "actions": [
            {"skill": "herald_content_draft", "params": {"topic": "New NFT minted on Base — collector alert"}},
            {"skill": "herald_thread_compose", "params": {"template": "tech_deep_dive"}},
            {"skill": "herald_schedule", "params": {}},
        ],
        "cooldown_seconds": 1800,
    },
    {
        "name": "media_to_nft_evaluation",
        "description": "When hero art is uploaded, evaluate if it should become an NFT",
        "trigger": {
            "event_type": "media.hero_uploaded",
            "accumulate": 1,
            "conditions": {"quality_score_min": 90},
        },
        "actions": [
            {"skill": "nft_art_generate", "params": {"source": "hero_asset"}},
        ],
        "cooldown_seconds": 3600,
    },
]


# ---------------------------------------------------------------------------
# Strategy state tracking
# ---------------------------------------------------------------------------

class StrategyTracker:
    """Tracks event accumulation and cooldowns for strategies."""

    def __init__(self) -> None:
        self._event_buffers: dict[str, list[dict]] = {}  # strategy_name → events
        self._last_fired: dict[str, float] = {}  # strategy_name → timestamp

    def record_event(self, event: dict) -> None:
        """Add an event to all matching strategy buffers."""
        event_type = event.get("event_type", "")
        for strategy in _active_strategies:
            trigger = strategy.get("trigger", {})
            if trigger.get("event_type") == event_type:
                name = strategy["name"]
                self._event_buffers.setdefault(name, []).append({
                    "event": event,
                    "timestamp": time.monotonic(),
                })

    def check_triggers(self) -> list[dict]:
        """Check which strategies have met their trigger conditions. Returns strategies to fire."""
        now = time.monotonic()
        to_fire: list[dict] = []

        for strategy in _active_strategies:
            name = strategy["name"]
            trigger = strategy.get("trigger", {})
            accumulate = trigger.get("accumulate", 1)
            window = trigger.get("window_seconds", 3600)
            cooldown = strategy.get("cooldown_seconds", 0)

            # Check cooldown
            last = self._last_fired.get(name, 0)
            if now - last < cooldown:
                continue

            # Check accumulation
            buffer = self._event_buffers.get(name, [])
            # Filter to events within the window
            recent = [e for e in buffer if now - e["timestamp"] <= window]
            self._event_buffers[name] = recent  # prune old events

            if len(recent) >= accumulate:
                # Check conditions if any
                conditions = trigger.get("conditions", {})
                if conditions:
                    # Simple condition matching on event payload
                    match = True
                    for event_entry in recent:
                        payload = event_entry["event"].get("payload", {})
                        for key, value in conditions.items():
                            if key.endswith("_min"):
                                actual_key = key[:-4]
                                if payload.get(actual_key, 0) < value:
                                    match = False
                            elif payload.get(key) != value:
                                match = False
                    if not match:
                        continue

                to_fire.append(strategy)
                self._last_fired[name] = now
                self._event_buffers[name] = []  # clear buffer after firing

        return to_fire

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "active_strategies": len(_active_strategies),
            "buffers": {name: len(events) for name, events in self._event_buffers.items()},
            "last_fired": {
                name: round(time.monotonic() - ts)
                for name, ts in self._last_fired.items()
            },
        }


# ---------------------------------------------------------------------------
# Strategy loading
# ---------------------------------------------------------------------------

_active_strategies: list[dict] = []
_tracker = StrategyTracker()


def load_strategies(config: dict) -> list[dict]:
    """Load strategies from config, custom YAML files, and builtins."""
    global _active_strategies

    strategies = list(BUILTIN_STRATEGIES)

    # Load custom strategies from strategies/ directory
    strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
    if strategies_dir.exists():
        for yaml_file in strategies_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    custom = yaml.safe_load(f)
                if isinstance(custom, dict) and "name" in custom:
                    strategies.append(custom)
                    logger.info("Loaded custom strategy: %s", custom["name"])
                elif isinstance(custom, list):
                    strategies.extend(custom)
            except Exception as exc:
                logger.warning("Failed to load strategy %s: %s", yaml_file, exc)

    _active_strategies = strategies
    logger.info("Maestro loaded %d strategies", len(strategies))
    return strategies


def process_event(event: dict) -> list[dict]:
    """Process an event through Maestro's strategy engine.

    Returns list of strategies that should fire.
    """
    _tracker.record_event(event)
    return _tracker.check_triggers()


def get_actions_for_strategy(strategy: dict) -> list[dict]:
    """Get the skill actions for a triggered strategy."""
    return strategy.get("actions", [])


def get_tracker_stats() -> dict[str, Any]:
    """Get current strategy tracker state for /metrics."""
    return _tracker.stats
