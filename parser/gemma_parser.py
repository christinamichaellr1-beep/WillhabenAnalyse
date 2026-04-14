"""
gemma_parser.py

Analysiert Anzeigentexte via Ollama (Gemma3:27b lokal).
Gibt pro Anzeige 1..N Event-Dicts zurück (Händler können mehrere Kategorien haben).

Confidence-System:
  hoch   → alle Kernfelder eindeutig → direkt in Excel
  mittel → 1-2 Felder fehlen → direkt in Excel (mit Markierung)
  niedrig → unklar → Review Queue (Sheet 2)
"""
import json
import re
import datetime
import logging
from typing import Any

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:27b"
TIMEOUT = 180  # Sekunden – Gemma3:27b braucht Zeit

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """Du bist ein Datenextraktions-Assistent für Konzertticket-Anzeigen von willhaben.at.

Antworte AUSSCHLIESSLICH mit einem JSON-Array. Kein Fließtext, keine Erklärungen, kein Markdown.
Das Array enthält IMMER mindestens ein Objekt.
Bei Händlern mit mehreren Ticket-Kategorien desselben Events: ein Objekt PRO Kategorie.

Anzeigentext:
---
{text}
---

Pro Eintrag im Array folgende Felder:

{{
  "event_name": "Künstlername oder Konzertname, so spezifisch wie möglich (string oder null)",
  "event_datum": "Datum im Format YYYY-MM-DD (string oder null)",
  "venue": "Veranstaltungsort/Halle (string oder null)",
  "stadt": "Stadt (string oder null)",
  "kategorie": "Stehplatz | Sitzplatz | VIP | Front-of-Stage | Gemischt | Unbekannt",
  "anzahl_karten": "Anzahl der angebotenen Tickets (integer oder null)",
  "angebotspreis_gesamt": "Gesamtpreis in Euro (float oder null)",
  "preis_ist_pro_karte": "true wenn Preis pro Einzelkarte gilt, false wenn Gesamtpreis für alle, null wenn unklar",
  "originalpreis_pro_karte": "Originalpreis pro Karte falls im Text erwähnt (float oder null)",
  "confidence": "hoch | mittel | niedrig",
  "confidence_grund": "Kurze Begründung wenn confidence nicht hoch (string oder null)"
}}

Regeln:
- confidence=hoch: event_name, event_datum, angebotspreis_gesamt und anzahl_karten alle eindeutig
- confidence=mittel: 1-2 Felder unsicher oder fehlend, aber Kernaussage klar
- confidence=niedrig: Event unklar, Preis nicht eindeutig zuordenbar, oder mehrere Konzerte vermischt
- Mehrere verschiedene Events in einer Anzeige: EIN Objekt mit event_name="MEHRERE", confidence=niedrig
- Händler mit mehreren Kategorien desselben Events: MEHRERE Objekte (je Kategorie eines)
- Preis-Ambiguität (unklar ob pro Karte oder gesamt): preis_ist_pro_karte=null, confidence=niedrig
- Setze NIEMALS einen Wert wenn du ihn nur erraten würdest — lieber null"""

# Standardwerte wenn Parsing fehlschlägt (null statt 0 für optionale Felder)
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


def _call_ollama(prompt: str) -> str:
    """Sendet einen Prompt an Ollama und gibt die Antwort als String zurück."""
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 2048,
            },
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def _extract_json_array(raw: str) -> list[dict]:
    """Versucht, ein JSON-Array aus dem Rohtext zu extrahieren."""
    # Direkt parsen
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        pass

    # JSON-Block aus Markdown extrahieren
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Erstes [ ... ] im Text
    m = re.search(r"(\[.*?\])", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    return []


def _validate_event(obj: Any) -> dict:
    """Füllt fehlende Felder mit Standardwerten, korrigiert Typen."""
    if not isinstance(obj, dict):
        return dict(EMPTY_EVENT)
    result = dict(EMPTY_EVENT)
    result.update({k: v for k, v in obj.items() if k in EMPTY_EVENT})

    # Float-Felder: None bleibt None, sonst float
    for field in ("angebotspreis_gesamt", "originalpreis_pro_karte"):
        val = result[field]
        if val is None:
            result[field] = None
        else:
            try:
                result[field] = float(val)
            except (ValueError, TypeError):
                result[field] = None

    # anzahl_karten: None bleibt None
    val = result["anzahl_karten"]
    if val is not None:
        try:
            result["anzahl_karten"] = int(val)
        except (ValueError, TypeError):
            result["anzahl_karten"] = None

    # preis_ist_pro_karte: true/false/null — string "null"/"true"/"false" normalisieren
    pipc = result["preis_ist_pro_karte"]
    if isinstance(pipc, str):
        if pipc.lower() in ("true", "ja", "yes"):
            result["preis_ist_pro_karte"] = True
        elif pipc.lower() in ("false", "nein", "no"):
            result["preis_ist_pro_karte"] = False
        else:
            result["preis_ist_pro_karte"] = None

    # confidence validieren
    if result["confidence"] not in ("hoch", "mittel", "niedrig"):
        result["confidence"] = "niedrig"

    # kategorie validieren
    valid_kategorien = {"Stehplatz", "Sitzplatz", "VIP", "Front-of-Stage", "Gemischt", "Unbekannt"}
    if result["kategorie"] not in valid_kategorien:
        result["kategorie"] = "Unbekannt"

    return result


def parse_ad(ad: dict) -> list[dict]:
    """
    Analysiert eine Anzeige (Dict aus dem Scraper) mit Gemma via Ollama.
    Gibt eine Liste von Event-Dicts zurück (mind. 1 Eintrag).
    """
    text = ad.get("text_komplett", "")
    titel = ad.get("titel", "")
    preis_roh = ad.get("preis_roh", "")

    # Kompakten Kontext-Text aufbauen
    context = f"Titel: {titel}\nPreis: {preis_roh}\n\n{text[:4000]}"
    prompt = PROMPT_TEMPLATE.format(text=context)

    try:
        raw_response = _call_ollama(prompt)
        events = _extract_json_array(raw_response)
    except requests.exceptions.ConnectionError as exc:
        logger.error("Ollama nicht erreichbar (läuft Ollama?): %s", exc)
        events = []
    except Exception as exc:
        logger.error("Fehler bei Ollama-Aufruf für %s: %s", ad.get("id"), exc)
        events = []

    if not events:
        fallback = dict(EMPTY_EVENT)
        fallback["event_name"] = titel
        fallback["confidence_grund"] = "Ollama-Fehler oder leere Antwort"
        events = [fallback]

    validated = [_validate_event(e) for e in events]

    # Anzeigen-Metadaten anhängen
    for e in validated:
        e["willhaben_id"] = ad.get("id", "")
        e["willhaben_link"] = ad.get("link", "")
        e["verkäufertyp"] = ad.get("verkäufertyp", "")
        e["verkäufername"] = ad.get("verkäufername", "")
        e["verkäufer_id"] = ad.get("verkäufer_id", "")
        e["mitglied_seit"] = ad.get("mitglied_seit", "")
        e["preis_roh"] = preis_roh
        e["parsed_at"] = datetime.datetime.now().isoformat()

    return validated


def parse_ads(ads: list[dict]) -> list[dict]:
    """Verarbeitet eine Liste von Anzeigen-Dicts."""
    all_events: list[dict] = []
    total = len(ads)
    for i, ad in enumerate(ads, 1):
        logger.info("Parse %d/%d: %s", i, total, ad.get("id", "?"))
        events = parse_ad(ad)
        all_events.extend(events)
    return all_events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = {
        "id": "test123",
        "link": "https://www.willhaben.at/test",
        "titel": "2x Rammstein Wien 15.06.2025",
        "preis_roh": "180 €",
        "text_komplett": (
            "Verkaufe 2 Tickets für Rammstein Wien am 15.06.2025 im Ernst Happel Stadion. "
            "Originalpreis je 75 €. Verkaufe wegen Verhinderung. Privatverkauf."
        ),
        "verkäufertyp": "Privat",
        "verkäufername": "Max Mustermann",
        "verkäufer_id": "12345",
        "mitglied_seit": "06/2020",
    }
    result = parse_ad(sample)
    print(json.dumps(result, ensure_ascii=False, indent=2))
