"""scout-report-generate skill: Generate daily intelligence digest.

Synthesizes all signals into an actionable report sent via webhook.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.scout-report-generate")


def run(config: dict[str, Any], supabase: Any, pipeline_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate intelligence report from today's signals."""
    stats = pipeline_stats or {}

    report_lines = [
        f"**ArcaneaClaw Scout — Daily Intelligence Report**",
        f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"- Market signals: {stats.get('market_signals', 0)}",
        f"- Competitor signals: {stats.get('competitor_signals', 0)}",
        f"- Alpha opportunities: {stats.get('alphas_found', 0)}",
        f"- Sentiment analyzed: {stats.get('analyzed_count', 0)}",
        "",
    ]

    # Get top alpha signals
    resp = (
        supabase.table("campaign_signals")
        .select("content, platform, engagement_score, metadata")
        .eq("status", "alpha_detected")
        .order("engagement_score", desc=True)
        .limit(5)
        .execute()
    )
    alphas = resp.data or []

    if alphas:
        report_lines.append("**Top Alpha Signals:**")
        for i, alpha in enumerate(alphas, 1):
            meta = alpha.get("metadata") or {}
            report_lines.append(
                f"{i}. [{meta.get('priority', '?').upper()}] "
                f"({alpha.get('platform')}) {alpha.get('content', '')[:150]}"
            )
        report_lines.append("")

    report = "\n".join(report_lines)
    logger.info("Intelligence report generated (%d lines)", len(report_lines))

    return {"report_generated": True, "report_text": report}
