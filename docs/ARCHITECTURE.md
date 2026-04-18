# Architektur: WillhabenAnalyse v2.1

## Überblick

WillhabenAnalyse ist ein macOS-Desktoptool, das Konzert-Ticket-Anzeigen von willhaben.at automatisch scrapt, per lokalem LLM (Ollama/Gemma) strukturiert extrahiert, Original-Verkaufspreise bei österreichischen Ticket-Anbietern nachschlägt und die Ergebnisse in eine Excel-Arbeitsmappe schreibt. Das System richtet sich an Privatnutzer, die den Ticket-Wiederverkaufsmarkt beobachten möchten, und läuft vollständig lokal — ohne Cloud-Abhängigkeit beim Parsing.

---

## System-Kontext

```
                        ┌───────────────────────────────────────────┐
                        │           WillhabenAnalyse v2.1           │
                        │                                           │
  willhaben.at ─────────►  Scraper (Playwright)                     │
  (Konzert-Tickets)     │       │                                   │
                        │       ▼                                   │
  Ollama (lokal) ───────►  Parser v2 (gemma3:27b)                   │
  localhost:11434       │       │                                   │
                        │       ▼                                   │
  oeticket / eventim /  │  OVP-Checker (Playwright)                 │
  ticketmaster / …  ────►       │                                   │
                        │       ▼                                   │
  Google Drive ◄─────────  Excel-Writer + Drive-Upload              │
                        │       │                                   │
                        │       ▼                                   │
                        │  .willhaben_status.json                   │
                        └───────────────────┬───────────────────────┘
                                            │
                                            ▼
                                    Nutzer (GUI / CLI)
```

---

## Komponenten-Übersicht

| Komponente | Modul | Verantwortung |
|---|---|---|
| Scraper | `scraper/willhaben_scraper.py` | Lädt per Playwright bis zu 5 Übersichtsseiten (90 Anzeigen/Seite) und je eine Detailseite pro Inserat; speichert Rohtext als JSON in `data/raw_cache/` |
| Parser v2 | `parser/v2/` (pipeline, preprocessing, prompt, extractor, postprocessing, schema) | Filtert Nicht-Ticket-Anzeigen, baut LLM-Kontext, ruft Ollama mit Structured-Output-Schema auf, validiert und normalisiert das Ergebnis |
| Parser v1 | `parser/gemma_parser.py` | Vorgänger-Parser (gemma4:latest, `/api/generate`); bleibt als Rollback-Option dauerhaft erhalten |
| Status-Writer | `parser/v2/status_writer.py` | Schreibt während des Parsing-Laufs atomar eine JSON-Heartbeat-Datei (`.willhaben_status.json`); wird von GUI und Monitoring gelesen |
| Excel-Writer | `export/excel_writer.py` | Upsert-Logik (Willhaben-ID als Schlüssel) über 4 Sheets: Hauptübersicht, Review Queue, Archiv, Watchlist-Config; archiviert abgelaufene Events automatisch |
| OVP-Checker | `ovp/ovp_checker.py` | Prüft Original-Ticketpreise bei konfigurierten Anbietern per Playwright; nutzt Event-Level-Cache (`data/ovp_cache.json`) |
| GUI | `app/gui.py` + `app/tabs/` | tkinter-Hauptfenster mit 7 Tabs; startet Pipeline als Subprozess; liest Status-Datei per Polling |
| Backend | `app/backend/` (dashboard_aggregator, launchd_manager, status_monitor, subprocess_runner) | Entkoppelte Logik-Module ohne direkte tkinter-Abhängigkeit |
| Scheduler | launchd (macOS) | Täglicher Cron-Auftrag über `~/Library/LaunchAgents/{label}.plist`; konfigurierbar über GUI-Zeitplan-Tab |

---

## Pipeline-Fluss

```
┌──────────────┐
│   Scraping   │  playwright → willhaben.at/Tickets-Kategorie
│              │  ├─ Übersichtsseiten (bis 5 Seiten × 90 Anzeigen)
│              │  └─ Detailseite pro Anzeige
│              │  → data/raw_cache/{id}.json
└──────┬───────┘
       │
       ▼
┌──────────────┐
│Preprocessing │  is_category_page() → verwerfen
│  (v2 Filter) │  is_non_ticket_ad() → verwerfen
│              │  strip_nav_prefix() + build_context() → max 6000 Zeichen
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Prompt-Build │  prompt.build_prompt(context)
│              │  Enthält Aufgabenbeschreibung + JSON-Schema-Hinweis
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│ Ollama-Extraktion (extractor.py)     │
│                                      │
│  PRIMARY:   gemma3:27b               │
│             POST /api/chat           │
│             format=OLLAMA_FORMAT_SCHEMA
│             → garantiertes JSON      │
│                    │  Fehler         │
│                    ▼                 │
│  FALLBACK:  gemma4:26b               │
│             POST /api/generate       │
│             Text-Modus              │
│                    │  Fehler         │
│                    ▼                 │
│  EMERGENCY: gemma4:latest            │
│             POST /api/generate       │
│  (jede Stufe: tenacity 3 Versuche)  │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────┐
│Postprocessing│  parse_raw() → JSON aus Antwort extrahieren
│              │  validate() → Typ-Coercion, Enum-Checks
│              │  attach_metadata() → willhaben_id, modell, parse_dauer_ms …
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  OVP-Check  │  Pro Event (name+datum) einmalig:
│              │  Watchlist-Direktlink ODER Anbieter-Suchseiten
│              │  → originalpreis_pro_karte, ovp_quelle, ausverkauft
│              │  Ergebnis → data/ovp_cache.json
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Excel-Write  │  upsert_events() → Hauptübersicht, Review Queue
│              │  archive_expired() → abgelaufene Events → Archiv
│              │  → data/willhaben_markt.xlsx
└──────┬───────┘
       │
       ▼
┌──────────────┐
│Drive-Upload  │  export/gdrive_upload.py (optional, nicht kritisch)
│              │  → Google Drive (falls Credentials vorhanden)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│Status-Update │  StatusWriter.finish() / .fail()
│              │  → .willhaben_status.json  status="done"|"error"
└──────────────┘
```

---

## Parser v2 — Detail-Architektur

### Verarbeitungs-Pipeline

| Schritt | Modul | Beschreibung |
|---|---|---|
| 1. Category-Filter | `preprocessing.is_category_page()` | Erkennt Willhaben-Kategorieseiten am Titel-Pattern `^\d+ Anzeigen in` oder fehlendem Preis/Datum im Text |
| 2. Non-Ticket-Filter | `preprocessing.is_non_ticket_ad()` | Verwirft Anzeigen ohne Event-/Ticket-Keywords in Titel und Hauptbeschreibung |
| 3. Nav-Strip | `preprocessing.strip_nav_prefix()` | Entfernt führenden Willhaben-Navigationsblock (Login, Kategorien, Zähler) anhand einer Keyword-Denylist |
| 4. Context-Build | `preprocessing.build_context()` | Formatiert `Titel / Preis / Beschreibung (max 6000 Zeichen)` als LLM-Input-String |
| 5. Prompt | `prompt.build_prompt()` | Kombiniert Aufgabenanweisung mit Kontext; weist auf JSON-Schema und Confidence-Vergabe hin |
| 6. Extraktion | `extractor.extract()` | HTTP-Aufruf an Ollama; Fallback-Chain (siehe unten); tenacity-Retry bei Netzwerkfehlern |
| 7. Parse-raw | `postprocessing.parse_raw()` | Strukturierter Pfad (`{"events":[…]}`-Wrapper) für Primary-Modell; Regex-Fallback-Kette für Text-Modus-Modelle |
| 8. Validierung | `postprocessing.validate()` | Typ-Coercion für Floats/Ints; Enum-Prüfung für `confidence` und `kategorie`; ungültige Felder → sichere Defaults |
| 9. Metadaten | `postprocessing.attach_metadata()` | Ergänzt Willhaben-Metadaten (`willhaben_id`, `link`, Verkäuferinformationen) sowie v2-Felder (`modell`, `pipeline_version`, `parse_dauer_ms`) |
| 10. Cache | `pipeline._save_cache()` | Schreibt Events als `data/parse_cache_v2/{ad_id}.json`; beim nächsten Run wird der Cache-Hit übersprungen (kein Ollama-Aufruf) |

### Fallback-Chain

```
gemma3:27b  (PRIMARY)
  POST /api/chat
  format=OLLAMA_FORMAT_SCHEMA   ← Ollama Structured Output, garantiertes JSON
  temperature=0, num_predict=2048
  tenacity: 3 Versuche, exponentieller Backoff 2–10s
        │
        │ Fehler (Timeout, ConnectionError, HTTP-Fehler)
        ▼
gemma4:26b  (FALLBACK)
  POST /api/generate             ← Text-Modus (format-Parameter inkompatibel wg. Thinking-Bug)
  temperature=0.1, num_predict=2048
  Antwort: Freitext → Regex-Extraktion in parse_raw()
  tenacity: 3 Versuche
        │
        │ Fehler
        ▼
gemma4:latest  (EMERGENCY)
  POST /api/generate
  Identisch zu FALLBACK
        │
        │ Fehler
        ▼
  ("", EMERGENCY_MODEL, 0, fallback_used=True)
  → postprocessing erzeugt EMPTY_EVENT mit confidence="niedrig"
```

Wenn `model_override` gesetzt ist, wird die Fallback-Chain übersprungen und nur das gewählte Modell versucht (kein weiterer Fallback bei Fehler).

### Caching-Strategie

**Parse-Cache v2** (`data/parse_cache_v2/{ad_id}.json`):
- Eine Datei pro Willhaben-ID, Inhalt: JSON-Array der extrahierten Events
- Wird bei jedem `parse_ads(use_cache=True)`-Aufruf zuerst geprüft
- Explizite Invalidierung: Datei löschen oder `--test-batch N` (übergibt `use_cache=False`)
- Kein TTL — Cache-Einträge bleiben unbegrenzt gültig

**Raw-Cache** (`data/raw_cache/{ad_id}.json`):
- Scraper-Rohausgabe (alle Felder der Anzeige inkl. `text_komplett`)
- Wird vom Scraper bei jedem Lauf überschrieben (kein TTL, letzte Version gewinnt)
- Dient als Eingabe für `--test-batch` ohne erneuten Scraper-Lauf

**OVP-Cache** (`data/ovp_cache.json`):
- Key: `{event_name.lower()}|{event_datum}` — ein einziger, flacher JSON-Dict
- Einmal gefundener OVP wird nicht erneut abgerufen
- Kein TTL — manuelle Invalidierung durch Datei löschen

---

## GUI-Architektur

### Tab-Struktur

| Tab | Klasse | Verantwortung |
|---|---|---|
| Engine | `app/tabs/engine.EngineTab` | Modell-Auswahl (Combobox), Max-Anzeigen-Spinner, Test-Batch-Aufruf mit Live-Log-Output; startet Pipeline als Subprozess via `subprocess_runner` |
| Zeitplan | `app/tabs/zeitplan.ZeitplanTab` | launchd-Konfiguration: Stunde/Minute, Label, Aktiviert-Checkbox, Scraping-Tiefe (max_age_days); schreibt/löscht `~/Library/LaunchAgents/{label}.plist` via `launchd_manager` |
| Status | `app/tabs/status.StatusTab` | Live-Monitoring: liest `.willhaben_status.json` alle 2 Sekunden per `after()`-Polling; zeigt Fortschritt, Modell, Ø-Dauer, Fehler-Count; kann Pipeline direkt starten |
| Dashboard | `app/tabs/dashboard.DashboardTab` | Markt-Übersicht: aggregiert Excel-Sheet via `dashboard_aggregator`; trennt Privat- und Händler-Angebote; zeigt Min/Avg/Max-Preise und Marge % gegenüber OVP |
| Anbieter (OVP) | `gui.App._build_providers_tab()` | Freiform-Editor für Such-URL-Templates (`{event}`-Platzhalter); direkt in `config.json` gespeichert |
| Watchlist | `gui.App._build_watchlist_tab()` | Zeilenbasierter Editor: `Event-Name | OVP: 89.90 | Link: https://…`; Link überspringt automatische Anbieter-Suche |
| Log | `gui.App._build_log_tab()` | Scrollbares Dark-Theme-Protokoll; wird per `_append_log()` aus Pipeline-Callbacks gefüllt |

### Backend-Entkopplung

Die Module unter `app/backend/` enthalten keine tkinter-Importe und sind damit unabhängig testbar:

| Modul | Abstraktion |
|---|---|
| `dashboard_aggregator.py` | Liest Excel-Sheet `Angebote` mit pandas; `aggregate()` gibt einen pandas-DataFrame zurück — GUI-unabhängig |
| `launchd_manager.py` | Rendert plist-Template, ruft `launchctl load/unload` per subprocess auf; gibt `(bool, str)`-Tupel zurück |
| `status_monitor.py` | Liest `.willhaben_status.json`; `read_status()`, `is_running()`, `format_progress()`, `avg_duration_ms()` als pure functions |
| `subprocess_runner.py` | Startet `main.py --once …` als `subprocess.Popen`; optionaler Stdout-Reader-Thread ruft `log_callback` auf; `is_running()` und `stop()` (SIGTERM/SIGKILL) |

---

## Daten-Modell

### Excel-Sheets (`data/willhaben_markt.xlsx`)

| Sheet | Inhalt | Zeilen (aktuell, ca.) |
|---|---|---|
| Hauptübersicht | Alle geparsten Events; 28 Spalten (24 Basis + 4 v2-Felder); Willhaben-ID als Upsert-Schlüssel | ~483 |
| Review Queue | Events mit `confidence=niedrig` oder `review_nötig=True`; 9 Spalten inkl. Notiz-Feld für manuelle Sichtung | ~32 |
| Archiv | Abgelaufene Events (Datum < heute); identisches Schema wie Hauptübersicht; werden nicht mehr aktualisiert | ~191 |
| Watchlist-Config | Konfigurierbare Watchlist mit Event-Name, OVP-Preis (optional) und Direktlink (optional); 3 Spalten | ~1 |

**Hauptübersicht-Spalten (28):** `scan_datum`, `willhaben_link`, `willhaben_id`, `verkäufer_id`, `verkäufername`, `verkäufertyp`, `mitglied_seit`, `event_name`, `event_datum`, `venue`, `stadt`, `kategorie`, `anzahl_karten`, `angebotspreis_gesamt`, `preis_ist_pro_karte`, `angebotspreis_pro_karte` (berechnet), `originalpreis_pro_karte`, `ovp_quelle`, `marge_eur` (berechnet), `marge_pct` (berechnet), `ausverkauft`, `watchlist`, `confidence`, `review_nötig`, `confidence_grund`, `modell`, `pipeline_version`, `parse_dauer_ms`.

Hinweis: `dashboard_aggregator.py` liest das Sheet unter dem Namen `"Angebote"`. Das tatsächliche Sheet heißt `"Hauptübersicht"` — dies ist ein bekannter Mismatch (siehe Bekannte Architektur-Schwächen).

### Status-File Schema (`.willhaben_status.json`)

```json
{
  "run_id":            "uuid4-String — eindeutig pro Pipeline-Lauf",
  "started_at":        "ISO-8601 UTC — Startzeitpunkt des Laufs",
  "model":             "z.B. gemma3:27b — verwendetes Primärmodell",
  "total":             250,
  "current":           42,
  "current_id":        "Willhaben-ID der aktuell verarbeiteten Anzeige",
  "current_title":     "Titel der aktuell verarbeiteten Anzeige (max 80 Zeichen)",
  "last_10_durations": [1230, 950, 1100],
  "errors_count":      0,
  "last_error":        null,
  "status":            "running | done | error"
}
```

Die Datei wird atomar geschrieben (`.json.tmp` → rename), um korrupte Lesezugriffe aus der GUI zu vermeiden.

### Parse-Cache Schema (`data/parse_cache_v2/{ad_id}.json`)

Jede Datei enthält ein JSON-Array mit einem oder mehreren Event-Objekten (eine Anzeige kann mehrere Events enthalten, z.B. bei Paketen):

```json
[
  {
    "event_name":              "Linkin Park Wien",
    "event_datum":             "2026-06-09",
    "venue":                   "Ernst-Happel-Stadion",
    "stadt":                   "Wien",
    "kategorie":               "Stehplatz | Sitzplatz | VIP | Front-of-Stage | Gemischt | Unbekannt",
    "anzahl_karten":           2,
    "angebotspreis_gesamt":    220.0,
    "preis_ist_pro_karte":     false,
    "originalpreis_pro_karte": 89.9,
    "confidence":              "hoch | mittel | niedrig",
    "confidence_grund":        "Freitext",
    "willhaben_id":            "1234567890",
    "willhaben_link":          "https://www.willhaben.at/iad/kaufen-und-verkaufen/d/…",
    "verkäufertyp":            "Privat | Händler",
    "verkäufername":           "…",
    "verkäufer_id":            "…",
    "mitglied_seit":           "…",
    "preis_roh":               "220 €",
    "parsed_at":               "2026-04-17T23:45:12.123456",
    "modell":                  "gemma3:27b",
    "pipeline_version":        "v2.0",
    "parse_dauer_ms":          1340
  }
]
```

---

## Deployment

### launchd (macOS)

Der Scheduler verwendet launchd anstelle von cron oder dem Python-`schedule`-Daemon.

| Parameter | Wert |
|---|---|
| Plist-Pfad | `~/Library/LaunchAgents/{label}.plist` (Standard-Label: `com.willhaben.analyse`) |
| Plist-Template | `app/templates/launchd.plist.template` |
| Ausführungszeit | Konfigurierbar über GUI-Tab (Standard: 02:00 Uhr täglich) |
| Python-Interpreter | `.venv/bin/python3` (bevorzugt); Fallback: `sys.executable` |
| Aufruf | `python3 main.py --once --parser-version=v2 --model=gemma3:27b [--max-listings=N]` |
| Ollama-Voraussetzung | Ollama muss zum Ausführungszeitpunkt laufen und `gemma3:27b` als Modell geladen haben (Modell-Volume ~18 GB im VRAM/Unified Memory) |

Installation und Deinstallation erfolgen über den GUI-Zeitplan-Tab oder manuell per `launchctl load/unload`.

### Konfiguration (`config.json`)

| Feld | Typ | Beschreibung |
|---|---|---|
| `schedule.scrape_interval_minutes` | int | Intervall für den Python-`schedule`-Daemon-Modus (Legacy, nicht für launchd relevant); Standard: 360 |
| `schedule.enabled` | bool | Aktiviert den internen Daemon-Modus (`--daemon`); launchd läuft unabhängig davon |
| `ovp_search_urls` | string[] | URL-Templates für OVP-Suche; `{event}` wird durch den Event-Namen ersetzt; 10 österreichische Anbieter vorkonfiguriert |
| `watchlist` | object[] | Pro Eintrag: `event_name` (Pflicht), `ovp_preis` (optional, float), `ovp_link` (optional, Direktlink überspringt Suche) |
| `max_age_days` | int | Maximales Anzeigenalter in Tagen beim Scraping (Filter in Scraper); Standard: 2 |
| `first_run_max_age_days` | int | Erweitertes Fenster beim allerersten Lauf (leerer raw_cache); Standard: 3 |
| `export_path` | string | Pfad zur Excel-Ausgabedatei; Standard: `data/willhaben_markt.xlsx` |
| `log_level` | string | Python-Logging-Level (`DEBUG`, `INFO`, `WARNING`); Standard: `INFO` |
| `max_listings` | int \| null | Maximale Anzahl zu parsender Anzeigen pro Lauf; `null` = keine Begrenzung |
| `model` | string | Primärmodell für GUI-Starts; Standard: `gemma3:27b` |
| `launchd.label` | string | launchd-Job-Label (= Plist-Dateiname ohne `.plist`) |
| `launchd.hour` | int | Ausführungsstunde (0–23) |
| `launchd.minute` | int | Ausführungsminute (0–59) |

---

## Bekannte Architektur-Schwächen (aus Audit Phase A/B)

1. **Dashboard-Sheet-Name-Mismatch**: `dashboard_aggregator.py` liest `sheet_name="Angebote"`, das tatsächliche Sheet in der Excel-Datei heißt `"Hauptübersicht"`. Das Dashboard-Tab zeigt daher immer einen leeren DataFrame, solange kein Sheet `"Angebote"` existiert.

2. **Blocking I/O in async-Kontext**: `extractor.py` verwendet synchrones `requests.post()` innerhalb von `parse_ads()`, das selbst synchron ist, aber aus `asyncio.run()` in `main.py` heraus im gleichen Thread aufgerufen werden könnte. Bei Nutzung des Daemon-Modus mit `asyncio.run(scrape())` gefolgt von synchronem `parse_ads()` entsteht kein technisches Problem, die Architektur ist aber inkonsistent (sync/async gemischt ohne explizites Executor-Muster).

3. **Keine Log-Rotation**: `logs/pipeline.log` wird unbegrenzt mit `logging.FileHandler` beschrieben. Bei täglichen Läufen wächst die Datei kontinuierlich; kein `RotatingFileHandler` konfiguriert.

4. **Ollama als Single Point of Failure**: Die gesamte Parsing-Stufe hängt an einem lokalen Ollama-Prozess auf `localhost:11434`. Fällt Ollama aus (Absturz, Modell nicht geladen, Speicher erschöpft), liefert die Fallback-Chain nach 3×3 Versuchen nur `EMPTY_EVENT`-Einträge mit `confidence=niedrig`. Es gibt keinen Alerting-Mechanismus.

5. **OVP-Cache ohne TTL**: `data/ovp_cache.json` wird nie automatisch invalidiert. Geänderte Original-Preise oder ausverkaufte Events werden nicht erneut geprüft, bis die Cache-Datei manuell gelöscht wird.

6. **Kein strukturiertes Fehler-Tracking**: `stats["errors"]` in `run_pipeline()` ist eine einfache String-Liste; keine strukturierten Fehlerobjekte, keine Aggregation über mehrere Läufe hinweg.

---

## Versionierung und Rollback

Zwei Parser-Versionen koexistieren dauerhaft im Repository:

| Version | Modul | Cache-Verzeichnis | Modell | API |
|---|---|---|---|---|
| v2 (Standard seit Phase 5) | `parser/v2/` | `data/parse_cache_v2/` | `gemma3:27b` | `/api/chat` + Structured Output |
| v1 (Rollback) | `parser/gemma_parser.py` | `data/parse_cache/` | `gemma4:latest` | `/api/generate` |

**Rollback auf v1:**

```bash
# Einmaliger Run mit v1-Parser
python main.py --once --parser-version v1

# GUI-gestartete Pipeline: im Engine-Tab Modell auf gemma4:latest setzen
# und parser_version in config.json auf "v1" setzen

# Zum Testen ohne Excel-Write
python main.py --test-batch 5 --parser-version v1
```

v1-Cache (`data/parse_cache/`) und v1-Modul (`parser/gemma_parser.py`) werden nicht gelöscht. Ein Wechsel zwischen den Versionen ist jederzeit ohne Datenverlust möglich, da beide Caches getrennte Verzeichnisse nutzen.
