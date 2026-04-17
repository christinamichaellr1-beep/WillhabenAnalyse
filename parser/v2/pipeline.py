"""
Pipeline v2.0 — Drop-in-Ersatz für parser/gemma_parser.py.
Öffentliche API: parse_ad(), parse_ads()
"""
import json
import logging
from pathlib import Path
from typing import Any

from . import extractor, postprocessing, preprocessing, prompt
from .status_writer import StatusWriter

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PARSE_CACHE_DIR = BASE_DIR / "data" / "parse_cache_v2"
PARSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def parse_ad(
    ad: dict,
    model: str | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """
    Parst eine Willhaben-Anzeige mit Parser v2.0.
    Drop-in-Ersatz für v1 parse_ad().
    Gibt Liste von Event-Dicts zurück (v1-Schema + modell, pipeline_version, parse_dauer_ms).
    """
    ad_id = str(ad.get("id", ""))

    # Category-Page-Filter (kein Ollama-Aufruf nötig)
    if preprocessing.is_category_page(ad):
        logger.info("Anzeige %s als Category-Page gefiltert", ad_id)
        return []

    if preprocessing.is_non_ticket_ad(ad):
        logger.info("Anzeige %s als Non-Ticket gefiltert", ad_id)
        return []

    context = preprocessing.build_context(ad)
    full_prompt = prompt.build_prompt(context)

    raw, model_used, duration_ms, fallback_used = extractor.extract(
        full_prompt, model_override=model
    )

    used_format = (model_used == extractor.PRIMARY_MODEL and not fallback_used)
    events_raw = postprocessing.parse_raw(raw, used_format_schema=used_format)
    events_validated = postprocessing.validate(events_raw)
    return postprocessing.attach_metadata(
        events_validated, ad, model_used, duration_ms, fallback_used
    )


def parse_ads(
    ads: list[dict],
    use_cache: bool = True,
    model: str | None = None,
) -> list[dict]:
    """
    Verarbeitet eine Liste von Anzeigen.
    Drop-in-Ersatz für v1 parse_ads().
    use_cache=True: bereits geparste IDs (parse_cache_v2/) werden übersprungen.
    """
    all_events: list[dict] = []
    total = len(ads)
    cache_hits = 0
    writer = StatusWriter(total=total, model=model or "gemma3:27b")

    for i, ad in enumerate(ads, 1):
        ad_id = str(ad.get("id", ""))

        if use_cache and ad_id:
            cached = _load_cache(ad_id)
            if cached is not None:
                all_events.extend(cached)
                cache_hits += 1
                ad_title = ad.get("title", ad.get("beschreibung", ""))[:80]
                writer.update(current=i, ad_id=ad_id, title=ad_title)
                continue

        logger.info("Parse %d/%d: %s (v2)", i, total, ad_id or "?")
        try:
            events = parse_ad(ad, model=model, use_cache=False)
        except Exception as exc:
            writer.error(str(exc))
            logger.warning("Fehler beim Parsen von %s: %s", ad_id, exc)
            events = []

        if use_cache and ad_id:
            _save_cache(ad_id, events)

        all_events.extend(events)

        ad_title = ad.get("title", ad.get("beschreibung", ""))[:80]
        duration_ms = events[0].get("parse_dauer_ms") if events else None
        writer.update(current=i, ad_id=ad_id, title=ad_title, duration_ms=duration_ms)

    writer.finish()
    logger.info(
        "v2 Parsing fertig: %d Events, %d Cache-Hits, %d Ollama-Aufrufe",
        len(all_events), cache_hits, total - cache_hits,
    )
    return all_events


def _cache_path(ad_id: str) -> Path:
    return PARSE_CACHE_DIR / f"{ad_id}.json"


def _load_cache(ad_id: str) -> list[dict] | None:
    path = _cache_path(ad_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_cache(ad_id: str, events: list[dict]) -> None:
    try:
        _cache_path(ad_id).write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("v2 Cache-Schreiben fehlgeschlagen: %s", exc)
