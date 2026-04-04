"""scout-sentiment-gauge skill: Analyze sentiment across collected signals.

Uses Gemini to classify signal sentiment and detect emerging narratives.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("arcanea-claw.scout-sentiment-gauge")

SENTIMENT_PROMPT = """Analyze the sentiment of these social media signals about AI creative tools and the creator economy.

Signals:
{signals_text}

For each signal, classify:
1. Sentiment: positive / neutral / negative
2. Relevance to Arcanea (AI world-building, creator tools): high / medium / low
3. Key theme in 3 words

Respond ONLY as JSON array:
[{{"id": "signal_id", "sentiment": "positive", "relevance": "high", "theme": "three word theme"}}]"""


def run(config: dict[str, Any], supabase: Any, gemini_model: Any = None) -> dict[str, Any]:
    """Gauge sentiment across recent signals."""
    if gemini_model is None:
        logger.info("Gemini not available — skipping sentiment analysis")
        return {"analyzed_count": 0}

    resp = (
        supabase.table("campaign_signals")
        .select("id, content, platform, query")
        .eq("status", "new")
        .order("detected_at", desc=True)
        .limit(20)
        .execute()
    )
    signals = resp.data or []

    if not signals:
        return {"analyzed_count": 0}

    # Batch analyze
    signals_text = "\n".join(
        f"[{s['id']}] ({s.get('platform','?')}) {s.get('content', '')[:200]}"
        for s in signals
    )

    try:
        response = gemini_model.generate_content(
            SENTIMENT_PROMPT.format(signals_text=signals_text)
        )
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        results = json.loads(text)
        analyzed = 0

        for result in results:
            signal_id = result.get("id", "")
            try:
                supabase.table("campaign_signals").update({
                    "metadata": {
                        "sentiment": result.get("sentiment", "neutral"),
                        "relevance": result.get("relevance", "low"),
                        "theme": result.get("theme", ""),
                    },
                }).eq("id", signal_id).execute()
                analyzed += 1
            except Exception:
                pass

        logger.info("Analyzed sentiment for %d signals", analyzed)
        return {"analyzed_count": analyzed}
    except Exception as exc:
        logger.warning("Sentiment analysis failed: %s", exc)
        return {"analyzed_count": 0}
