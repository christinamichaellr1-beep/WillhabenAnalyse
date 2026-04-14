"""
ovp_checker.py

Prüft Original-Ticketpreise (OVP) pro Event bei konfigurierten Anbietern.

Ablauf pro Event:
  1. Direktlink aus Watchlist vorhanden? → direkt aufrufen
  2. Sonst: Suchseiten der Anbieter aus config.json mit Event-Name suchen
  3. Ersten Treffer mit Preis verwenden

Rückgabe pro Event:
  {originalpreis_pro_karte, ovp_quelle, ausverkauft}

OVP wird pro Event gecacht (event_key = event_name + event_datum).
Einmal gefundener OVP wird nicht erneut abgerufen.
"""
import asyncio
import json
import re
import logging
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
OVP_CACHE_FILE = BASE_DIR / "data" / "ovp_cache.json"

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _load_ovp_cache() -> dict:
    """Lädt den OVP-Cache (event_key → {preis, quelle, ausverkauft})."""
    if OVP_CACHE_FILE.exists():
        try:
            return json.loads(OVP_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_ovp_cache(cache: dict) -> None:
    OVP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVP_CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _event_key(event_name: str, event_datum: str) -> str:
    return f"{event_name.strip().lower()}|{(event_datum or '').strip()}"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("config.json Lesefehler: %s", exc)
        return {}


def _get_provider_search_urls(config: dict) -> list[str]:
    """Gibt Such-URL-Templates zurück. {event} wird durch den Event-Namen ersetzt."""
    return config.get("ovp_search_urls", [
        "https://www.oeticket.com/search?q={event}",
        "https://www.myticket.at/search?q={event}",
    ])


def _get_watchlist(config: dict) -> list[dict]:
    """
    Watchlist-Einträge aus config.json.
    Format: {event_name, ovp_preis (optional), ovp_link (optional)}
    """
    return config.get("watchlist", [])


# ---------------------------------------------------------------------------
# Preis + Status aus Seitentext
# ---------------------------------------------------------------------------

def _extract_price(text: str) -> float | None:
    """Extrahiert den ersten plausiblen Ticketpreis aus Text."""
    patterns = [
        r"(\d{1,4}[.,]\d{2})\s*€",
        r"€\s*(\d{1,4}[.,]\d{2})",
        r"(\d{2,4})\s*€",
        r"EUR\s*(\d{1,4}[.,]?\d{0,2})",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            raw = m.group(1).replace(",", ".")
            try:
                val = float(raw)
                # Plausibilitätscheck: Ticketpreise zwischen 5 und 5000 €
                if 5.0 <= val <= 5000.0:
                    return val
            except ValueError:
                continue
    return None


def _detect_sold_out(text: str) -> str:
    """Gibt 'ja', 'nein' oder 'unbekannt' zurück."""
    text_lower = text.lower()
    sold_out_keywords = [
        "ausverkauft", "sold out", "sold-out", "nicht mehr verfügbar",
        "vergriffen", "nicht verfügbar", "keine tickets mehr",
    ]
    available_keywords = [
        "in den warenkorb", "ticket kaufen", "jetzt kaufen", "tickets bestellen",
        "add to cart", "buy now",
    ]
    if any(kw in text_lower for kw in sold_out_keywords):
        return "ja"
    if any(kw in text_lower for kw in available_keywords):
        return "nein"
    return "unbekannt"


# ---------------------------------------------------------------------------
# Seite prüfen
# ---------------------------------------------------------------------------

async def _fetch_page_text(page, url: str) -> str | None:
    """Lädt eine URL und gibt den Seitentext zurück."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(1500)
        return await page.evaluate("document.body ? document.body.innerText : ''")
    except PlaywrightTimeoutError:
        logger.warning("Timeout: %s", url)
        return None
    except Exception as exc:
        logger.warning("Fehler beim Laden von %s: %s", url, exc)
        return None


async def _check_direct_url(page, url: str) -> dict:
    """Prüft eine direkte Anbieter-URL auf Preis und Verfügbarkeit."""
    text = await _fetch_page_text(page, url)
    if not text:
        return {"preis": None, "ausverkauft": "unbekannt"}

    # Anbieter-Name aus URL ableiten
    quelle = "unbekannt"
    for anbieter in ("oeticket", "myticket", "konzerthaus", "eventim", "ticketmaster"):
        if anbieter in url.lower():
            quelle = anbieter
            break

    return {
        "preis": _extract_price(text),
        "ausverkauft": _detect_sold_out(text),
        "quelle": quelle,
    }


async def _search_providers(page, event_name: str, search_url_templates: list[str]) -> dict:
    """
    Sucht auf Anbieter-Suchseiten nach dem Event-Namen.
    Gibt bestes Ergebnis zurück (erstes mit Preis).
    """
    encoded_name = event_name.replace(" ", "+")

    for template in search_url_templates:
        url = template.replace("{event}", encoded_name)

        # Anbieter-Name aus URL
        quelle = "unbekannt"
        for anbieter in ("oeticket", "myticket", "konzerthaus", "eventim", "ticketmaster"):
            if anbieter in url.lower():
                quelle = anbieter
                break

        text = await _fetch_page_text(page, url)
        if not text:
            continue

        preis = _extract_price(text)
        ausverkauft = _detect_sold_out(text)

        if preis is not None:
            logger.info("  OVP gefunden bei %s: %.2f € (%s)", quelle, preis, ausverkauft)
            return {"preis": preis, "ausverkauft": ausverkauft, "quelle": quelle}

        # Auch ohne Preis: Ausverkauft-Status verwerten
        if ausverkauft == "ja":
            return {"preis": None, "ausverkauft": "ja", "quelle": quelle}

        await page.wait_for_timeout(800)

    return {"preis": None, "ausverkauft": "unbekannt", "quelle": ""}


# ---------------------------------------------------------------------------
# Haupt-API
# ---------------------------------------------------------------------------

async def check_events(events: list[dict], log_fn=logger.info, headless: bool = True) -> list[dict]:
    """
    Prüft OVP für eine Liste von Event-Dicts (aus gemma_parser).
    Überspringt Events deren OVP bereits im Cache ist.
    Gibt die Events mit ergänzten Feldern zurück:
      originalpreis_pro_karte, ovp_quelle, ausverkauft
    """
    config = _load_config()
    search_templates = _get_provider_search_urls(config)
    watchlist = {
        entry["event_name"].strip().lower(): entry
        for entry in _get_watchlist(config)
        if entry.get("event_name")
    }
    ovp_cache = _load_ovp_cache()
    cache_updated = False

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="de-AT",
        )
        page = await context.new_page()
        page.set_default_timeout(30000)

        # Deduplizieren: pro Event-Key nur einmal prüfen
        checked_keys: dict[str, dict] = {}

        for event in events:
            event_name = event.get("event_name") or ""
            event_datum = event.get("event_datum") or ""

            if not event_name or event_name == "MEHRERE":
                results.append(event)
                continue

            key = _event_key(event_name, event_datum)

            # 1. Cache-Hit?
            if key in ovp_cache:
                cached = ovp_cache[key]
                event["originalpreis_pro_karte"] = cached.get("preis")
                event["ovp_quelle"] = cached.get("quelle", "")
                event["ausverkauft"] = cached.get("ausverkauft", "unbekannt")
                results.append(event)
                continue

            # 2. Bereits in diesem Run geprüft?
            if key in checked_keys:
                ovp_result = checked_keys[key]
                event["originalpreis_pro_karte"] = ovp_result.get("preis")
                event["ovp_quelle"] = ovp_result.get("quelle", "")
                event["ausverkauft"] = ovp_result.get("ausverkauft", "unbekannt")
                results.append(event)
                continue

            log_fn(f"OVP-Check: {event_name} ({event_datum})")

            # 3. Watchlist-Direktlink?
            watchlist_entry = watchlist.get(event_name.strip().lower(), {})
            direct_link = watchlist_entry.get("ovp_link")
            known_ovp = watchlist_entry.get("ovp_preis")

            if known_ovp:
                # OVP aus Watchlist direkt verwenden
                ovp_result = {
                    "preis": float(known_ovp),
                    "ausverkauft": "unbekannt",
                    "quelle": "manuell",
                }
                log_fn(f"  → Watchlist OVP: {known_ovp} €")
            elif direct_link:
                ovp_result = await _check_direct_url(page, direct_link)
                log_fn(f"  → Direktlink: Preis={ovp_result['preis']}, Status={ovp_result['ausverkauft']}")
            else:
                # 4. Anbieter-Suche
                ovp_result = await _search_providers(page, event_name, search_templates)
                log_fn(f"  → Suche: Preis={ovp_result['preis']}, Status={ovp_result['ausverkauft']}")

            # Ergebnis cachen
            ovp_cache[key] = ovp_result
            checked_keys[key] = ovp_result
            cache_updated = True

            event["originalpreis_pro_karte"] = ovp_result.get("preis")
            event["ovp_quelle"] = ovp_result.get("quelle", "")
            event["ausverkauft"] = ovp_result.get("ausverkauft", "unbekannt")
            results.append(event)

            await page.wait_for_timeout(500)

        await browser.close()

    if cache_updated:
        _save_ovp_cache(ovp_cache)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample_events = [
        {
            "event_name": "Linkin Park",
            "event_datum": "2026-06-09",
            "stadt": "Wien",
            "kategorie": "Stehplatz",
            "willhaben_id": "12345",
        }
    ]
    result = asyncio.run(check_events(sample_events))
    print(json.dumps(result, ensure_ascii=False, indent=2))
