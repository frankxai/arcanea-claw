"""ArcaneaClaw media pipeline skills.

Provides individual skill modules and a ``run_pipeline()`` function that
chains them in order: scan -> classify -> dedup -> process -> score ->
upload -> social_prep -> notify.

Each skill is isolated: one skill failing logs the error and the pipeline
continues with the next step.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from . import (
    media_classify,
    media_dedup,
    media_process,
    media_scan,
    media_upload,
    notify,
    social_prep,
    taste_score,
)

logger = logging.getLogger("arcanea-claw.pipeline")

__all__ = [
    "media_scan",
    "media_classify",
    "media_dedup",
    "media_process",
    "taste_score",
    "media_upload",
    "social_prep",
    "notify",
    "run_pipeline",
]

# Pipeline step definitions in execution order.
# Each tuple: (name, module, requires_gemini)
PIPELINE_STEPS: list[tuple[str, Any, bool]] = [
    ("media-scan", media_scan, False),
    ("media-classify", media_classify, True),
    ("media-dedup", media_dedup, False),
    ("media-process", media_process, False),
    ("taste-score", taste_score, True),
    ("media-upload", media_upload, False),
    ("social-prep", social_prep, True),
    ("notify", notify, False),
]


def run_pipeline(
    config: dict[str, Any],
    supabase: Any,
    gemini_model: Any = None,
) -> dict[str, Any]:
    """Execute the full ArcaneaClaw media pipeline.

    Runs all 8 skills in sequence. Each skill is wrapped in error handling
    so a failure in one step does not prevent subsequent steps from running.

    Args:
        config: Parsed config.yaml under ``arcanea_claw``.
        supabase: Authenticated Supabase client.
        gemini_model: Initialized ``google.generativeai.GenerativeModel``.
            Required for classify, taste-score, and social-prep steps.

    Returns:
        Aggregated stats dict from all pipeline steps, plus timing info.
    """
    pipeline_stats: dict[str, Any] = {}
    step_timings: dict[str, float] = {}
    errors: dict[str, str] = {}
    pipeline_start = time.monotonic()

    logger.info("Starting ArcaneaClaw media pipeline (%d steps)", len(PIPELINE_STEPS))

    for step_name, module, requires_gemini in PIPELINE_STEPS:
        step_start = time.monotonic()
        logger.info("Running step: %s", step_name)

        try:
            # Build kwargs based on what the skill needs
            kwargs: dict[str, Any] = {
                "config": config,
                "supabase": supabase,
            }

            if requires_gemini:
                kwargs["gemini_model"] = gemini_model

            # The notify step receives aggregated stats
            if step_name == "notify":
                kwargs["pipeline_stats"] = pipeline_stats

            result = module.run(**kwargs)
            if isinstance(result, dict):
                pipeline_stats.update(result)

            elapsed = time.monotonic() - step_start
            step_timings[step_name] = round(elapsed, 2)
            logger.info("Completed %s in %.2fs: %s", step_name, elapsed, result)

        except Exception as exc:
            elapsed = time.monotonic() - step_start
            step_timings[step_name] = round(elapsed, 2)
            errors[step_name] = str(exc)
            logger.error(
                "Step %s failed after %.2fs: %s",
                step_name,
                elapsed,
                exc,
                exc_info=True,
            )

    total_elapsed = time.monotonic() - pipeline_start
    pipeline_stats["_timings"] = step_timings
    pipeline_stats["_errors"] = errors
    pipeline_stats["_total_seconds"] = round(total_elapsed, 2)

    if errors:
        logger.warning(
            "Pipeline completed with %d error(s) in %.2fs: %s",
            len(errors),
            total_elapsed,
            list(errors.keys()),
        )
    else:
        logger.info("Pipeline completed successfully in %.2fs", total_elapsed)

    return pipeline_stats
