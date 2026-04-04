"""herald-thread-compose skill: Compose multi-tweet threads from long-form content.

Takes build logs, lore drops, or tech deep-dives and structures them as
engaging Twitter/X threads with proper hooks, pacing, and CTAs.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("arcanea-claw.herald-thread-compose")

THREAD_PROMPT = """You are composing a Twitter/X thread for Arcanea.

Template type: {template}
Source material: {source}

{voice_guidelines}

Rules for threads:
- Hook tweet MUST stop the scroll (question, bold claim, or surprising stat)
- 4-8 tweets max. Each tweet < 280 chars
- Use line breaks within tweets for readability
- End with a clear CTA (follow, try it, check link)
- NO emoji spam. Max 1 emoji per tweet if any
- Number tweets: 1/, 2/, etc.

Respond ONLY as JSON:
{{"tweets": ["tweet 1 text", "tweet 2 text", ...], "hook_type": "question|claim|stat|story"}}"""


def run(config: dict[str, Any], supabase: Any, gemini_model: Any = None) -> dict[str, Any]:
    """Compose threads from approved draft content or scheduled templates."""
    content_cfg = config.get("content", {})
    voice = content_cfg.get("voice_guidelines", "")
    templates = content_cfg.get("thread_templates", [])

    if gemini_model is None:
        logger.warning("Gemini not available — skipping thread composition")
        return {"threads_composed": 0}

    # Get drafts that are long enough for threads
    resp = (
        supabase.table("social_queue")
        .select("id, platform, content_text, hashtags")
        .eq("platform", "twitter")
        .eq("status", "draft")
        .execute()
    )
    drafts = resp.data or []

    # Filter: only drafts with enough content for a thread
    threadable = [d for d in drafts if len(d.get("content_text", "")) > 300]

    threads_composed = 0

    for draft in threadable[:3]:  # max 3 threads per cycle
        template = templates[threads_composed % len(templates)] if templates else "build_log"

        prompt = THREAD_PROMPT.format(
            template=template,
            source=draft.get("content_text", ""),
            voice_guidelines=voice,
        )

        try:
            response = gemini_model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines).strip()

            thread_data = json.loads(text)
            tweets = thread_data.get("tweets", [])

            if not tweets:
                continue

            # Store thread as a single social_queue entry with tweets in metadata
            supabase.table("social_queue").update({
                "content_text": tweets[0],  # Hook tweet as primary
                "hashtags": draft.get("hashtags", []),
                "status": "thread_ready",
            }).eq("id", draft["id"]).execute()

            threads_composed += 1
        except Exception as exc:
            logger.warning("Thread composition failed: %s", exc)

    logger.info("Composed %d threads", threads_composed)
    return {"threads_composed": threads_composed}
