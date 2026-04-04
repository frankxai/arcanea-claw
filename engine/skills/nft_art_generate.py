"""nft-art-generate skill: Generate NFT artwork via ComfyUI, Replicate, or local SD.

Pulls pending generation requests from nft_assets table, sends to the configured
art provider, and stores the resulting image paths.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("arcanea-claw.nft-art-generate")

GENERATION_PROMPT_TEMPLATE = """Create a unique character portrait for the Arcanea fantasy universe.

Style Pack: {style_pack}
Guardian Affinity: {guardian}
Element: {element}
Rarity: {rarity}
Traits: {traits}

Art direction:
- Dark fantasy aesthetic with luminous accents
- Rich detail, painterly quality, NOT generic AI art
- {guardian}-specific color palette and symbolism
- {rarity} tier: {"simple composition" if rarity == "common" else "complex, ornate composition with special effects" if rarity in ("epic", "legendary") else "balanced composition"}
"""


def _generate_comfyui(prompt: str, config: dict) -> str | None:
    """Generate via ComfyUI API. Returns local file path."""
    comfyui_url = os.environ.get("COMFYUI_URL", config.get("art", {}).get("comfyui_url", ""))
    if not comfyui_url:
        logger.warning("COMFYUI_URL not set — skipping ComfyUI generation")
        return None

    try:
        # Queue a prompt via ComfyUI API
        resp = requests.post(
            f"{comfyui_url}/prompt",
            json={"prompt": {"text": prompt}},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        prompt_id = data.get("prompt_id")

        # Poll for completion (max 2 min)
        for _ in range(24):
            time.sleep(5)
            status = requests.get(f"{comfyui_url}/history/{prompt_id}", timeout=10).json()
            if prompt_id in status and status[prompt_id].get("status", {}).get("completed"):
                outputs = status[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    images = node_output.get("images", [])
                    if images:
                        return images[0].get("filename")
                break

        return None
    except Exception as exc:
        logger.warning("ComfyUI generation failed: %s", exc)
        return None


def _generate_replicate(prompt: str, config: dict) -> str | None:
    """Generate via Replicate API. Returns downloaded file path."""
    token = os.environ.get("REPLICATE_TOKEN", "")
    if not token:
        logger.warning("REPLICATE_TOKEN not set — skipping Replicate generation")
        return None

    try:
        resp = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "version": "stability-ai/sdxl:latest",
                "input": {
                    "prompt": prompt,
                    "negative_prompt": "low quality, blurry, deformed, generic, clipart",
                    "width": config.get("art", {}).get("default_resolution", [1024, 1024])[0],
                    "height": config.get("art", {}).get("default_resolution", [1024, 1024])[1],
                    "num_outputs": 1,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        prediction = resp.json()
        prediction_url = prediction.get("urls", {}).get("get", "")

        # Poll for result
        for _ in range(60):
            time.sleep(3)
            poll = requests.get(prediction_url, headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
            if poll.get("status") == "succeeded":
                output_urls = poll.get("output", [])
                if output_urls:
                    # Download image
                    img_resp = requests.get(output_urls[0], timeout=30)
                    output_dir = Path("/data/nft-raw")
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_path = output_dir / f"gen_{int(time.time())}.png"
                    output_path.write_bytes(img_resp.content)
                    return str(output_path)
            elif poll.get("status") == "failed":
                logger.warning("Replicate prediction failed: %s", poll.get("error"))
                return None

        return None
    except Exception as exc:
        logger.warning("Replicate generation failed: %s", exc)
        return None


def run(config: dict[str, Any], supabase: Any, gemini_model: Any = None) -> dict[str, Any]:
    """Generate NFT artwork for pending requests.

    Reads from nft_assets where status='pending_generation', generates art,
    updates with the file path.
    """
    art_cfg = config.get("art", {})
    provider = art_cfg.get("provider", "replicate")
    batch_size = art_cfg.get("batch_size", 10)

    # Fetch pending generation requests
    resp = (
        supabase.table("nft_assets")
        .select("id, collection_id, token_id, traits, guardian, element, rarity, style_pack")
        .eq("status", "pending_generation")
        .limit(batch_size)
        .execute()
    )
    assets = resp.data or []

    if not assets:
        logger.info("No pending NFT art generation requests")
        return {"generated_count": 0}

    generated = 0

    for asset in assets:
        asset_id = asset["id"]
        traits = asset.get("traits", {})

        prompt = GENERATION_PROMPT_TEMPLATE.format(
            style_pack=asset.get("style_pack", "guardian_portraits"),
            guardian=asset.get("guardian", "Shinkami"),
            element=asset.get("element", "Void"),
            rarity=asset.get("rarity", "common"),
            traits=json.dumps(traits),
        )

        # Generate based on provider
        file_path = None
        if provider == "comfyui":
            file_path = _generate_comfyui(prompt, config)
        elif provider == "replicate":
            file_path = _generate_replicate(prompt, config)

        if file_path is None:
            logger.warning("Art generation failed for NFT %s", asset_id)
            supabase.table("nft_assets").update({"status": "generation_failed"}).eq("id", asset_id).execute()
            continue

        try:
            supabase.table("nft_assets").update({
                "image_path": file_path,
                "status": "generated",
            }).eq("id", asset_id).execute()
            generated += 1
        except Exception as exc:
            logger.warning("Failed to update NFT %s: %s", asset_id, exc)

    logger.info("Generated %d NFT artworks via %s", generated, provider)
    return {"generated_count": generated}
