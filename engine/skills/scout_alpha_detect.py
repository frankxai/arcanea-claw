"""scout-alpha-detect skill: Detect high-value opportunities and alpha signals.

Analyzes collected signals for partnership opportunities, viral potential,
and strategic moves. Scores opportunities and flags urgent ones.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.scout-alpha-detect")


def run(config: dict[str, Any], supabase: Any, gemini_model: Any = None) -> dict[str, Any]:
    """Analyze signals for alpha opportunities."""
    alerts_cfg = config.get("alerts", {})
    viral_threshold = alerts_cfg.get("viral_threshold", 1000)

    # Get unprocessed high-engagement signals
    resp = (
        supabase.table("campaign_signals")
        .select("id, platform, content, engagement_score, signal_type, query")
        .eq("status", "new")
        .gte("engagement_score", 50)
        .order("engagement_score", desc=True)
        .limit(20)
        .execute()
    )
    signals = resp.data or []

    alphas_found = 0

    for signal in signals:
        score = signal.get("engagement_score", 0)
        is_viral = score >= viral_threshold
        is_competitor = signal.get("signal_type") == "competitor_activity"
        is_partnership = any(kw in (signal.get("content", "")).lower()
                           for kw in ["partnership", "collaboration", "integration", "arcanea"])

        # Score the opportunity
        opportunity_score = score
        if is_viral:
            opportunity_score *= 3
        if is_partnership:
            opportunity_score *= 5
        if is_competitor:
            opportunity_score *= 2

        priority = "low"
        if opportunity_score >= viral_threshold * 5:
            priority = "critical"
        elif opportunity_score >= viral_threshold:
            priority = "high"
        elif opportunity_score >= 100:
            priority = "medium"

        if priority in ("critical", "high"):
            try:
                supabase.table("campaign_signals").update({
                    "status": "alpha_detected",
                    "metadata": {
                        "opportunity_score": opportunity_score,
                        "priority": priority,
                        "is_viral": is_viral,
                        "is_partnership": is_partnership,
                        "is_competitor": is_competitor,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    },
                }).eq("id", signal["id"]).execute()
                alphas_found += 1
            except Exception as exc:
                logger.debug("Alpha update failed: %s", exc)

    logger.info("Detected %d alpha opportunities", alphas_found)
    return {"alphas_found": alphas_found}
