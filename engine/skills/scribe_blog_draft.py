"""scribe-blog-draft skill: AI-generate blog posts from changelog and project updates.

Takes changelog entries and creates polished blog drafts in the FrankX voice.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("arcanea-claw.scribe-blog-draft")

BLOG_PROMPT = """Write a blog post for arcanea.ai based on these recent updates:

{changelog_summary}

{voice_guidelines}

Requirements:
- Title: catchy, specific, not clickbait
- Length: 500-1500 words
- Structure: intro hook, what shipped, why it matters, what's next
- Include code snippets or technical details where relevant
- End with a call to action

Respond ONLY as JSON:
{{"title": "Post Title", "slug": "post-slug", "excerpt": "2-sentence summary", "body": "Full markdown body", "tags": ["tag1", "tag2"]}}"""


def run(
    config: dict[str, Any],
    supabase: Any,
    gemini_model: Any = None,
    pipeline_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate blog drafts from changelog entries."""
    content_cfg = config.get("content", {})
    voice = content_cfg.get("voice", "")
    stats = pipeline_stats or {}
    entries = stats.get("changelog_entries", [])

    if not entries:
        logger.info("No changelog entries to draft from")
        return {"drafts_created": 0}

    if gemini_model is None:
        logger.warning("Gemini not available — skipping blog draft")
        return {"drafts_created": 0}

    # Group entries by category
    features = [e for e in entries if e["category"] == "feature"]
    fixes = [e for e in entries if e["category"] == "fix"]

    if not features and not fixes:
        logger.info("No features or fixes to blog about")
        return {"drafts_created": 0}

    summary = "**Features:**\n"
    for f in features[:10]:
        summary += f"- {f['message']} ({f['repo']}, {f['sha']})\n"
    summary += "\n**Fixes:**\n"
    for f in fixes[:10]:
        summary += f"- {f['message']} ({f['repo']}, {f['sha']})\n"

    prompt = BLOG_PROMPT.format(changelog_summary=summary, voice_guidelines=voice)

    try:
        response = gemini_model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        draft = json.loads(text)
        logger.info("Blog draft created: %s", draft.get("title", ""))
        return {"drafts_created": 1, "blog_draft": draft}
    except Exception as exc:
        logger.warning("Blog draft generation failed: %s", exc)
        return {"drafts_created": 0}
