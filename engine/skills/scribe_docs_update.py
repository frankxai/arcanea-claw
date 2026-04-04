"""scribe-docs-update skill: Auto-update documentation from code changes.

Detects when API routes, components, or configs change and flags
documentation that needs updating.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("arcanea-claw.scribe-docs-update")


def run(config: dict[str, Any], supabase: Any, pipeline_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    """Identify docs that need updating based on code changes."""
    stats = pipeline_stats or {}
    entries = stats.get("changelog_entries", [])

    docs_needed = []
    for entry in entries:
        msg = entry.get("message", "").lower()
        # Flag commits that likely need doc updates
        if any(kw in msg for kw in ["api", "route", "endpoint", "config", "schema", "breaking"]):
            docs_needed.append({
                "repo": entry.get("repo"),
                "commit": entry.get("sha"),
                "message": entry.get("message"),
                "reason": "API/config change detected",
            })

    logger.info("Found %d docs needing updates", len(docs_needed))
    return {"docs_flagged": len(docs_needed), "docs_needed": docs_needed}
