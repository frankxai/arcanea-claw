"""Structured JSON logging for production + human-readable for local dev.

Set LOG_FORMAT=json for Railway/CloudWatch. Default is human-readable.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for cloud environments."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }
        # Extra fields
        for key in ("skill", "claw_profile", "pipeline_run", "duration_ms", "event_type"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Clean human-readable formatter for local development."""

    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        name = record.name.replace("arcanea-claw.", "")
        return f"{ts} {color}{record.levelname:>7}{reset} [{name}] {record.getMessage()}"


def setup_logging(level: str = "INFO") -> None:
    """Configure logging based on LOG_FORMAT env var."""
    log_format = os.environ.get("LOG_FORMAT", "human").lower()
    log_level = getattr(logging, os.environ.get("LOG_LEVEL", level).upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(HumanFormatter())

    root.addHandler(handler)

    # Quiet noisy libraries
    for lib in ("httpx", "httpcore", "urllib3", "aiohttp.access"):
        logging.getLogger(lib).setLevel(logging.WARNING)
