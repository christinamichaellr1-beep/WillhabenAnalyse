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

PROMPT_TEMPLATE = """Du analysierst eine Ticket-Anzeige von willhaben.at. Antworte NUR mit einem JSON-Array — kein Text, kein Markdown.

=== ANZEIGE ===
{text}
=== ENDE DER ANZEIGE ===

WICHTIG: Der Abschnitt "Noch mehr ähnliche Anzeigen" am Ende enthält ANDERE Anzeigen — ignoriere ihn vollständig. Analysiere nur den Haupttext der Anzeige (Titel, Preis und Beschreibung).

---

SCHRITT 1 — HÄNDLER ODER PRIVAT?
Händler-Signale: "Unternehmen", "Ticketshop", "Ticketswien", "TicketExpress", "Kartenbüro", "Ticketbörse", "Hotline", "Firmenwebsite", "Anbieter kontaktieren", "Wirtschaftskammer", "§ 4a Abs. 1 Z 7 FAGG".
→ Händler können mehrere Kategorien (Stehplatz, Sitzplatz, VIP, FoS) für dasselbe Event anbieten → je eine Zeile pro Kategorie.
→ Privatperson: immer eine Zeile (außer wirklich mehrere verschiedene Events vermischt).

SCHRITT 2 — ORIGINALPREIS ERKENNEN
Suche nach diesen Mustern und extrahiere den Betrag als originalpreis_pro_karte (immer PRO KARTE, umrechnen falls nötig):
• "Originalpreis: X€", "OVP: X€", "NP: X€", "UVP: X€", "Neupreis X€", "Listenpreis X€", "Normalpreis X€"
• "OP: X Schilling" → Schilling in Euro ignorieren (null setzen, keine Umrechnung)
• "originaler Kaufpreis X€", "damals um X€ gekauft", "damals um X€ pro Stück gekauft"
• "gekauft für X€", "bezahlt X€", "hat X€ gekostet", "Preis war X€"
• "(89€)", "(Originalpreis 300€)", "(NP 65€)" — Betrag in Klammern
• "Originalpreis für 2 Karten X€" → divide by 2 → originalpreis_pro_karte
• "Information zum Originalpreis gemäß: § 4a Abs. 1 Z 7 FAGG — Kategorie: X,XX" → X,XX ist der gesetzliche Originalpreis pro Karte
• "unter OVP", "zum Originalpreis" → Hinweis dass OVP existiert, aber Wert oft im Text direkt danach
Wenn kein Originalpreis erkennbar: null (nicht raten!).

SCHRITT 3 — PREIS INTERPRETIEREN
Der "Preis:" im Kopf ist der ANGEBOTSPREIS. Entscheide ob er pro Karte oder Gesamt ist:
→ preis_ist_pro_karte=true: "je X€", "pro Karte X€", "pro Ticket X€", "Stückpreis X€", "FIXPREIS X€ JE Karte", "Preis pro Ticket: X€", "X€ pro Ticket"
→ preis_ist_pro_karte=false: "für beide X€", "beide zusammen X€", "2 Karten für X€", "X€ für alle", "für N Stück X€"
→ preis_ist_pro_karte=null: weder das eine noch das andere eindeutig erkennbar → confidence=niedrig

SCHRITT 4 — CONFIDENCE
• hoch: event_name + event_datum + angebotspreis_gesamt + anzahl_karten alle eindeutig aus dem Text
• mittel: 1–2 Felder fehlen oder unklar, Kernaussage aber verständlich
• niedrig: Preis-Ambiguität, mehrere vermischte Events, oder anzahl_karten völlig unklar

---

OUTPUT-SCHEMA (ein Objekt pro Kategorie bei Händlern, sonst ein Objekt):
{{
  "event_name": "Künstler/Konzertname (string | null)",
  "event_datum": "YYYY-MM-DD (string | null)",
  "venue": "Halle/Location (string | null)",
  "stadt": "Stadt (string | null)",
  "kategorie": "Stehplatz | Sitzplatz | VIP | Front-of-Stage | Gemischt | Unbekannt",
  "anzahl_karten": "Anzahl der angebotenen Tickets (integer | null)",
  "angebotspreis_gesamt": "Gesamtpreis aller Karten in Euro (float | null)",
  "preis_ist_pro_karte": "true | false | null",
  "originalpreis_pro_karte": "Originalpreis je Karte in Euro (float | null)",
  "confidence": "hoch | mittel | niedrig",
  "confidence_grund": "Pflicht wenn nicht hoch (string | null)"
}}

---

BEISPIELE:

Beispiel A — Einfache Privatanzeige mit OVP:
Titel: Dante YN - Tranquille Tour 2026 - Wien - 2x Tickets
Preis: € 40
Beschreibung: Krankheitsbedingt verkaufe ich kurzfristig 2 Tickets für Dante YN - Tranquille Tour 2026 am 14.4. in Wien (FLUCC). Habe die Tickets damals um 30€ pro Stück gekauft und würde beide zusammen für 40€ weitergeben.
→ [
  {{
    "event_name": "Dante YN - Tranquille Tour 2026",
    "event_datum": "2026-04-14",
    "venue": "FLUCC",
    "stadt": "Wien",
    "kategorie": "Unbekannt",
    "anzahl_karten": 2,
    "angebotspreis_gesamt": 40.0,
    "preis_ist_pro_karte": false,
    "originalpreis_pro_karte": 30.0,
    "confidence": "hoch",
    "confidence_grund": null
  }}
]

Beispiel B — Händler mit § 4a FAGG Originalpreis:
Titel: Soap & Skin 05.07.2026 Wiener Staatsoper TOP Sitzplätze Parkett - 3.Reihe
Preis: € 129
Beschreibung: SOAP & SKIN IN WIEN. Datum: 5. Juli 2026. Location: Wiener Staatsoper. 4x TOP-Sitzplätze Parkett - 3.Reihe. Preis pro Ticket: 129,-- Euro. 100% ORIGINAL - TICKETS!!! Gewerbliches Kartenbüro. Information zum Originalpreis gemäß: § 4a Abs. 1 Z 7 FAGG. TOP Sitzplatz Parkett: 109,50
→ [
  {{
    "event_name": "Soap & Skin",
    "event_datum": "2026-07-05",
    "venue": "Wiener Staatsoper",
    "stadt": "Wien",
    "kategorie": "Sitzplatz",
    "anzahl_karten": 4,
    "angebotspreis_gesamt": 516.0,
    "preis_ist_pro_karte": true,
    "originalpreis_pro_karte": 109.5,
    "confidence": "hoch",
    "confidence_grund": null
  }}
]

Beispiel C — Expliziter Originalpreis + pro Karte Preis:
Titel: (reserviert) 2x BTS TICKETS IN MÜNCHEN - SA. 11. JULI 2026
Preis: € 500
Beschreibung: Tickets für BTS „ARIRANG" in München. Originalpreis: € 180,50 pro Ticket. Verkaufspreis: €500 pro Ticket. Bereich 228 Kern H.
→ [
  {{
    "event_name": "BTS - ARIRANG World Tour",
    "event_datum": "2026-07-11",
    "venue": null,
    "stadt": "München",
    "kategorie": "Sitzplatz",
    "anzahl_karten": 2,
    "angebotspreis_gesamt": 1000.0,
    "preis_ist_pro_karte": true,
    "originalpreis_pro_karte": 180.5,
    "confidence": "hoch",
    "confidence_grund": null
  }}
]

Beispiel D — Unklarer Preis (pro Karte oder gesamt?):
Titel: ADELE - The show from London
Preis: € 250
Beschreibung: Ich verkaufe 4 Tickets. In der Reihe 11. Das Event findet am 31.10.2026 im Austria Center Vienna statt. Privatverkauf.
→ [
  {{
    "event_name": "Adele - The Show from London",
    "event_datum": "2026-10-31",
    "venue": "Austria Center Vienna",
    "stadt": "Wien",
    "kategorie": "Sitzplatz",
    "anzahl_karten": 4,
    "angebotspreis_gesamt": 250.0,
    "preis_ist_pro_karte": null,
    "originalpreis_pro_karte": null,
    "confidence": "niedrig",
    "confidence_grund": "Unklar ob 250€ pro Karte oder für alle 4 Karten gesamt"
  }}
]

---

Jetzt analysiere die obige Anzeige und gib NUR das JSON-Array zurück."""

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
