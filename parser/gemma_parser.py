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
from pathlib import Path
from typing import Any

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:latest"
TIMEOUT = 180  # Sekunden

BASE_DIR = Path(__file__).resolve().parent.parent
PARSE_CACHE_DIR = BASE_DIR / "data" / "parse_cache"
PARSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """Du bist ein Datenextraktions-Assistent für Konzertticket-Anzeigen von willhaben.at.

Denke zuerst schrittweise nach (im Feld "_denkschritt"), dann befülle die anderen Felder:
1. Was ist das Event? (Künstler, Datum, Ort)
2. Wie viele Tickets werden angeboten?
3. Ist der genannte Preis pro Karte oder ein Gesamtpreis?
4. Gibt es einen Originalpreis/OVP? In welcher Form steht er im Text?
5. Handelt es sich um einen Händler mit mehreren Ticket-Kategorien?

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt dieser Struktur (kein Fließtext, kein Markdown):
{{"events": [ ...ein Objekt pro Ticket-Kategorie... ]}}

Das Array "events" enthält IMMER mindestens ein Objekt.
Bei Händlern mit mehreren Ticket-Kategorien desselben Events: ein Objekt PRO Kategorie.

--- ANZEIGENTEXT ---
{text}
--- ENDE ---

Pro Eintrag in "events" folgende Felder:

{{
  "_denkschritt": "Dein kurzes Reasoning zu Preis, OVP und Kategorien (string, wird ignoriert)",
  "event_name": "Künstlername oder Konzertname, so spezifisch wie möglich (string oder null)",
  "event_datum": "Datum im Format YYYY-MM-DD (string oder null)",
  "venue": "Veranstaltungsort/Halle (string oder null)",
  "stadt": "Stadt (string oder null)",
  "kategorie": "Stehplatz | Sitzplatz | VIP | Front-of-Stage | Gemischt | Unbekannt",
  "anzahl_karten": "Anzahl der angebotenen Tickets (integer oder null)",
  "angebotspreis_gesamt": "Gesamtpreis für ALLE angebotenen Tickets in Euro (float oder null)",
  "preis_ist_pro_karte": "true wenn angebotspreis_gesamt pro Einzelkarte gilt (Gesamtmenge unbekannt), false wenn es der Gesamtpreis ist, null wenn völlig unklar",
  "originalpreis_pro_karte": "Originalpreis/OVP pro Karte in Euro, falls im Text erkennbar (float oder null)",
  "confidence": "hoch | mittel | niedrig",
  "confidence_grund": "Kurze Begründung wenn confidence nicht hoch (string oder null)"
}}

=== PREIS-REGELN ===
- "€ 360" + "4 Tickets x 90€" → angebotspreis_gesamt=360, preis_ist_pro_karte=false
- "40€ pro Karte" + "2 Karten" → angebotspreis_gesamt=80 (2×40), preis_ist_pro_karte=false
- "Preis pro Ticket: 129€" + "4x Stehplätze" → angebotspreis_gesamt=516 (4×129), preis_ist_pro_karte=false
- "Preis pro Ticket: 89€" ohne Anzahl → angebotspreis_gesamt=89, preis_ist_pro_karte=true
- Unklar ob pro Karte oder gesamt → preis_ist_pro_karte=null, confidence=niedrig

=== OVP-REGELN (originalpreis_pro_karte setzen wenn EINE dieser Varianten vorkommt) ===
- "Originalpreis: 75€", "Originalpreis war 135€", "Originalpreis 19€ pro Ticket"
- "OP ist 39 €", "OP: 45€", "OP 80€"
- "NP 80€", "Neupreis: 90€"
- "Ursprünglich für 19€ gekauft", "gekauft um 60€", "bezahlt 55€"
- "Preis war 70€", "hat damals 80€ gekostet"
- "(NP 80€)", "(OVP 95€)" — Klammern beachten
- "Information zum Originalpreis gemäß § 4a ... Stehplatz: 67,49 Euro" → OVP = 67,49
- Online-Ticketshop-Preis genannt → als OVP setzen

=== KONFIDENZ-REGELN ===
- hoch: event_name, event_datum, angebotspreis_gesamt und anzahl_karten alle eindeutig bekannt
- mittel: 1–2 Felder fehlen oder unsicher, aber Kernaussage klar
- niedrig: Event unklar, Preis nicht zuordenbar, oder mehrere verschiedene Konzerte
- Mehrere verschiedene Events: EIN Objekt, event_name="MEHRERE", confidence=niedrig
- Setze NIEMALS einen Wert wenn du ihn nur erraten würdest — lieber null

=== FEW-SHOT-BEISPIELE ===

Beispiel 1 – Privatverkauf, Originalpreis bekannt:
Titel: 2 x Tickets Johannes Oerding, 17.04. Gasometer Wien
Preis: € 120
Beschreibung: Ich verkaufe zwei Tickets für Johannes Oerding am 17.04. in der Raiffeisenarena im Gasometer. Originalpreis: 75€ pro Karte. Nur Abholung in Wien.
→ {{"events": [
  {{
    "_denkschritt": "2 Tickets, Gesamtpreis 120€ (2×60). Originalpreis 75€ pro Karte explizit. Datum 17.04. ohne Jahr – nehme aktuelles Jahr 2026.",
    "event_name": "Johannes Oerding",
    "event_datum": "2026-04-17",
    "venue": "Gasometer",
    "stadt": "Wien",
    "kategorie": "Unbekannt",
    "anzahl_karten": 2,
    "angebotspreis_gesamt": 120,
    "preis_ist_pro_karte": false,
    "originalpreis_pro_karte": 75,
    "confidence": "hoch",
    "confidence_grund": null
  }}
]}}

Beispiel 2 – Privatverkauf, Preis-pro-Karte im Text:
Titel: 2 Tickets - BLACKOUT ELEMNT Arena Wien
Preis: € 80
Beschreibung: 40€ pro Karte (Original Preis - Finale Phase). Ich habe 2 Karten für Blackout am 11.04. Tickets per PDF.
→ {{"events": [
  {{
    "_denkschritt": "2 Karten × 40€ = 80€ Gesamt. 'Original Preis' = 40€ pro Karte, da Angebotspreis gleich Original – kein Abschlag/Aufschlag. Kein Jahr, nehme 2026.",
    "event_name": "BLACKOUT",
    "event_datum": "2026-04-11",
    "venue": "ELEMNT Arena",
    "stadt": "Wien",
    "kategorie": "Unbekannt",
    "anzahl_karten": 2,
    "angebotspreis_gesamt": 80,
    "preis_ist_pro_karte": false,
    "originalpreis_pro_karte": 40,
    "confidence": "hoch",
    "confidence_grund": null
  }}
]}}

Beispiel 3 – Händler mit 2 Kategorien + § 4a Originalpreis:
Titel: Die Fantastischen Vier 06.02.2027 Stadthalle Wien Stehplätze Front of Stage
Preis: € 149
Beschreibung: DIE FANTASTISCHEN VIER LIVE IN WIEN / Datum: 6. Februar 2027 / Location: Stadthalle Wien
4x Stehplätze / Preis pro Ticket: 149,-- Euro
4x Stehplätze Front of Stage / Preis pro Ticket: 189,-- Euro
Information zum Originalpreis gemäß § 4a: Stehplatz: 79,90 Euro / Stehplatz Front of Stage: 119,90 Euro
→ {{"events": [
  {{
    "_denkschritt": "Händler, 2 Kategorien desselben Events → 2 Objekte. Kat.1: 4×149=596€, OVP 79,90. Kat.2: 4×189=756€, OVP 119,90.",
    "event_name": "Die Fantastischen Vier",
    "event_datum": "2027-02-06",
    "venue": "Stadthalle Wien",
    "stadt": "Wien",
    "kategorie": "Stehplatz",
    "anzahl_karten": 4,
    "angebotspreis_gesamt": 596,
    "preis_ist_pro_karte": false,
    "originalpreis_pro_karte": 79.90,
    "confidence": "hoch",
    "confidence_grund": null
  }},
  {{
    "_denkschritt": "Zweite Kategorie: Front of Stage.",
    "event_name": "Die Fantastischen Vier",
    "event_datum": "2027-02-06",
    "venue": "Stadthalle Wien",
    "stadt": "Wien",
    "kategorie": "Front-of-Stage",
    "anzahl_karten": 4,
    "angebotspreis_gesamt": 756,
    "preis_ist_pro_karte": false,
    "originalpreis_pro_karte": 119.90,
    "confidence": "hoch",
    "confidence_grund": null
  }}
]}}"""

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
                "num_predict": 4096,
            },
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def _extract_json_array(raw: str) -> list[dict]:
    """Versucht, ein JSON-Array aus dem Rohtext zu extrahieren.
    Unterstützt: {"events": [...]}, direkte Arrays, und einzelne Objekte."""
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            # {"events": [...]} Wrapper (bevorzugtes Format)
            if "events" in parsed and isinstance(parsed["events"], list):
                return parsed["events"]
            return [parsed]
    except Exception:
        pass

    # JSON-Block aus Markdown extrahieren
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                if "events" in parsed and isinstance(parsed["events"], list):
                    return parsed["events"]
                return [parsed]
        except Exception:
            pass

    # Erstes { "events": [...] } im Text
    m = re.search(r'(\{[^{}]*"events"\s*:\s*\[.*?\]\s*\})', raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if "events" in parsed:
                return parsed["events"]
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
    """Füllt fehlende Felder mit Standardwerten, korrigiert Typen. Ignoriert _denkschritt."""
    if not isinstance(obj, dict):
        return dict(EMPTY_EVENT)
    result = dict(EMPTY_EVENT)
    result.update({k: v for k, v in obj.items() if k in EMPTY_EVENT})  # _denkschritt nicht in EMPTY_EVENT → wird verworfen

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


def _parse_cache_path(ad_id: str) -> Path:
    return PARSE_CACHE_DIR / f"{ad_id}.json"


def _load_parse_cache(ad_id: str) -> list[dict] | None:
    path = _parse_cache_path(ad_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_parse_cache(ad_id: str, events: list[dict]) -> None:
    try:
        _parse_cache_path(ad_id).write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Parse-Cache konnte nicht gespeichert werden: %s", exc)


def parse_ads(ads: list[dict], use_cache: bool = True) -> list[dict]:
    """
    Verarbeitet eine Liste von Anzeigen-Dicts.
    use_cache=True: bereits geparste Anzeigen (data/parse_cache/{id}.json) werden übersprungen.
    """
    all_events: list[dict] = []
    total = len(ads)
    cache_hits = 0
    for i, ad in enumerate(ads, 1):
        ad_id = str(ad.get("id", ""))
        if use_cache and ad_id:
            cached = _load_parse_cache(ad_id)
            if cached is not None:
                all_events.extend(cached)
                cache_hits += 1
                if cache_hits % 50 == 0 or i == total:
                    logger.info("Parse %d/%d: Cache-Hit (%d cached, %d neu)", i, total, cache_hits, i - cache_hits)
                continue
        logger.info("Parse %d/%d: %s (Ollama)", i, total, ad_id or "?")
        events = parse_ad(ad)
        if use_cache and ad_id:
            _save_parse_cache(ad_id, events)
        all_events.extend(events)
    logger.info("Parsing fertig: %d Events, %d Cache-Hits, %d Ollama-Aufrufe",
                len(all_events), cache_hits, total - cache_hits)
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
