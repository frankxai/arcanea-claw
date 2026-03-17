"""
ArcaneaClaw Daemon — 24/7 media processing engine.

Runs two concurrent loops:
  1. Heartbeat — pings Supabase every N seconds to prove liveness
  2. Pipeline  — runs the full skill chain every M seconds:
     scan -> classify -> dedup -> process -> score -> upload -> social_prep -> notify

Also serves an HTTP health endpoint on port 8080.
"""

import asyncio
import importlib
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from aiohttp import web
from dotenv import load_dotenv

# Ensure engine package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import supabase_client as db

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("arcanea-claw")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = os.environ.get("ARCANEA_CLAW_CONFIG", "/app/config.yaml")


def load_config() -> dict[str, Any]:
    """Load and return config.yaml as a dict."""
    with open(CONFIG_PATH, "r") as f:
        raw = yaml.safe_load(f)
    return raw.get("arcanea_claw", raw)


# ---------------------------------------------------------------------------
# Skill chain — each skill is a module in /app/skills/ with a run() function
# ---------------------------------------------------------------------------

SKILL_CHAIN = [
    "media_scan",
    "media_classify",
    "media_dedup",
    "media_process",
    "taste_score",
    "media_upload",
    "social_prep",
    "notify",
]


async def run_skill(skill_name: str, config: dict) -> dict[str, Any]:
    """
    Import and execute a single skill module.

    Each skill lives at engine/skills/<name>.py and exposes an async run(config) -> dict.
    If the skill module doesn't exist yet, log a warning and skip.
    """
    module_path = f"engine.skills.{skill_name}"
    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError:
        logger.warning("Skill not implemented yet: %s — skipping", skill_name)
        return {"skill": skill_name, "status": "skipped", "reason": "not_implemented"}

    if not hasattr(mod, "run"):
        logger.warning("Skill %s has no run() function — skipping", skill_name)
        return {"skill": skill_name, "status": "skipped", "reason": "no_run_function"}

    start = time.monotonic()
    try:
        result = await mod.run(config)
        elapsed = round(time.monotonic() - start, 2)
        logger.info("Skill %s completed in %.2fs", skill_name, elapsed)
        return {
            "skill": skill_name,
            "status": "ok",
            "elapsed_s": elapsed,
            "result": result,
        }
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 2)
        logger.error("Skill %s failed after %.2fs: %s", skill_name, elapsed, exc, exc_info=True)
        return {
            "skill": skill_name,
            "status": "error",
            "elapsed_s": elapsed,
            "error": str(exc),
        }


async def run_pipeline(config: dict) -> list[dict]:
    """Execute the full skill chain sequentially, collecting results."""
    results: list[dict] = []
    for skill_name in SKILL_CHAIN:
        result = await run_skill(skill_name, config)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Health HTTP server
# ---------------------------------------------------------------------------

_daemon_state: dict[str, Any] = {
    "status": "starting",
    "started_at": None,
    "last_pipeline_at": None,
    "last_heartbeat_at": None,
    "pipeline_runs": 0,
    "errors": 0,
}


async def health_handler(_request: web.Request) -> web.Response:
    """GET /health — returns daemon state as JSON."""
    return web.json_response(_daemon_state)


async def start_health_server(port: int = 8080) -> web.AppRunner:
    """Start the aiohttp health endpoint."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health server listening on port %d", port)
    return runner


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------

async def heartbeat_loop(config: dict, shutdown_event: asyncio.Event) -> None:
    """Send heartbeat to Supabase at configured interval."""
    agent_id = config["agent_id"]
    interval = config.get("heartbeat", {}).get("interval_seconds", 300)

    while not shutdown_event.is_set():
        try:
            db.heartbeat(agent_id, stats=_daemon_state)
            _daemon_state["last_heartbeat_at"] = time.time()
        except Exception as exc:
            logger.error("Heartbeat failed: %s", exc)
            _daemon_state["errors"] += 1

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break  # shutdown requested
        except asyncio.TimeoutError:
            pass  # interval elapsed, loop again


async def pipeline_loop(config: dict, shutdown_event: asyncio.Event) -> None:
    """Run the full pipeline at configured interval."""
    agent_id = config["agent_id"]
    interval = config.get("heartbeat", {}).get("pipeline_interval_seconds", 900)

    while not shutdown_event.is_set():
        logger.info("--- Pipeline run #%d starting ---", _daemon_state["pipeline_runs"] + 1)
        db.update_agent_status(agent_id, "processing")

        results = await run_pipeline(config)

        _daemon_state["pipeline_runs"] += 1
        _daemon_state["last_pipeline_at"] = time.time()
        _daemon_state["last_pipeline_results"] = results

        error_count = sum(1 for r in results if r["status"] == "error")
        _daemon_state["errors"] += error_count

        db.update_agent_status(agent_id, "online")
        logger.info(
            "--- Pipeline run #%d complete (%d skills, %d errors) ---",
            _daemon_state["pipeline_runs"],
            len(results),
            error_count,
        )

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    config = load_config()
    agent_id = config["agent_id"]
    agent_name = config.get("agent_name", agent_id)

    logger.info("ArcaneaClaw starting — agent=%s", agent_id)

    # Register in Supabase
    try:
        db.register_agent(agent_id, agent_name, metadata={"version": "0.1.0"})
    except Exception as exc:
        logger.error("Failed to register agent (continuing anyway): %s", exc)

    _daemon_state["status"] = "online"
    _daemon_state["started_at"] = time.time()

    # Graceful shutdown via SIGTERM / SIGINT
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # Start health server
    health_runner = await start_health_server(port=8080)

    # Run heartbeat + pipeline concurrently
    try:
        await asyncio.gather(
            heartbeat_loop(config, shutdown_event),
            pipeline_loop(config, shutdown_event),
        )
    finally:
        # Graceful teardown
        logger.info("Shutting down ArcaneaClaw...")
        _daemon_state["status"] = "offline"
        try:
            db.update_agent_status(agent_id, "offline")
        except Exception as exc:
            logger.error("Failed to set offline status: %s", exc)
        await health_runner.cleanup()
        logger.info("ArcaneaClaw stopped.")


if __name__ == "__main__":
    asyncio.run(main())
