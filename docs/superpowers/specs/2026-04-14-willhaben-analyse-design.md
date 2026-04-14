# WillhabenAnalyse — Design Spec
**Datum:** 2026-04-14  
**Status:** Approved

---

## Zweck

Tägliche Marktübersicht aller Konzert-Tickets auf dem Willhaben-Sekundärmarkt. Ziel: Preisgestaltung für eigene Ticket-Verkäufe, Identifikation attraktiver Events zum Zukaufen.

---

## Architektur: 4-stufige Pipeline

```
Scraping → KI-Parsing → OVP-Check → Excel-Update
```

### Schritt 1: Scraping (`scraper/willhaben_scraper.py`)
- Playwright, headless Chromium
- Kategorie: willhaben.at Konzerte/Musikfestivals, bis zu 3 Listingseiten (90 Anzeigen/Seite)
- Pro Anzeige wird extrahiert: `id, link, titel, preis_roh, text_komplett, verkäufer_id, verkäufername, verkäufertyp, mitglied_seit`
- `verkäufer_id`: aus Profil-Link `/vendor/{id}/` per Regex
- `mitglied_seit`: Text "seit MM/YYYY" per Regex
- Vollständiger Rohtext gespeichert in `data/raw_cache/{id}.json` — kein Datenverlust

### Schritt 2: KI-Parsing (`parser/gemma_parser.py`)
- Ollama API: `requests.post("http://localhost:11434/api/generate")`
- Modell: `gemma3:27b`
- Input: kompletter Rohtext pro Anzeige
- Output: JSON-Array (1..N Objekte — bei Händlern mit mehreren Kategorien ein Objekt pro Kategorie)
- Confidence-System: `hoch / mittel / niedrig`
- `confidence=niedrig` → Review Queue (Sheet 2)

**Gemma-Prompt:**
```
Du bist ein Datenextraktions-Assistent für Konzertticket-Anzeigen von willhaben.at.

Antworte AUSSCHLIESSLICH mit einem JSON-Array. Kein Fließtext, keine Erklärungen, kein Markdown.
Das Array enthält IMMER mindestens ein Objekt.
Bei Händlern mit mehreren Ticket-Kategorien: ein Objekt PRO Kategorie.

Anzeigentext:
---
{anzeigentext}
---

Pro Eintrag:
{
  "event_name": "Künstlername oder Konzertname (string oder null)",
  "event_datum": "YYYY-MM-DD oder null",
  "venue": "Veranstaltungsort/Halle oder null",
  "stadt": "Stadt oder null",
  "kategorie": "Stehplatz | Sitzplatz | VIP | Front-of-Stage | Gemischt | Unbekannt",
  "anzahl_karten": "integer oder null",
  "angebotspreis_gesamt": "float in Euro oder null",
  "preis_ist_pro_karte": "true | false | null (null = unklar)",
  "originalpreis_pro_karte": "float in Euro oder null",
  "confidence": "hoch | mittel | niedrig",
  "confidence_grund": "string oder null"
}

Regeln:
- confidence=hoch: event_name, event_datum, angebotspreis_gesamt, anzahl_karten alle eindeutig
- confidence=mittel: 1-2 Felder unsicher/fehlend, Kernaussage klar
- confidence=niedrig: Event unklar, Preis nicht eindeutig, mehrere Konzerte vermischt
- Mehrere verschiedene Events → EIN Objekt: event_name="MEHRERE", confidence=niedrig
- Händler mit mehreren Kategorien desselben Events → MEHRERE Objekte
- Preis-Ambiguität → preis_ist_pro_karte=null, confidence=niedrig
- Niemals raten — lieber null
```

### Schritt 3: OVP-Check (`ovp/ovp_checker.py`)
- Pro eindeutigem Event (name + datum) einmalig ausgeführt
- Anbieter-URLs aus `config.json` (Freitext, vorbefüllt mit oeticket, myticket, Konzerthaus)
- Watchlist-Events können direkte Event-URLs haben → überspringt Suche
- Preis-Hierarchie: Anbieter-Check > Gemma-extrakt > manuell
- Einmal gefundener OVP bleibt erhalten bei späteren Updates
- Extrahiert: `originalpreis_pro_karte`, `ovp_quelle`, `ausverkauft`

### Schritt 4: Excel-Update (`export/excel_writer.py`)
- `openpyxl`
- Willhaben-ID als Schlüssel → bestehende Zeile updaten
- Event-Datum < heute → automatisch in Archiv-Sheet verschieben
- Farbmarkierungen: OVP-Quelle (grün/gelb/rot) + Confidence (grün/gelb/rot)

---

## Excel-Struktur

### Sheet 1 — Hauptübersicht (24 Spalten)

| # | Spalte | Inhalt |
|---|--------|--------|
| 1 | Scan-Datum | Wann gescannt |
| 2 | Willhaben-Link | URL der Anzeige |
| 3 | Anzeigen-ID | Willhaben-Code |
| 4 | Verkäufer-ID | Willhaben User-ID (fix) |
| 5 | Verkäufername | Anzeigename (kann sich ändern) |
| 6 | Verkäufertyp | Privat / Gewerblich |
| 7 | Mitglied seit | MM/YYYY |
| 8 | Event-Name | Künstler / Konzert |
| 9 | Event-Datum | Datum des Konzerts |
| 10 | Venue | Veranstaltungsort |
| 11 | Stadt | Stadt |
| 12 | Kategorie | Stehplatz / Sitzplatz / VIP / Front-of-Stage / Gemischt / Unbekannt |
| 13 | Anzahl Karten | Anzahl angebotener Tickets |
| 14 | Angebotspreis gesamt | Preis laut Anzeige |
| 15 | Preis ist pro Karte | ja / nein / unklar |
| 16 | Angebotspreis pro Karte | Berechnet: gesamt ÷ anzahl |
| 17 | Originalpreis pro Karte | OVP — farbig: grün=Anbieter, gelb=Anzeige, rot=fehlt |
| 18 | OVP-Quelle | oeticket / myticket / Konzerthaus / Anzeige / manuell / — |
| 19 | Marge € | Angebotspreis p.K. − OVP |
| 20 | Marge % | Aufschlag über OVP |
| 21 | Ausverkauft beim Anbieter | ja / nein / unbekannt |
| 22 | Watchlist | ja / nein |
| 23 | Confidence | hoch / mittel / niedrig — farbig |
| 24 | Review nötig | ja / nein |

### Sheet 2 — Review Queue
Nur Zeilen mit Confidence=niedrig. Zur manuellen Nachbearbeitung.

### Sheet 3 — Archiv
Automatisch verschobene Events (Event-Datum < heute).

### Sheet 4 — Watchlist-Config
Format: `Event-Name | OVP: 89.90 | Link: https://...`  
OVP und Link sind optional. Direktlink überschreibt automatische Anbieter-Suche.

---

## Mac Mini GUI (`app/gui.py`)

tkinter, 5 Tabs:

- **Zeitplan:** Uhrzeit + Intervall (täglich / alle N Stunden). Start/Stop.
- **Anbieter:** Freitext-Liste von Such-URLs. Vorbefüllt: oeticket.com, myticket.at, Wiener Konzerthaus. Erweiterbar.
- **Watchlist:** Ein Event pro Zeile. Format: `Event-Name | OVP: 89.90 | Link: https://...`
- **Export:** Ziel-Ordner. "Jetzt ausführen"-Button.
- **Log:** Scrollbarer Live-Output des letzten Runs.

Konfiguration in `config.json`, beim Start geladen.

---

## Technologie

- Python 3.12
- `playwright` (Scraping)
- `requests` (Ollama API)
- `openpyxl` (Excel)
- `tkinter` (GUI, stdlib)
- `schedule` (Scheduling)
- Ollama mit Gemma3:27b lokal

---

## Dateistruktur

```
/Users/Boti/WillhabenAnalyse/
├── main.py
├── config.json
├── scraper/willhaben_scraper.py
├── parser/gemma_parser.py
├── parser/review_queue.py
├── ovp/ovp_checker.py
├── export/excel_writer.py
├── app/gui.py
├── data/willhaben_markt.xlsx
├── data/raw_cache/{willhaben_id}.json
└── logs/run.log
```

---

## Implementierungsreihenfolge

1. `scraper/willhaben_scraper.py`
2. `parser/gemma_parser.py`
3. `export/excel_writer.py`
4. `ovp/ovp_checker.py`
5. `app/gui.py`
6. `main.py` + `config.json`
