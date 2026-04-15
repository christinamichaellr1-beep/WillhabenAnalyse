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

Antworte AUSSCHLIESSLICH mit einem JSON-Array. Kein Fließtext, keine Erklärungen, kein Markdown.
Das Array enthält IMMER mindestens ein Objekt.

Der Anzeigentext enthält willhaben-Navigation (z.B. "Zum Inhalt", "Nachrichten", "Rechtlicher Hinweis", "Noch mehr ähnliche Anzeigen"). Ignoriere diesen Rausch vollständig. Konzentriere dich ausschließlich auf Titel, Preis und den "Beschreibung"-Abschnitt.

════════════════════════════════════════
SCHRITT 1 — ORIGINALPREIS SUCHEN
════════════════════════════════════════

Durchsuche TITEL und BESCHREIBUNG nach Originalpreis-Mustern:

  Direkte Bezeichnungen:
    Originalpreis / Original-Preis / OVP / NP / Neupreis / UVP
    Aufgedruckter Preis / Aufgedruckter Originalpreis

  Umgangssprachlich:
    "damals um X€ gekauft" / "damals um X€ pro Stück gekauft"
    "habe X€ bezahlt" / "gekauft um X€" / "bezahlt X€"
    "Ticketpreis war X€" / "Preis war X€"

  Im Titel in Klammern:
    "(Originalpreis X€)" / "(NP X€)" / "(OVP: X€)"

→ Trage den Originalpreis IMMER als Preis PRO KARTE ein (nie als Gesamtbetrag).
→ Kein Originalpreis erkennbar → null

════════════════════════════════════════
SCHRITT 2 — PREIS EINORDNEN
════════════════════════════════════════

`angebotspreis_gesamt` = der Gesamtbetrag für ALLE angebotenen Karten zusammen.
  Wenn nur Preis pro Karte bekannt und Anzahl bekannt: Preis × Anzahl = Gesamt.
  Wenn Anzahl unbekannt (z.B. Händler mit offener Stückzahl): null.

`preis_ist_pro_karte` = ob der im Text genannte Preis pro Einzelkarte gilt.
  true  → "Preis pro Karte", "je Ticket", "pro Stück", Händler-Preisilste
  false → "beide zusammen", "für X Karten zusammen", "Gesamtpreis"
  null  → unklar (→ confidence=niedrig)

════════════════════════════════════════
SCHRITT 3 — ANZAHL OBJEKTE
════════════════════════════════════════

WICHTIGSTE REGEL: Händler mit mehreren Ticket-Kategorien desselben Events
→ EIN OBJEKT PRO KATEGORIE. Nicht ein zusammengefasstes Objekt!

Beispiel: "1) Front-of-Stage EUR 129 / 2) Stehplatz EUR 99" → 2 Objekte!

Normallfall (Privatperson, eine Kategorie): 1 Objekt.
Mehrere VERSCHIEDENE Events in einer Anzeige: 1 Objekt, event_name="MEHRERE", confidence=niedrig.

════════════════════════════════════════
FEW-SHOT BEISPIELE
════════════════════════════════════════

--- BEISPIEL A: Privatverkauf, OVP "damals um X€ pro Stück" ---
Titel: Dante YN - Tranquille Tour 2026 - Wien - 2x Tickets
Preis: € 40
Beschreibung: Krankheitsbedingt verkaufe ich 2 Tickets für Dante YN am 14.4. in Wien (FLUCC).
Habe die Tickets damals um 30€ pro Stück gekauft und würde beide zusammen für 40€ weitergeben.

Ausgabe:
[{{"event_name": "Dante YN - Tranquille Tour 2026", "event_datum": "2026-04-14", "venue": "FLUCC", "stadt": "Wien", "kategorie": "Unbekannt", "anzahl_karten": 2, "angebotspreis_gesamt": 40.0, "preis_ist_pro_karte": false, "originalpreis_pro_karte": 30.0, "confidence": "hoch", "confidence_grund": null}}]

--- BEISPIEL B: Privatverkauf, OVP "Originalpreis X Euro Pro Karte" ---
Titel: Luciano Tickets Donauinsel Open Air
Preis: € 40
Beschreibung: Luciano Konzert 21.Juli 2026, Donauinsel Open Air.
Verkaufe beide Karten um 40 Euro, Origninalpreis wäre normalerweise 79 Euro Pro Karte
aber ich habe beide Karten gewonnen und gebe sie für 40 Euro weiter.

Ausgabe:
[{{"event_name": "Luciano", "event_datum": "2026-07-21", "venue": "Donauinsel Open Air", "stadt": "Wien", "kategorie": "Unbekannt", "anzahl_karten": 2, "angebotspreis_gesamt": 40.0, "preis_ist_pro_karte": false, "originalpreis_pro_karte": 79.0, "confidence": "hoch", "confidence_grund": null}}]

--- BEISPIEL C: Händler 1 Kategorie, "Preis pro Karte", OVP explizit ---
Titel: BERQ / Stehplatz / 18.11.26 Graz
Preis: € 85
Beschreibung: BERQ Live in Graz 18.11.26 Helmuth List Halle
4 x Stehplatz – Preis pro Karte 85€ – auch einzeln abzugeben
Originalpreis Stehplätze 58,90 € inkl.Gebühren

Ausgabe:
[{{"event_name": "BERQ", "event_datum": "2026-11-18", "venue": "Helmuth List Halle", "stadt": "Graz", "kategorie": "Stehplatz", "anzahl_karten": 4, "angebotspreis_gesamt": 340.0, "preis_ist_pro_karte": true, "originalpreis_pro_karte": 58.9, "confidence": "hoch", "confidence_grund": null}}]

--- BEISPIEL D: OVP im Titel in Klammern ---
Titel: Olivia Dean - Köln, 11.5., Lounge, (Originalpreis 300€), Plätze in 1. Reihe inkl Buffet
Preis: € 290
Beschreibung: Olivia Dean - Köln, 11.5., Lounge, Plätze in 1. Reihe inkl Buffet. Versand übernehme gerne ich.

Ausgabe:
[{{"event_name": "Olivia Dean", "event_datum": "2026-05-11", "venue": null, "stadt": "Köln", "kategorie": "VIP", "anzahl_karten": null, "angebotspreis_gesamt": 290.0, "preis_ist_pro_karte": null, "originalpreis_pro_karte": 300.0, "confidence": "mittel", "confidence_grund": "Anzahl Karten unklar; OVP aus Titel entnommen"}}]

--- BEISPIEL E: Händler mit 2 Kategorien → ZWINGEND 2 Objekte ---
Titel: Pizzera & Jaus 30.05.2026 Salzburg! Front of Stage & Stehplatz Tickets!
Preis: € 99
Beschreibung: Pizzera und Jaus, Salzburg, 30.05.2026, Residenzplatz Salzburg.
1) Stehplatz Front-of-Stage* Preis pro Karte EUR 129,-
2) Stehplatz** Preis pro Karte EUR 99,-
Aufgedruckter Originalpreis Stehplatz Front-of-Stage* EUR 97,49
Aufgedruckter Originalpreis Stehplatz** EUR 77,49

Ausgabe (2 Objekte!):
[
  {{"event_name": "Pizzera & Jaus", "event_datum": "2026-05-30", "venue": "Residenzplatz Salzburg", "stadt": "Salzburg", "kategorie": "Front-of-Stage", "anzahl_karten": null, "angebotspreis_gesamt": null, "preis_ist_pro_karte": true, "originalpreis_pro_karte": 97.49, "confidence": "hoch", "confidence_grund": null}},
  {{"event_name": "Pizzera & Jaus", "event_datum": "2026-05-30", "venue": "Residenzplatz Salzburg", "stadt": "Salzburg", "kategorie": "Stehplatz", "anzahl_karten": null, "angebotspreis_gesamt": null, "preis_ist_pro_karte": true, "originalpreis_pro_karte": 77.49, "confidence": "hoch", "confidence_grund": null}}
]

════════════════════════════════════════
FELDER (je Objekt)
════════════════════════════════════════

{{
  "event_name": "Künstlername oder Konzertname (string oder null)",
  "event_datum": "YYYY-MM-DD (string oder null)",
  "venue": "Veranstaltungsort/Halle (string oder null)",
  "stadt": "Stadt (string oder null)",
  "kategorie": "Stehplatz | Sitzplatz | VIP | Front-of-Stage | Gemischt | Unbekannt",
  "anzahl_karten": "Anzahl angebotener Tickets (integer oder null)",
  "angebotspreis_gesamt": "Gesamtbetrag für alle Karten in Euro (float oder null)",
  "preis_ist_pro_karte": true/false/null,
  "originalpreis_pro_karte": "OVP/NP/Originalpreis PRO Karte in Euro (float oder null)",
  "confidence": "hoch | mittel | niedrig",
  "confidence_grund": "Begründung wenn nicht hoch (string oder null)"
}}

Confidence-Regeln:
- hoch:    event_name, event_datum, angebotspreis_gesamt und anzahl_karten alle eindeutig
           ODER Händler mit klarem Preis-pro-Karte (dann darf anzahl_karten null sein)
- mittel:  1-2 Felder fehlen/unsicher, Kernaussage klar
- niedrig: Event unklar, Preis nicht zuordenbar, grundlegende Ambiguität

Setze NIEMALS einen Wert wenn du ihn nur erraten würdest — lieber null.

════════════════════════════════════════
AKTUELLE ANZEIGE
════════════════════════════════════════

{text}"""

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
