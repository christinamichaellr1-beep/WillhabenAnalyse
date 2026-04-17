"""
Ollama-Aufrufe für Parser v2.0.
Fallback-Chain: gemma3:27b (format) → gemma4:26b (text) → gemma4:latest (text).
Retry via tenacity bei transienten Fehlern.
"""
import logging
import time

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_RETRY_EXCEPTIONS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)

from .schema import OLLAMA_FORMAT_SCHEMA

logger = logging.getLogger(__name__)

PRIMARY_MODEL   = "gemma3:27b"
FALLBACK_MODEL  = "gemma4:26b"
EMERGENCY_MODEL = "gemma4:latest"

CHAT_URL     = "http://localhost:11434/api/chat"
GENERATE_URL = "http://localhost:11434/api/generate"
TIMEOUT      = 240


def _duration_from_response(data: dict) -> int:
    """Extrahiert total_duration (Nanosekunden) und wandelt in ms um."""
    ns = data.get("total_duration", 0)
    return max(1, int(ns / 1_000_000))


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=10),
       retry=retry_if_exception_type(_RETRY_EXCEPTIONS),
       reraise=True)
def _call_chat(prompt: str, model: str) -> tuple[str, int]:
    """POST /api/chat mit format-Schema. Für gemma3:27b (Structured Output)."""
    resp = requests.post(
        CHAT_URL,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "format": OLLAMA_FORMAT_SCHEMA,
            "options": {"temperature": 0, "num_predict": 2048},
            "stream": False,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("message", {}).get("content", "")
    return content, _duration_from_response(data)


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=2, max=10),
       retry=retry_if_exception_type(_RETRY_EXCEPTIONS),
       reraise=True)
def _call_generate(prompt: str, model: str) -> tuple[str, int]:
    """POST /api/generate — Text-Modus für Fallback-Modelle."""
    resp = requests.post(
        GENERATE_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 2048},
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("response", "")
    return content, _duration_from_response(data)


def extract(
    prompt: str,
    model_override: str | None = None,
) -> tuple[str, str, int, bool]:
    """
    Führt den LLM-Aufruf durch.

    Fallback-Chain (ohne model_override):
      1. PRIMARY_MODEL   via /api/chat + format-Schema
      2. FALLBACK_MODEL  via /api/generate (Text-Modus)
      3. EMERGENCY_MODEL via /api/generate (Text-Modus)

    Gibt (raw_response, model_used, duration_ms, fallback_used) zurück.
    Bei vollständigem Ausfall: ("", EMERGENCY_MODEL, 0, True).
    """
    if model_override:
        try:
            if model_override == PRIMARY_MODEL:
                raw, ms = _call_chat(prompt, model_override)
            else:
                raw, ms = _call_generate(prompt, model_override)
            return raw, model_override, ms, False
        except Exception as exc:
            logger.error("model_override %s fehlgeschlagen: %s", model_override, exc)
            return "", model_override, 0, True

    # Primary: gemma3:27b mit Structured Output
    try:
        raw, ms = _call_chat(prompt, PRIMARY_MODEL)
        logger.debug("Primary model %s erfolgreich (%d ms)", PRIMARY_MODEL, ms)
        return raw, PRIMARY_MODEL, ms, False
    except Exception as exc:
        logger.warning("Primary %s fehlgeschlagen, Fallback: %s", PRIMARY_MODEL, exc)

    # Fallback: gemma4:26b Text-Modus (Thinking-Bug → kein format)
    try:
        raw, ms = _call_generate(prompt, FALLBACK_MODEL)
        logger.info("Fallback %s erfolgreich (%d ms)", FALLBACK_MODEL, ms)
        return raw, FALLBACK_MODEL, ms, True
    except Exception as exc:
        logger.warning("Fallback %s fehlgeschlagen, Emergency: %s", FALLBACK_MODEL, exc)

    # Emergency: gemma4:latest
    try:
        raw, ms = _call_generate(prompt, EMERGENCY_MODEL)
        logger.info("Emergency %s erfolgreich (%d ms)", EMERGENCY_MODEL, ms)
        return raw, EMERGENCY_MODEL, ms, True
    except Exception as exc:
        logger.error("Alle Modelle fehlgeschlagen: %s", exc)
        return "", EMERGENCY_MODEL, 0, True
