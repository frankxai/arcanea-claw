"""
ArcaneaClaw Daemon — The Claw Fleet Engine.

One daemon, many profiles. Runs any claw type (Media, Forge, Herald, Scout, Scribe)
based on CLAW_PROFILE env var and config-driven skill chains.

Three concurrent loops:
  1. Heartbeat — pings Supabase to prove liveness
  2. Pipeline  — runs the skill chain at configured interval
  3. Events    — consumes cross-claw events and triggers actions

HTTP endpoints:
  GET /health  — daemon state + circuit breaker status
  GET /metrics — pipeline timing, skill stats, error rates
"""

from __future__ import annotations

import asyncio
import functools
import importlib
import inspect
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from aiohttp import web
from dotenv import load_dotenv

# Ensure engine package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import supabase_client as db
from engine.logging_config import setup_logging
from engine.resilience import (
    CircuitBreaker,
    RateLimiter,
    all_circuit_stats,
    all_limiter_stats,
    get_circuit,
    get_limiter,
)
from engine.security import (
    auth_middleware,
    check_auth_configured,
    configure_pillow_limits,
    install_log_redaction,
    rate_limit_middleware,
    safe_error_response,
    validate_skill_name,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Logging — structured JSON for cloud, human-readable for local
# ---------------------------------------------------------------------------

import logging

setup_logging()
logger = logging.getLogger("arcanea-claw")

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# Gemini model (lazy init with circuit breaker)
# ---------------------------------------------------------------------------

_gemini_model: Any = None
_gemini_circuit = get_circuit("gemini", failure_threshold=3, reset_timeout=120)
_gemini_limiter = get_limiter("gemini", rate=15, per=60)  # 15 RPM


def get_gemini_model(config: dict) -> Any:
    """Initialize and return a Gemini GenerativeModel, or None if unavailable."""
    global _gemini_model
    if _gemini_model is not None:
        return _gemini_model

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — AI classification/scoring disabled")
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model_name = config.get("classify", {}).get("model", "gemini-2.0-flash")
        _gemini_model = genai.GenerativeModel(model_name)
        logger.info("Gemini model initialized: %s", model_name)
        return _gemini_model
    except Exception as exc:
        logger.error("Failed to initialize Gemini: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Config — profile-based
# ---------------------------------------------------------------------------

CLAW_PROFILE = os.environ.get("CLAW_PROFILE", "media")


def load_config() -> dict[str, Any]:
    """Load config from profile YAML or env override."""
    # Priority: ARCANEA_CLAW_CONFIG env > profiles/<profile>.yaml > config.local.yaml > config.yaml
    explicit = os.environ.get("ARCANEA_CLAW_CONFIG")
    candidates = []

    if explicit:
        candidates.append(Path(explicit))

    base_dir = Path(__file__).resolve().parent.parent
    candidates.extend([
        base_dir / "profiles" / f"{CLAW_PROFILE}.yaml",
        Path(f"/app/profiles/{CLAW_PROFILE}.yaml"),
        base_dir / "config.local.yaml",
        base_dir / "config.yaml",
        Path("/app/config.yaml"),
    ])

    config_path = None
    for candidate in candidates:
        if candidate.exists():
            config_path = candidate
            break

    if config_path is None:
        raise FileNotFoundError(f"No config found for profile '{CLAW_PROFILE}'. Tried: {[str(c) for c in candidates]}")

    logger.info("Config loaded: %s (profile=%s)", config_path, CLAW_PROFILE)
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    return raw.get("arcanea_claw", raw)


# ---------------------------------------------------------------------------
# Default skill chains (per profile)
# ---------------------------------------------------------------------------

DEFAULT_CHAINS: dict[str, list[str]] = {
    "media": ["media_scan", "media_classify", "media_dedup", "media_process", "taste_score", "media_upload", "social_prep", "notify"],
    "forge": ["nft_art_generate", "nft_trait_compose", "nft_metadata_build", "nft_ipfs_pin", "nft_mint", "nft_marketplace_list", "nft_rarity_score", "notify"],
    "herald": ["herald_trend_scan", "herald_content_draft", "herald_thread_compose", "herald_schedule", "herald_cross_post", "herald_engage", "herald_analytics", "notify"],
    "scout": ["scout_market_scan", "scout_competitor_track", "scout_alpha_detect", "scout_sentiment_gauge", "scout_report_generate", "notify"],
    "scribe": ["scribe_changelog_scan", "scribe_blog_draft", "scribe_newsletter_compose", "scribe_docs_update", "scribe_distribute", "notify"],
}


# ---------------------------------------------------------------------------
# Skill runner with resilience
# ---------------------------------------------------------------------------

async def run_skill(
    skill_name: str,
    config: dict,
    supabase: Any,
    gemini_model: Any = None,
    pipeline_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Import and execute a single skill with resilience wrappers."""
    # CRIT-03: Validate against allowlist before importing
    if not validate_skill_name(skill_name):
        return {"skill": skill_name, "status": "blocked", "reason": "not_in_allowlist"}

    module_path = f"engine.skills.{skill_name}"
    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError:
        logger.warning("Skill not found: %s — skipping", skill_name)
        return {"skill": skill_name, "status": "skipped", "reason": "not_found"}

    if not hasattr(mod, "run"):
        logger.warning("Skill %s missing run() — skipping", skill_name)
        return {"skill": skill_name, "status": "skipped", "reason": "no_run_function"}

    # Dynamic kwarg injection
    sig = inspect.signature(mod.run)
    kwargs: dict[str, Any] = {"config": config}
    if "supabase" in sig.parameters:
        kwargs["supabase"] = supabase
    if "gemini_model" in sig.parameters:
        kwargs["gemini_model"] = gemini_model
    if "pipeline_stats" in sig.parameters:
        kwargs["pipeline_stats"] = pipeline_stats

    start = time.monotonic()
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None, functools.partial(mod.run, **kwargs)
        )
        elapsed_ms = round((time.monotonic() - start) * 1000)
        _metrics["skill_runs"][skill_name] = _metrics["skill_runs"].get(skill_name, 0) + 1
        _metrics["skill_timing"][skill_name] = elapsed_ms
        logger.info("%-25s %6dms  OK", skill_name, elapsed_ms)
        return {"skill": skill_name, "status": "ok", "elapsed_ms": elapsed_ms, "result": result}
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000)
        _metrics["skill_errors"][skill_name] = _metrics["skill_errors"].get(skill_name, 0) + 1
        logger.error("%-25s %6dms  FAIL: %s", skill_name, elapsed_ms, exc, exc_info=True)
        return {"skill": skill_name, "status": "error", "elapsed_ms": elapsed_ms, "error": str(exc)}


async def run_pipeline(config: dict, supabase: Any, gemini_model: Any = None) -> list[dict]:
    """Execute skill chain, aggregate stats, emit cross-claw events."""
    skill_chain = config.get("skill_chain", DEFAULT_CHAINS.get(CLAW_PROFILE, DEFAULT_CHAINS["media"]))
    results: list[dict] = []
    aggregated_stats: dict[str, Any] = {}

    pipeline_start = time.monotonic()
    logger.info("Pipeline starting: %d skills [%s]", len(skill_chain), CLAW_PROFILE)

    for skill_name in skill_chain:
        result = await run_skill(skill_name, config, supabase, gemini_model, pipeline_stats=aggregated_stats)
        results.append(result)
        if result.get("status") == "ok" and isinstance(result.get("result"), dict):
            aggregated_stats.update(result["result"])

    elapsed_ms = round((time.monotonic() - pipeline_start) * 1000)
    ok_count = sum(1 for r in results if r["status"] == "ok")
    err_count = sum(1 for r in results if r["status"] == "error")
    skip_count = sum(1 for r in results if r["status"] == "skipped")

    logger.info(
        "Pipeline complete: %dms total | %d ok, %d errors, %d skipped",
        elapsed_ms, ok_count, err_count, skip_count,
    )
    _metrics["pipeline_timing"].append(elapsed_ms)
    if len(_metrics["pipeline_timing"]) > 100:
        _metrics["pipeline_timing"] = _metrics["pipeline_timing"][-50:]

    # Emit cross-claw events based on results
    _emit_pipeline_events(supabase, aggregated_stats)

    return results


def _emit_pipeline_events(supabase: Any, stats: dict[str, Any]) -> None:
    """Emit cross-claw events from pipeline results."""
    try:
        from engine.events import on_hero_uploaded, on_nft_minted, on_alpha_detected, on_blog_ready

        # Media → Herald: new hero uploaded
        hero_count = stats.get("hero_count", 0)
        if hero_count > 0 and CLAW_PROFILE == "media":
            on_hero_uploaded(supabase, asset_id="batch", guardian="multiple", storage_url="batch")

        # Forge → Herald: NFT minted
        minted = stats.get("minted_count", 0)
        if minted > 0 and CLAW_PROFILE == "forge":
            on_nft_minted(supabase, nft_id="batch", token_id=0, tx_hash="batch", chain="base")

        # Scout → Herald: alpha detected
        alphas = stats.get("alphas_found", 0)
        if alphas > 0 and CLAW_PROFILE == "scout":
            on_alpha_detected(supabase, signal_id="batch", priority="high", content="Alpha batch detected")

        # Scribe → Herald: blog ready
        if stats.get("drafts_created", 0) > 0 and CLAW_PROFILE == "scribe":
            draft = stats.get("blog_draft", {})
            if draft:
                on_blog_ready(supabase, title=draft.get("title", ""), slug=draft.get("slug", ""), excerpt=draft.get("excerpt", ""))

    except Exception as exc:
        logger.debug("Event emission failed (non-critical): %s", exc)


# ---------------------------------------------------------------------------
# Event consumer — processes cross-claw events
# ---------------------------------------------------------------------------

async def event_loop(
    config: dict,
    shutdown_event: asyncio.Event,
    supabase: Any,
    gemini_model: Any = None,
) -> None:
    """Consume and process cross-claw events targeted at this claw."""
    claw_name = CLAW_PROFILE
    interval = 30  # check every 30s

    # Map event actions to skill runs
    ACTION_SKILLS: dict[str, list[str]] = {
        "draft_announcement": ["herald_content_draft"],
        "draft_pipeline_summary": ["herald_content_draft"],
        "announce_mint": ["herald_content_draft", "herald_schedule"],
        "launch_campaign": ["herald_content_draft", "herald_thread_compose", "herald_schedule"],
        "draft_alpha_response": ["herald_content_draft"],
        "thread_and_distribute": ["herald_thread_compose", "herald_schedule"],
        "evaluate_for_nft": ["nft_art_generate"],
        "draft_comparison": ["scribe_blog_draft"],
    }

    # Initialize Maestro strategies
    try:
        from engine.maestro import load_strategies, process_event, get_actions_for_strategy
        load_strategies(config)
        maestro_enabled = True
    except Exception as exc:
        logger.warning("Maestro init failed: %s", exc)
        maestro_enabled = False

    while not shutdown_event.is_set():
        try:
            from engine.events import consume_events, complete_event, fail_event

            events = consume_events(supabase, claw_name, limit=5)
            for event in events:
                action = event.get("action", "")
                skills_to_run = ACTION_SKILLS.get(action, [])

                # Feed event to Maestro for strategy evaluation
                if maestro_enabled:
                    triggered_strategies = process_event(event)
                    for strategy in triggered_strategies:
                        logger.info("Maestro strategy fired: %s", strategy["name"])
                        strategy_actions = get_actions_for_strategy(strategy)
                        for sa in strategy_actions:
                            skill_name = sa.get("skill", "")
                            if skill_name and skill_name not in skills_to_run:
                                skills_to_run.append(skill_name)
                        _daemon_state["events_processed"] += 1

                if not skills_to_run:
                    complete_event(supabase, event["id"], {"skipped": "no_skill_mapping"})
                    continue

                logger.info("Processing event: %s -> %s (%d skills)",
                           event.get("event_type"), action, len(skills_to_run))

                # Run the triggered skills
                event_stats: dict[str, Any] = {"event_payload": event.get("payload", {})}
                for skill_name in skills_to_run:
                    result = await run_skill(skill_name, config, supabase, gemini_model, pipeline_stats=event_stats)
                    if result.get("status") == "ok" and isinstance(result.get("result"), dict):
                        event_stats.update(result["result"])

                complete_event(supabase, event["id"], event_stats)

        except Exception as exc:
            logger.debug("Event consumer error: %s", exc)

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# Hermes message bus event consumer
# ---------------------------------------------------------------------------

async def hermes_loop(
    config: dict,
    shutdown_event: asyncio.Event,
    supabase: Any,
    gemini_model: Any = None,
) -> None:
    """Real-time event processing loop via Hermes TCP Message Bus."""
    # Only load if config does not disable it
    if config.get("hermes", {}).get("enabled", True) is False:
        logger.info("Hermes client disabled in config")
        return

    from engine.hermes import get_client
    from engine.events import EVENT_TRIGGERS, complete_event
    
    # Map event actions to skill runs
    ACTION_SKILLS: dict[str, list[str]] = {
        "draft_announcement": ["herald_content_draft"],
        "draft_pipeline_summary": ["herald_content_draft"],
        "announce_mint": ["herald_content_draft", "herald_schedule"],
        "launch_campaign": ["herald_content_draft", "herald_thread_compose", "herald_schedule"],
        "draft_alpha_response": ["herald_content_draft"],
        "thread_and_distribute": ["herald_thread_compose", "herald_schedule"],
        "evaluate_for_nft": ["nft_art_generate"],
        "draft_comparison": ["scribe_blog_draft"],
    }

    # Initialize Maestro strategies
    try:
        from engine.maestro import process_event, get_actions_for_strategy
        maestro_enabled = True
    except Exception as exc:
        logger.warning("Maestro init failed for Hermes loop: %s", exc)
        maestro_enabled = False

    claw_name = CLAW_PROFILE
    client = get_client(
        host=config.get("hermes", {}).get("host", "127.0.0.1"),
        port=config.get("hermes", {}).get("port", 8520)
    )

    async def event_handler(message: dict[str, Any]) -> None:
        event = message.get("payload", {})
        event_id = event.get("id")
        action = event.get("action", "")
        skills_to_run = list(ACTION_SKILLS.get(action, []))

        # Check-and-set status to prevent duplicate execution with Supabase polling
        if event_id:
            try:
                resp = supabase.table("claw_events").update({"status": "processing"}).eq("id", event_id).eq("status", "pending").execute()
                if not resp.data:
                    logger.debug("Hermes event %s already processed/processing, skipping", event_id)
                    return
            except Exception as exc:
                logger.warning("Failed to atomically mark event %s as processing: %s", event_id, exc)

        # Feed event to Maestro for strategy evaluation
        if maestro_enabled:
            triggered_strategies = process_event(event)
            for strategy in triggered_strategies:
                logger.info("Maestro strategy fired via Hermes: %s", strategy["name"])
                strategy_actions = get_actions_for_strategy(strategy)
                for sa in strategy_actions:
                    skill_name = sa.get("skill", "")
                    if skill_name and skill_name not in skills_to_run:
                        skills_to_run.append(skill_name)
                _daemon_state["events_processed"] += 1

        if not skills_to_run:
            if event_id:
                complete_event(supabase, event_id, {"skipped": "no_skill_mapping"})
            return

        logger.info("Processing Hermes event: %s -> %s (%d skills)",
                    event.get("event_type"), action, len(skills_to_run))

        # Run the triggered skills
        event_stats: dict[str, Any] = {"event_payload": event.get("payload", {})}
        for skill_name in skills_to_run:
            result = await run_skill(skill_name, config, supabase, gemini_model, pipeline_stats=event_stats)
            if result.get("status") == "ok" and isinstance(result.get("result"), dict):
                event_stats.update(result["result"])

        if event_id:
            complete_event(supabase, event_id, event_stats)
        _daemon_state["events_processed"] += 1

    # Subscribe to matching events
    for event_type, trigger in EVENT_TRIGGERS.items():
        if trigger["target_claw"] == claw_name:
            await client.subscribe(event_type, event_handler)

    # Start listen loop
    client.agent_id = f"{config['agent_id']}-hermes"
    await client.listen_loop(shutdown_event)


# ---------------------------------------------------------------------------
# Metrics + Health HTTP server
# ---------------------------------------------------------------------------

_daemon_state: dict[str, Any] = {
    "status": "starting",
    "version": VERSION,
    "profile": CLAW_PROFILE,
    "started_at": None,
    "last_pipeline_at": None,
    "last_heartbeat_at": None,
    "pipeline_runs": 0,
    "events_processed": 0,
    "errors": 0,
}

_metrics: dict[str, Any] = {
    "skill_runs": {},
    "skill_errors": {},
    "skill_timing": {},  # last run ms
    "pipeline_timing": [],  # list of pipeline durations
}


async def health_handler(_request: web.Request) -> web.Response:
    """GET /health — daemon state + circuit breakers."""
    body = {
        **_daemon_state,
        "circuits": all_circuit_stats(),
        "rate_limiters": all_limiter_stats(),
        "uptime_s": round(time.time() - (_daemon_state.get("started_at") or time.time())),
    }
    return web.json_response(body)


async def metrics_handler(_request: web.Request) -> web.Response:
    """GET /metrics — pipeline timing, skill stats, error rates."""
    timings = _metrics["pipeline_timing"]
    # Maestro strategy stats
    try:
        from engine.maestro import get_tracker_stats
        maestro_stats = get_tracker_stats()
    except Exception:
        maestro_stats = {}

    body = {
        "profile": CLAW_PROFILE,
        "pipeline": {
            "total_runs": _daemon_state["pipeline_runs"],
            "avg_ms": round(sum(timings) / len(timings)) if timings else 0,
            "p95_ms": sorted(timings)[int(len(timings) * 0.95)] if len(timings) >= 2 else 0,
            "last_ms": timings[-1] if timings else 0,
        },
        "skills": {
            name: {
                "runs": _metrics["skill_runs"].get(name, 0),
                "errors": _metrics["skill_errors"].get(name, 0),
                "last_ms": _metrics["skill_timing"].get(name, 0),
                "error_rate": round(
                    _metrics["skill_errors"].get(name, 0) / max(_metrics["skill_runs"].get(name, 0), 1), 3
                ),
            }
            for name in set(list(_metrics["skill_runs"]) + list(_metrics["skill_errors"]))
        },
        "circuits": all_circuit_stats(),
        "maestro": maestro_stats,
    }
    return web.json_response(body)


async def trigger_handler(request: web.Request) -> web.Response:
    """POST /trigger — manually trigger a pipeline run or specific skill.

    Requires CLAW_API_SECRET bearer token (enforced by auth_middleware).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    skill = body.get("skill")
    if skill:
        if not validate_skill_name(skill):
            return web.json_response({"error": f"Unknown skill: {skill}"}, status=400)
        config = load_config()
        supabase = db.get_client()
        gemini = get_gemini_model(config)
        result = await run_skill(skill, config, supabase, gemini)
        # Sanitize error details before returning
        if result.get("status") == "error" and "error" in result:
            result = {**result, **safe_error_response(result["error"])}
        return web.json_response(result)
    else:
        return web.json_response({"queued": True, "message": "Pipeline trigger queued"})


async def start_http_server(port: int = 8080) -> web.AppRunner:
    """Start the HTTP server with security middleware."""
    app = web.Application(middlewares=[rate_limit_middleware, auth_middleware])
    app.router.add_get("/health", health_handler)
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_post("/trigger", trigger_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("HTTP server on port %d — /health /metrics /trigger", port)
    return runner


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------

async def heartbeat_loop(config: dict, shutdown_event: asyncio.Event) -> None:
    """Send heartbeat to Supabase at configured interval."""
    agent_id = config["agent_id"]
    interval = config.get("heartbeat", {}).get("interval_seconds", 300)
    supabase_circuit = get_circuit("supabase", failure_threshold=5, reset_timeout=60)

    while not shutdown_event.is_set():
        if supabase_circuit.can_execute():
            try:
                db.heartbeat(agent_id, stats=_daemon_state)
                _daemon_state["last_heartbeat_at"] = time.time()
                supabase_circuit.record_success()
            except Exception as exc:
                supabase_circuit.record_failure()
                logger.error("Heartbeat failed: %s", exc)
                _daemon_state["errors"] += 1
        else:
            logger.debug("Supabase circuit OPEN — skipping heartbeat")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass


async def pipeline_loop(
    config: dict,
    shutdown_event: asyncio.Event,
    supabase: Any,
    gemini_model: Any = None,
) -> None:
    """Run the full pipeline at configured interval."""
    agent_id = config["agent_id"]
    interval = config.get("heartbeat", {}).get("pipeline_interval_seconds", 900)

    # Skip auto-loop if interval is 0 (on-demand only, like Forge)
    if interval <= 0:
        logger.info("Pipeline interval=0 — on-demand mode (use /trigger)")
        await shutdown_event.wait()
        return

    while not shutdown_event.is_set():
        run_num = _daemon_state["pipeline_runs"] + 1
        logger.info("--- Pipeline run #%d ---", run_num)

        try:
            db.update_agent_status(agent_id, "processing")
        except Exception:
            pass

        results = await run_pipeline(config, supabase, gemini_model)

        _daemon_state["pipeline_runs"] += 1
        _daemon_state["last_pipeline_at"] = time.time()
        error_count = sum(1 for r in results if r["status"] == "error")
        _daemon_state["errors"] += error_count

        try:
            db.update_agent_status(agent_id, "online")
        except Exception:
            pass

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
    skill_chain = config.get("skill_chain", DEFAULT_CHAINS.get(CLAW_PROFILE, []))

    logger.info("=== ArcaneaClaw %s | %s ===", VERSION, CLAW_PROFILE.upper())
    logger.info("Agent: %s | Skills: %d in chain", agent_id, len(skill_chain))

    # Security initialization
    configure_pillow_limits()    # HIGH-04: decompression bomb protection
    install_log_redaction()      # MED-06: secret redaction in logs
    check_auth_configured()      # CRIT-01: warn if no API secret

    # Initialize shared dependencies
    supabase = db.get_client()
    gemini_model = get_gemini_model(config)

    # Register in Supabase
    try:
        db.register_agent(agent_id, agent_name, metadata={
            "version": VERSION,
            "profile": CLAW_PROFILE,
            "skill_chain": skill_chain,
        })
    except Exception as exc:
        logger.error("Agent registration failed (continuing): %s", exc)

    _daemon_state["status"] = "online"
    _daemon_state["started_at"] = time.time()
    _daemon_state["skill_chain"] = skill_chain

    # Graceful shutdown
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: _signal_handler())

    # Start HTTP server
    http_runner = await start_http_server(port=int(os.environ.get("PORT", 8080)))

    # Run all loops concurrently
    try:
        await asyncio.gather(
            heartbeat_loop(config, shutdown_event),
            pipeline_loop(config, shutdown_event, supabase, gemini_model),
            event_loop(config, shutdown_event, supabase, gemini_model),
            hermes_loop(config, shutdown_event, supabase, gemini_model),
        )
    finally:
        logger.info("Shutting down ArcaneaClaw...")
        _daemon_state["status"] = "offline"
        try:
            db.update_agent_status(agent_id, "offline")
        except Exception:
            pass
        await http_runner.cleanup()
        logger.info("ArcaneaClaw stopped.")


if __name__ == "__main__":
    asyncio.run(main())
