"""
Postprocessing für Parser v2.0.
parse_raw → validate → attach_metadata.
"""
import datetime
import json
import logging
import re
from typing import Any

from .schema import Confidence, Kategorie

logger = logging.getLogger(__name__)

EMPTY_EVENT: dict[str, Any] = {
    "event_name": None,
    "event_datum": None,
    "venue": None,
    "stadt": None,
    "kategorie": "Unbekannt",
    "anzahl_karten": None,
    "angebotspreis_gesamt": None,
    "preis_ist_pro_karte": None,
    "originalpreis_pro_karte": None,
    "confidence": "niedrig",
    "confidence_grund": "Parse-Fehler",
}

_VALID_CONFIDENCE = {c.value for c in Confidence}
_VALID_KATEGORIE  = {k.value for k in Kategorie}


def parse_raw(raw: str, used_format_schema: bool) -> list[dict]:
    """
    Parst die Ollama-Antwort in eine Liste von Event-Dicts.

    used_format_schema=True  → erwartet {"events": [...]} (Grammar-guaranteed)
    used_format_schema=False → Regex-Fallback-Kette (Text-Modus Fallback-Modelle)

    Gibt immer min. 1 Element zurück (EMPTY_EVENT als letzter Fallback).
    """
    if not raw or not raw.strip():
        fallback = dict(EMPTY_EVENT)
        fallback["confidence_grund"] = "Leere Antwort vom Modell"
        return [fallback]

    if used_format_schema:
        return _parse_structured(raw)
    else:
        return _parse_text(raw)


def _parse_structured(raw: str) -> list[dict]:
    """JSON mit {"events": [...]} Wrapper parsen."""
    try:
        data = json.loads(raw.strip())
        if isinstance(data, dict) and "events" in data:
            events = data["events"]
            if isinstance(events, list) and events:
                return events
        # Fallback: Top-Level Array oder einzelnes Object
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except Exception as exc:
        logger.warning("Structured-Output-Parse fehlgeschlagen: %s | raw: %.100s", exc, raw)

    fallback = dict(EMPTY_EVENT)
    fallback["confidence_grund"] = "Structured-Output-Parse-Fehler"
    return [fallback]


def _parse_text(raw: str) -> list[dict]:
    """Regex-Fallback für Text-Modus (gemma4-Modelle)."""
    raw = raw.strip()

    # Direkt parsen
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            events = parsed.get("events")
            if isinstance(events, list):
                return events
            return [parsed]
    except Exception:
        pass

    # JSON aus Markdown-Block
    m = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except Exception:
            pass

    # Erstes [...] im Text
    m = re.search(r"(\[.*?\])", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Erstes {...} im Text
    m = re.search(r"(\{.*?\})", raw, re.DOTALL)
    if m:
        try:
            return [json.loads(m.group(1))]
        except Exception:
            pass

    fallback = dict(EMPTY_EVENT)
    fallback["confidence_grund"] = "JSON-Extraktion fehlgeschlagen"
    return [fallback]


def validate(raw_events: list[dict]) -> list[dict]:
    """
    Pydantic-ähnliche Validierung ohne harten Crash:
    Ungültige Felder werden auf sichere Defaults gesetzt.
    """
    return [_validate_one(e) for e in raw_events]


def _validate_one(obj: Any) -> dict:
    if not isinstance(obj, dict):
        return dict(EMPTY_EVENT)

    result = dict(EMPTY_EVENT)
    result.update({k: v for k, v in obj.items() if k in EMPTY_EVENT})

    # Float-Felder
    for field in ("angebotspreis_gesamt", "originalpreis_pro_karte"):
        val = result[field]
        if val is not None:
            try:
                result[field] = float(val)
            except (ValueError, TypeError):
                result[field] = None

    # anzahl_karten
    val = result["anzahl_karten"]
    if val is not None:
        try:
            result["anzahl_karten"] = int(val)
        except (ValueError, TypeError):
            result["anzahl_karten"] = None

    # preis_ist_pro_karte normalisieren
    pipc = result["preis_ist_pro_karte"]
    if isinstance(pipc, str):
        if pipc.lower() in ("true", "ja", "yes"):
            result["preis_ist_pro_karte"] = True
        elif pipc.lower() in ("false", "nein", "no"):
            result["preis_ist_pro_karte"] = False
        else:
            result["preis_ist_pro_karte"] = None

    # confidence validieren
    if result["confidence"] not in _VALID_CONFIDENCE:
        result["confidence"] = "niedrig"

    # kategorie validieren
    if result["kategorie"] not in _VALID_KATEGORIE:
        result["kategorie"] = "Unbekannt"

    return result


def attach_metadata(
    events: list[dict],
    ad: dict,
    model_used: str,
    duration_ms: int,
    fallback_used: bool,
) -> list[dict]:
    """
    Hängt Willhaben-Metadaten und v2-Felder an jeden Event-Dict an.
    Gibt eine neue Liste zurück (keine Mutation des Inputs).
    """
    result = []
    for e in events:
        ev = dict(e)
        ev["willhaben_id"]      = ad.get("id", "")
        ev["willhaben_link"]    = ad.get("link", "")
        ev["verkäufertyp"]      = ad.get("verkäufertyp", "")
        ev["verkäufername"]     = ad.get("verkäufername", "")
        ev["verkäufer_id"]      = ad.get("verkäufer_id", "")
        ev["mitglied_seit"]     = ad.get("mitglied_seit", "")
        ev["preis_roh"]         = ad.get("preis_roh", "")
        ev["parsed_at"]         = datetime.datetime.now().isoformat()
        ev["modell"]            = model_used
        ev["pipeline_version"]  = "v2.0"
        ev["parse_dauer_ms"]    = duration_ms
        result.append(ev)
    return result
