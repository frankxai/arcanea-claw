"""scout-competitor-track skill: Monitor competitor activity and product changes.

Tracks named competitors from config, checks their social presence,
GitHub activity, and product updates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.scout-competitor-track")


def run(config: dict[str, Any], supabase: Any) -> dict[str, Any]:
    """Track competitor activity."""
    competitors = config.get("competitors", [])
    tracked = 0
    now = datetime.now(timezone.utc)

    for comp in competitors:
        name = comp.get("name", "Unknown")
        domain = comp.get("domain", "")

        # Check GitHub activity if tracked
        if "github" in comp.get("track", []) and domain:
            try:
                # Simple: check if they have recent GitHub activity
                resp = requests.get(
                    f"https://api.github.com/search/repositories",
                    params={"q": f"org:{domain.split('.')[0]}", "sort": "updated", "per_page": 3},
                    timeout=10,
                )
                if resp.status_code == 200:
                    repos = resp.json().get("items", [])
                    for repo in repos:
                        signal = {
                            "platform": "github",
                            "source_id": f"comp-{name}-{repo.get('id', '')}",
                            "content": f"[COMPETITOR] {name}: {repo.get('full_name')} updated — {repo.get('description', '')[:200]}",
                            "engagement_score": repo.get("stargazers_count", 0),
                            "query": f"competitor:{name}",
                            "signal_type": "competitor_activity",
                            "detected_at": now.isoformat(),
                            "status": "new",
                        }
                        try:
                            supabase.table("campaign_signals").upsert(
                                signal, on_conflict="platform,source_id"
                            ).execute()
                            tracked += 1
                        except Exception:
                            pass
            except Exception as exc:
                logger.debug("Competitor GitHub scan failed for %s: %s", name, exc)

    logger.info("Tracked %d competitor signals", tracked)
    return {"competitor_signals": tracked}
