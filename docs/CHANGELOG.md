# Changelog: WillhabenAnalyse

Alle wesentlichen Änderungen werden in dieser Datei dokumentiert.
Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.1.0] — 2026-04-17/18

Entwickelt auf Branch `claude/xenodochial-hofstadter-16be42`, gemergt nach `main` als
Commit `43869b4`. Basis: v2.0 Parser (`9eb4a2e`). 8 Commits, 143/143 Tests grün.

### Hinzugefügt

**Parser / Kern**

- `parser/v2/status_writer.py` — neues Modul `StatusWriter` mit atomarem JSON-Heartbeat:
  schreibt `.willhaben_status.json` via `.tmp`-Datei + `os.rename()` (atomar, kein halbgeschriebenes JSON bei Absturz)
- Status-File-Schema: `run_id`, `started_at`, `model`, `total`, `current`, `current_id`,
  `current_title`, `last_10_durations`, `errors_count`, `last_error`, `status`
- `--max-listings N` CLI-Parameter in `main.py` — begrenzt Scraping und Parsing auf N Anzeigen
  (Early-Stop auf Übersichtsseiten und im Detail-Loop des Scrapers)

**Backend-Module (`app/backend/`)**

- `status_monitor.py` — liest `.willhaben_status.json`; stellt `read_status()`, `is_running()`,
  `format_progress()`, `avg_duration_ms()` bereit
- `launchd_manager.py` — erzeugt macOS Launch-Agent Plist aus Template; Methoden:
  `generate_plist()`, `install_plist()`, `uninstall_plist()`, `is_installed()`
- `dashboard_aggregator.py` — Pandas-Aggregation aus Excel; `load_excel()`, `aggregate()`,
  `export_csv()`
- `subprocess_runner.py` — startet Pipeline als Hintergrundprozess; `start_pipeline()`,
  `is_running()`, `stop()`
- `pandas>=2.0.0` zu `requirements.txt` hinzugefügt

**Templates**

- `app/templates/launchd.plist.template` — Apple plist XML mit `str.format()`-Platzhaltern:
  `{LABEL}`, `{PYTHON_PATH}`, `{PROJECT_DIR}`, `{MODEL}`, `{MAX_LISTINGS_ARG}`, `{HOUR}`,
  `{MINUTE}`

**GUI-Tabs (`app/tabs/`)**

- `EngineTab` — Modell-Dropdown, Max-Anzeigen-Eingabe, Test-Batch mit Log-Stream
- `ZeitplanTab` — Uhrzeit (Stunde/Minute), launchd installieren/deinstallieren; bevorzugt
  `.venv/bin/python3`, Fallback auf `sys.executable`
- `StatusTab` — Live-Monitoring mit Auto-Refresh (2 s), Pipeline starten/stoppen
- `DashboardTab` — Marktanalyse-Tabelle mit Event-Filter, Sortierung, CSV-Export;
  Spalten: Event, Kategorie, Datum, Venue, Stadt, Privat_Anzahl, Privat_Min, Privat_Avg,
  Privat_Max, Haendler_Anzahl, Haendler_Min, Haendler_Avg, Haendler_Max, OVP,
  Marge_Haendler_Pct, Marge_Privat_Pct

**Branding**

- `MikesMarkt.app` — Anwendungsname und Fenster-Titel umbenannt

**Zeitplan-Tab**

- Scraping-Tiefe-Spinner im Zeitplan-Tab (Commit `636283f`)

### Geändert

- `app/gui.py` refaktoriert: 303 → 186 Zeilen; 7-Tab-Struktur (Engine, Zeitplan, Status,
  Dashboard, Anbieter, Watchlist, Log) statt monolithischem Einzelfenster
- GUI zu Tabbed-Interface migriert — alle Funktionen in dedizierten Tab-Klassen gekapselt
- launchd venv-Pfad: `ZeitplanTab._install()` bevorzugt `.venv/bin/python3` statt
  `sys.executable`, um Shell-Aktivierungs-Abhängigkeit zu vermeiden

### Behoben

- `ValueError`-Schutz in `EngineTab._save_settings()` bei leerem Zahlen-Input
- Guard gegen doppelten Subprocess-Start in `StatusTab` und `EngineTab` (concurrent-spawn-Guard)
- `after_cancel()` in `StatusTab.destroy()` verhindert `TclError` beim Schließen des Fensters
- Early-Stop nach `max_listings` im Scraper: sowohl auf Übersichtsseiten als auch im
  Detail-Loop (Commit `ee5eae4`)
- `stderr`-Kommentar-Fix im Subprocess-Modul
- `import math` aus innerer Schleife an Modul-Kopf verschoben
- `if max_listings:` → `if max_listings is not None:` (falsy-Bug: N=0 wurde fälschlich
  wie "kein Limit" behandelt)
- `try/finally` um `parse_ads()`-Schleife: `StatusWriter.fail()` wird auch bei Ausnahmen
  aufgerufen
- `PRIMARY_MODEL`-Konstante statt hardcoded String

### Bekannte offene Bugs (v2.1)

- `dashboard_aggregator.load_excel()` liest Sheet `"Angebote"` statt `"Hauptübersicht"` —
  Dashboard dauerhaft leer (CRITICAL)
- Spalten-Konstanten im Aggregator stimmen nicht mit Excel-Headern überein (CRITICAL)
- `app/tabs/status.py` liest `status.get("errors", 0)` statt `"errors_count"` — GUI
  zeigt immer 0 Fehler (CRITICAL)
- Statischer `.tmp`-Dateiname in `StatusWriter` kann bei Parallelausführung zu Race Condition
  führen (HIGH)

---

## [2.0.0] — 2026-04-15/16

Parser v2 mit `gemma3:27b` und Ollama Structured Output. Basis: v1.x (`gemma4:8B` Parser).

### Hinzugefügt

**Parser v2 (`parser/v2/`)**

- `gemma3:27b` (27B-Modell) als primäres Parsing-Modell
- Ollama Structured Output via `/api/chat` — garantiert schema-konformes JSON, 100 % Parse-Rate
- Schema-Definition (`parser/v2/schema.py`) mit vollständigem Event-Datenmodell
- Dreistufige Fallback-Chain: `gemma3:27b` → `gemma4:26b` → `gemma4:latest`
- `tenacity`-Retry-Logik: 3 Versuche mit exponential Backoff bei Ollama-Timeouts
- Category-Pages-Filter: Kategorie-Seiten werden als Non-Ticket klassifiziert und übersprungen
- Non-Ticket-Preprocessing-Filter: Anzeigen ohne Ticket-Kontext werden vor dem LLM-Aufruf
  ausgesiebt

**Eval-Suite**

- `eval/run_eval.py` — Eval-Pipeline für Parser v1 und v2
- `eval/gold_standard.json` — 25 hand-verifizierte Anzeigen (händler_einfach ×5,
  privat_einfach ×10, händler_multi ×5, edge_case ×3, non_ticket ×2)
- Eval-Ergebnisse: JSON-Parse-Rate 100 %, Event-Count-Accuracy 92 % (23/25),
  event_name 100 %, originalpreis_pro_karte 96,7 %, event_datum 93,3 %

**CLI**

- `--parser-version v2` / `--parser-version v1` — Modell-Selektion
- `--model gemma3:27b` — Modell-Override (nur v2)
- `--test-batch N` — N raw_cache-Einträge parsen ohne Excel-Write
- `--dry-run` — komplette Pipeline ohne Excel- und Drive-Write

**Excel-Ausgabe**

- Neue v2-Metadaten-Spalten: `modell`, `pipeline_version`, `parse_dauer_ms`,
  `confidence_grund`

### Geändert

- Modell: `gemma4:latest` (8B) → `gemma3:27b` (27B)
- API-Endpunkt: `/api/generate` → `/api/chat`
- JSON-Parse-Rate: ~85 % (v1) → 100 % (v2, Structured Output)
- Durchschnittliche Parse-Latenz: ~25 s (v1) → ~83–90 s (v2)

### Behoben

- Instabile JSON-Extraktion aus Freitext-Antworten (v1: ~15 % Parse-Fehler → v2: 0 %)
- Multi-Ticket-Kategorie-Bug: Anzeigen mit mehreren Event-Kategorien wurden falsch
  klassifiziert

---

## [1.x] — 2026-04-14 und früher

Erste produktive Implementierung. Kein separater Feature-Branch; Entwicklung direkt auf `main`.

### Enthalten

- Scraper für willhaben.at (Ticket-Kategorie, Paginierung, raw_cache als JSON per ID)
- Parser v1 (`parser/gemma_parser.py`) mit `gemma4:latest` (8B) via `/api/generate`
- Freitext-JSON-Extraktion mit Greedy-Regex (fehleranfällig, ~85 % Parse-Rate)
- Excel-Export (`data/willhaben_analyse.xlsx`) mit Basis-Spalten
- Google-Drive-Sync (`export/gdrive_upload.py`) für raw_cache und Excel
- OVP-Pipeline: Parser-OVP beibehalten, Preis-pro-Karte-Berechnung, Drive-Pfad
- Prompt-Optimierung: Few-Shot-Beispiele, OVP-Muster, Multi-Kategorie-Fix

### Bekannte Limitierungen (v1)

- `gemma4:8B` mit `/api/generate` liefert Freitext statt JSON → ~15 % Parse-Fehler
- Kein Retry bei Ollama-Timeouts
- Kein Pre-Filter für Non-Ticket-Anzeigen
- Keine Eval-Suite, kein Qualitäts-Nachweis
- Keine GUI, kein Status-Monitoring, kein launchd-Support
