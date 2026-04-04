"""LLM provider abstraction — decouple skills from Gemini.

Skills call llm.generate() and llm.generate_with_image(). The provider
is resolved from config: gemini, claude, or local (ollama).

This prevents the "Gemini key expired = 60% of fleet disabled" problem.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from engine.resilience import get_circuit, get_limiter

logger = logging.getLogger("arcanea-claw.llm")

_provider: str = "gemini"
_model: Any = None
_initialized: bool = False


def init(config: dict) -> str:
    """Initialize the LLM provider from config. Returns provider name."""
    global _provider, _model, _initialized

    # Check config for provider preference
    _provider = config.get("llm", {}).get("provider", "gemini")

    if _provider == "gemini":
        _model = _init_gemini(config)
    elif _provider == "claude":
        _model = _init_claude(config)
    elif _provider == "ollama":
        _model = _init_ollama(config)
    else:
        # Auto-detect: try Gemini first, then Claude, then Ollama
        _model = _init_gemini(config)
        if _model:
            _provider = "gemini"
        else:
            _model = _init_claude(config)
            if _model:
                _provider = "claude"
            else:
                logger.warning("No LLM provider available — AI skills will be limited")
                _provider = "none"

    _initialized = True
    return _provider


def _init_gemini(config: dict) -> Any:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model_name = config.get("classify", {}).get("model", "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)
        logger.info("LLM: Gemini (%s)", model_name)
        return model
    except Exception as exc:
        logger.warning("Gemini init failed: %s", exc)
        return None


def _init_claude(config: dict) -> Any:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        logger.info("LLM: Claude (claude-sonnet-4-20250514)")
        return client
    except Exception as exc:
        logger.warning("Claude init failed: %s", exc)
        return None


def _init_ollama(config: dict) -> Any:
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    try:
        import requests
        resp = requests.get(f"{url}/api/tags", timeout=3)
        if resp.status_code == 200:
            logger.info("LLM: Ollama (%s)", url)
            return {"url": url, "model": config.get("llm", {}).get("ollama_model", "llama3.2")}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Unified generation interface
# ---------------------------------------------------------------------------

def generate(prompt: str, max_tokens: int = 2048) -> str | None:
    """Generate text from prompt. Returns response text or None."""
    if not _model:
        return None

    circuit = get_circuit("llm", failure_threshold=3, reset_timeout=120)
    limiter = get_limiter("llm", rate=15, per=60)

    if not circuit.can_execute():
        return None
    if not limiter.acquire():
        logger.debug("LLM rate limited")
        return None

    try:
        if _provider == "gemini":
            resp = _model.generate_content(prompt)
            circuit.record_success()
            return resp.text
        elif _provider == "claude":
            resp = _model.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            circuit.record_success()
            return resp.content[0].text
        elif _provider == "ollama":
            import requests
            resp = requests.post(
                f"{_model['url']}/api/generate",
                json={"model": _model["model"], "prompt": prompt, "stream": False},
                timeout=60,
            )
            circuit.record_success()
            return resp.json().get("response", "")
    except Exception as exc:
        circuit.record_failure()
        logger.warning("LLM generate failed (%s): %s", _provider, exc)
        return None


def generate_with_image(prompt: str, image_path: str, mime_type: str = "image/png") -> str | None:
    """Generate text from prompt + image (vision). Returns response text or None."""
    if not _model:
        return None

    circuit = get_circuit("llm", failure_threshold=3, reset_timeout=120)
    limiter = get_limiter("llm", rate=15, per=60)

    if not circuit.can_execute() or not limiter.acquire():
        return None

    try:
        image_data = Path(image_path).read_bytes()
        encoded = base64.b64encode(image_data).decode("utf-8")

        if _provider == "gemini":
            resp = _model.generate_content([
                prompt,
                {"mime_type": mime_type, "data": encoded},
            ])
            circuit.record_success()
            return resp.text
        elif _provider == "claude":
            resp = _model.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": encoded}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            circuit.record_success()
            return resp.content[0].text
        elif _provider == "ollama":
            import requests
            resp = requests.post(
                f"{_model['url']}/api/generate",
                json={"model": _model["model"], "prompt": prompt, "images": [encoded], "stream": False},
                timeout=120,
            )
            circuit.record_success()
            return resp.json().get("response", "")
    except Exception as exc:
        circuit.record_failure()
        logger.warning("LLM vision failed (%s): %s", _provider, exc)
        return None


def parse_json_response(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


@property
def provider() -> str:
    return _provider


@property
def is_available() -> bool:
    return _model is not None
