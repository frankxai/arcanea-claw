"""ArcaneaClaw CLI — Fleet control from the command line.

Usage:
    arcanea-claw run [--profile media|forge|herald|scout|scribe]
    arcanea-claw trigger [skill_name]
    arcanea-claw status
    arcanea-claw fleet
    arcanea-claw skills [--profile media]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure engine is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_run(args: argparse.Namespace) -> None:
    """Run the daemon with the specified profile."""
    os.environ["CLAW_PROFILE"] = args.profile
    if args.interval:
        os.environ["PIPELINE_INTERVAL"] = str(args.interval)
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.json_logs:
        os.environ["LOG_FORMAT"] = "json"

    from engine.daemon import main
    asyncio.run(main())


def cmd_trigger(args: argparse.Namespace) -> None:
    """Trigger a pipeline run or specific skill via HTTP."""
    import requests

    port = args.port or 8080
    url = f"http://localhost:{port}/trigger"
    payload = {}
    if args.skill:
        payload["skill"] = args.skill

    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(json.dumps(resp.json(), indent=2))
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to daemon on port {port}. Is it running?")
        sys.exit(1)


def cmd_status(args: argparse.Namespace) -> None:
    """Get daemon health status."""
    import requests

    port = args.port or 8080
    try:
        resp = requests.get(f"http://localhost:{port}/health", timeout=5)
        data = resp.json()
        print(f"Status:    {data.get('status', 'unknown')}")
        print(f"Profile:   {data.get('profile', '?')}")
        print(f"Version:   {data.get('version', '?')}")
        print(f"Runs:      {data.get('pipeline_runs', 0)}")
        print(f"Errors:    {data.get('errors', 0)}")
        print(f"Uptime:    {data.get('uptime_s', 0)}s")

        circuits = data.get("circuits", [])
        if circuits:
            print(f"\nCircuit Breakers:")
            for cb in circuits:
                print(f"  {cb['name']:>12}: {cb['state']} ({cb['failures']} failures)")
    except requests.ConnectionError:
        print(f"OFFLINE — no daemon on port {port}")
        sys.exit(1)


def cmd_metrics(args: argparse.Namespace) -> None:
    """Get detailed metrics."""
    import requests

    port = args.port or 8080
    try:
        resp = requests.get(f"http://localhost:{port}/metrics", timeout=5)
        print(json.dumps(resp.json(), indent=2))
    except requests.ConnectionError:
        print(f"OFFLINE — no daemon on port {port}")
        sys.exit(1)


def cmd_fleet(args: argparse.Namespace) -> None:
    """Show fleet architecture and available profiles."""
    profiles = {
        "media": ("Media Engine", "scan → classify → dedup → process → score → upload → social → notify"),
        "forge": ("NFT Forge", "art gen → compose → metadata → IPFS → mint → marketplace → rarity"),
        "herald": ("PR & Social", "trend → draft → thread → schedule → post → engage → analytics"),
        "scout": ("Intelligence", "market → competitor → alpha → sentiment → report"),
        "scribe": ("Content Engine", "changelog → blog → newsletter → docs → distribute"),
    }

    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║              THE CLAW FLEET — ArcaneaClaw v0.3              ║")
    print("╠═══════════════════════════════════════════════════════════════╣")

    for name, (title, chain) in profiles.items():
        print(f"║  {name:>7} │ {title:<15} │ {chain[:40]:<40} ║")

    print("╠═══════════════════════════════════════════════════════════════╣")
    print("║  Run:  arcanea-claw run --profile forge                     ║")
    print("║  All:  docker compose up  (spins up all 5)                  ║")
    print("╚═══════════════════════════════════════════════════════════════╝")


def cmd_skills(args: argparse.Namespace) -> None:
    """List skills for a profile."""
    from engine.daemon import DEFAULT_CHAINS, load_config

    os.environ["CLAW_PROFILE"] = args.profile
    chain = DEFAULT_CHAINS.get(args.profile, [])
    print(f"Profile: {args.profile} ({len(chain)} skills)")
    print()
    for i, skill in enumerate(chain, 1):
        print(f"  {i:>2}. {skill}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="arcanea-claw",
        description="ArcaneaClaw — The Claw Fleet Engine",
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Start the daemon")
    p_run.add_argument("--profile", "-p", default="media", choices=["media", "forge", "herald", "scout", "scribe"])
    p_run.add_argument("--interval", type=int, help="Pipeline interval in seconds")
    p_run.add_argument("--port", type=int, default=8080, help="HTTP port")
    p_run.add_argument("--json-logs", action="store_true", help="JSON log output")

    # trigger
    p_trigger = sub.add_parser("trigger", help="Trigger pipeline or skill")
    p_trigger.add_argument("skill", nargs="?", help="Specific skill to trigger")
    p_trigger.add_argument("--port", type=int, default=8080)

    # status
    p_status = sub.add_parser("status", help="Daemon health status")
    p_status.add_argument("--port", type=int, default=8080)

    # metrics
    p_metrics = sub.add_parser("metrics", help="Detailed metrics")
    p_metrics.add_argument("--port", type=int, default=8080)

    # fleet
    sub.add_parser("fleet", help="Show fleet architecture")

    # skills
    p_skills = sub.add_parser("skills", help="List skills for a profile")
    p_skills.add_argument("--profile", "-p", default="media", choices=["media", "forge", "herald", "scout", "scribe"])

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "trigger": cmd_trigger,
        "status": cmd_status,
        "metrics": cmd_metrics,
        "fleet": cmd_fleet,
        "skills": cmd_skills,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
