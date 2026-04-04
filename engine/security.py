"""Security hardening for ArcaneaClaw daemon.

Fixes:
  CRIT-01: /trigger authentication via CLAW_API_SECRET bearer token
  CRIT-03: Skill allowlist — only configured skills can be triggered
  CRIT-05: Path boundary enforcement for media_scan
  HIGH-01: Inbound HTTP rate limiting
  HIGH-04: Pillow decompression bomb protection
  MED-01: Error message sanitization (no internal details in HTTP responses)
  MED-06: Secret redaction in logs
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from aiohttp import web

logger = logging.getLogger("arcanea-claw.security")

# ---------------------------------------------------------------------------
# CRIT-01 + MED-02: API authentication middleware
# ---------------------------------------------------------------------------

_API_SECRET: str = os.environ.get("CLAW_API_SECRET", "")

# Public endpoints (no auth required) — only basic health
PUBLIC_PATHS = {"/health"}

# Endpoints requiring auth
PROTECTED_PATHS = {"/trigger", "/metrics"}


@web.middleware
async def auth_middleware(request: web.Request, handler: Any) -> web.Response:
    """Authenticate protected endpoints via Bearer token.

    Set CLAW_API_SECRET env var to enable. If not set, ALL endpoints
    are open (dev mode) but a warning is logged on startup.
    """
    path = request.path

    if path in PUBLIC_PATHS:
        return await handler(request)

    if _API_SECRET and path in PROTECTED_PATHS:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response(
                {"error": "Authentication required", "hint": "Set Authorization: Bearer <CLAW_API_SECRET>"},
                status=401,
            )
        token = auth_header[7:]
        if token != _API_SECRET:
            return web.json_response({"error": "Invalid token"}, status=403)

    return await handler(request)


def check_auth_configured() -> bool:
    """Check if API authentication is configured. Warn if not."""
    if not _API_SECRET:
        logger.warning(
            "SECURITY: CLAW_API_SECRET not set — /trigger and /metrics are UNAUTHENTICATED. "
            "Set CLAW_API_SECRET env var for production."
        )
        return False
    logger.info("API authentication enabled (CLAW_API_SECRET configured)")
    return True


# ---------------------------------------------------------------------------
# CRIT-03: Skill allowlist
# ---------------------------------------------------------------------------

# All known valid skill names
VALID_SKILLS: set[str] = {
    # Media
    "media_scan", "media_classify", "media_dedup", "media_process",
    "taste_score", "media_upload", "social_prep",
    # Forge
    "nft_art_generate", "nft_trait_compose", "nft_metadata_build",
    "nft_ipfs_pin", "nft_mint", "nft_marketplace_list", "nft_rarity_score",
    # Herald
    "herald_trend_scan", "herald_content_draft", "herald_thread_compose",
    "herald_schedule", "herald_cross_post", "herald_engage", "herald_analytics",
    # Scout
    "scout_market_scan", "scout_competitor_track", "scout_alpha_detect",
    "scout_sentiment_gauge", "scout_report_generate",
    # Scribe
    "scribe_changelog_scan", "scribe_blog_draft", "scribe_newsletter_compose",
    "scribe_docs_update", "scribe_distribute",
    # Shared
    "notify",
}


def validate_skill_name(skill_name: str) -> bool:
    """Check if a skill name is in the allowlist. Prevents arbitrary module loading."""
    if skill_name not in VALID_SKILLS:
        logger.warning("SECURITY: Blocked unauthorized skill execution: %s", skill_name)
        return False
    return True


# ---------------------------------------------------------------------------
# CRIT-05: Path boundary enforcement
# ---------------------------------------------------------------------------

ALLOWED_SCAN_ROOTS: set[str] = {"/data", "./demo-media", "/app"}


def validate_scan_path(path: str, allowed_roots: set[str] | None = None) -> bool:
    """Ensure scan path is within allowed boundaries."""
    roots = allowed_roots or ALLOWED_SCAN_ROOTS
    resolved = Path(path).resolve()

    for root in roots:
        root_resolved = Path(root).resolve()
        try:
            resolved.relative_to(root_resolved)
            return True
        except ValueError:
            continue

    # Also allow paths under the project directory
    project_dir = Path(__file__).resolve().parent.parent
    try:
        resolved.relative_to(project_dir)
        return True
    except ValueError:
        pass

    logger.warning("SECURITY: Blocked scan path outside allowed roots: %s", path)
    return False


def validate_file_path(filepath: str, allowed_dirs: list[str] | None = None) -> bool:
    """Validate a file path doesn't traverse outside allowed directories."""
    resolved = Path(filepath).resolve()
    dirs = allowed_dirs or ["/data", "./data", "/app"]

    for d in dirs:
        try:
            resolved.relative_to(Path(d).resolve())
            return True
        except ValueError:
            continue

    # Allow project-relative paths
    project_dir = Path(__file__).resolve().parent.parent
    try:
        resolved.relative_to(project_dir)
        return True
    except ValueError:
        pass

    return False


# ---------------------------------------------------------------------------
# HIGH-01: Inbound HTTP rate limiting
# ---------------------------------------------------------------------------

class InboundRateLimiter:
    """Simple per-IP rate limiter for HTTP endpoints."""

    def __init__(self, rate: int = 30, window: float = 60.0) -> None:
        self.rate = rate
        self.window = window
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.monotonic()
        reqs = self._requests[client_ip]
        # Prune old requests
        reqs[:] = [t for t in reqs if now - t < self.window]
        if len(reqs) >= self.rate:
            return False
        reqs.append(now)
        return True


_inbound_limiter = InboundRateLimiter(rate=30, window=60)


@web.middleware
async def rate_limit_middleware(request: web.Request, handler: Any) -> web.Response:
    """Rate limit inbound HTTP requests per client IP."""
    client_ip = request.remote or "unknown"
    if not _inbound_limiter.is_allowed(client_ip):
        return web.json_response(
            {"error": "Rate limited", "retry_after": 60},
            status=429,
        )
    return await handler(request)


# ---------------------------------------------------------------------------
# HIGH-04: Pillow decompression bomb protection
# ---------------------------------------------------------------------------

def configure_pillow_limits() -> None:
    """Set Pillow image processing limits to prevent decompression bombs."""
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = 50_000_000  # ~7000x7000 max
        logger.info("Pillow MAX_IMAGE_PIXELS set to 50M")
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# MED-01: Error sanitization for HTTP responses
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = re.compile(
    r"(sk-[a-zA-Z0-9_-]+|eyJ[a-zA-Z0-9_-]+|AIza[a-zA-Z0-9_-]+|sb_secret_[a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


def sanitize_error(error: str) -> str:
    """Remove potential secrets from error messages before returning to clients."""
    return _SECRET_PATTERNS.sub("[REDACTED]", error)


def safe_error_response(error: str) -> dict:
    """Return a safe error dict for HTTP responses."""
    return {
        "error": "Skill execution failed",
        "detail": sanitize_error(error)[:200],  # truncate long errors
    }


# ---------------------------------------------------------------------------
# MED-06: Log secret redaction filter
# ---------------------------------------------------------------------------

class SecretRedactFilter(logging.Filter):
    """Redact potential secrets from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = _SECRET_PATTERNS.sub("[REDACTED]", record.msg)
        return True


def install_log_redaction() -> None:
    """Install secret redaction filter on all loggers."""
    root = logging.getLogger()
    root.addFilter(SecretRedactFilter())
    logger.info("Log secret redaction filter installed")
