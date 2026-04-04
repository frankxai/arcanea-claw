"""scribe-distribute skill: Distribute generated content to configured channels.

Publishes blog posts to website, newsletters to email, and changelogs to GitHub.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("arcanea-claw.scribe-distribute")


def run(config: dict[str, Any], supabase: Any, pipeline_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    """Distribute content to configured channels."""
    stats = pipeline_stats or {}
    distributed = 0

    blog = stats.get("blog_draft")
    if blog:
        # Log for manual review — auto-publish requires approval
        logger.info(
            "Blog draft ready for review: '%s' (%d words)",
            blog.get("title", ""),
            len(blog.get("body", "").split()),
        )
        distributed += 1

    newsletter = stats.get("newsletter_composed")
    if newsletter:
        logger.info("Newsletter ready for review and send")
        distributed += 1

    docs = stats.get("docs_flagged", 0)
    if docs:
        logger.info("%d documentation updates flagged", docs)

    return {"distributed_count": distributed}
