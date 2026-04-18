# Onboarding: WillhabenAnalyse v2.1

## Voraussetzungen

| Anforderung | Version | Hinweis |
|-------------|---------|---------|
| macOS | 12 Monterey oder neuer | launchd-Integration erfordert macOS |
| Python | 3.11+ | `python3 --version` prüfen |
| Git | beliebig | für `git clone` |
| Ollama | aktuell | [ollama.com](https://ollama.com) — muss als Dienst laufen |
| Modell `gemma3:27b` | — | ~17 GB Download beim ersten `pull` |
| Festplattenspeicher | ~20 GB | Modell + raw_cache + Excel |

Ollama muss während des Betriebs als Hintergrundprozess laufen. Ob er läuft, lässt sich prüfen mit:
```bash
ollama list
```

---

## Schnell-Setup (5 Minuten)

```bash
# 1. Repository klonen
git clone <repo-url> WillhabenAnalyse
cd WillhabenAnalyse

# 2. Virtuelle Umgebung anlegen und aktivieren
python3 -m venv .venv
source .venv/bin/activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. Ollama-Modell herunterladen (einmalig, ~17 GB)
ollama pull gemma3:27b

# 5. Smoke-Test: 3 Anzeigen aus dem raw_cache parsen
#    (Hinweis: raw_cache muss bereits vorhanden sein — siehe "Ersten Lauf ausführen")
python main.py --test-batch 3
```

Wenn `--test-batch` meldet "Kein raw_cache vorhanden", zuerst einen vollständigen Lauf durchführen:
```bash
python main.py --once --dry-run
```

---

## Verzeichnis-Struktur

```
WillhabenAnalyse/
├── main.py                     # Einstiegspunkt: CLI, Orchestrator, Scheduling
├── config.json                 # Laufzeitkonfiguration (Zeitplan, Pfade, Modelle)
├── requirements.txt            # Python-Abhängigkeiten
│
├── parser/
│   ├── v2/                     # Aktueller Parser (Standard)
│   │   ├── pipeline.py         # Öffentliche API: parse_ad(), parse_ads()
│   │   ├── schema.py           # Pydantic-Modelle: EventResult, ParseResponse
│   │   ├── extractor.py        # Ollama-Aufruf mit Retry (tenacity)
│   │   ├── postprocessing.py   # JSON-Parsing, Validierung, Metadaten
│   │   ├── preprocessing.py    # Vorfilter (Category-Pages, Non-Tickets)
│   │   ├── prompt.py           # Prompt-Baustein
│   │   └── status_writer.py    # StatusWriter: Heartbeat-Datei
│   └── gemma_parser.py         # Parser v1 (Rollback, nicht löschen)
│
├── scraper/
│   └── willhaben_scraper.py    # Playwright-basierter Scraper
│
├── ovp/
│   └── ovp_checker.py          # OVP-Check gegen Ticketing-Anbieter
│
├── export/
│   └── excel_writer.py         # Upsert-Logik, 4 Sheets, Farbgebung
│
├── app/
│   ├── gui.py                  # tkinter-GUI-Einstiegspunkt
│   ├── tabs/
│   │   ├── engine.py           # Tab "Pipeline": Start/Stop, Log-Ausgabe
│   │   ├── status.py           # Tab "Status": Fortschrittsanzeige
│   │   ├── dashboard.py        # Tab "Dashboard": Marktübersicht
│   │   └── zeitplan.py         # Tab "Zeitplan": launchd konfigurieren
│   ├── backend/
│   │   ├── status_monitor.py   # Liest .willhaben_status.json
│   │   ├── dashboard_aggregator.py  # Aggregiert Excel-Daten für Dashboard
│   │   ├── subprocess_runner.py    # Startet Pipeline als Subprocess
│   │   └── launchd_manager.py      # macOS launchd plist erzeugen/installieren
│   └── templates/
│       └── launchd.plist.template  # Vorlage für launchd-Job
│
├── eval/
│   ├── run_eval.py             # Eval-Suite ausführen
│   ├── gold_standard.json      # 25 hand-verifizierte Anzeigen
│   └── results/                # Eval-Ergebnisse (JSON)
│
├── data/
│   ├── raw_cache/              # Rohdaten vom Scraper (<id>.json)
│   ├── parse_cache_v2/         # Parse-Ergebnisse v2 (<id>.json)
│   ├── parse_cache/            # Parse-Ergebnisse v1 (nicht löschen)
│   └── willhaben_markt.xlsx    # Haupt-Ausgabedatei
│
├── tests/                      # pytest-Tests
├── logs/
│   └── pipeline.log            # Laufzeit-Log
├── docs/                       # Diese Dokumentation
└── .willhaben_status.json      # Heartbeat-Datei (während Parsing-Lauf)
```

---

## Ersten Lauf ausführen

### Schritt 1 — Dry-Run (empfohlen als erstes)

Scrapt und parst, schreibt aber **nichts** in Excel oder Google Drive:
```bash
python main.py --once --dry-run
```

Die Ausgabe auf stdout zeigt das Stats-Dict:
```json
{
  "scraped": 234,
  "parsed_events": 187,
  "ovp_checked": 42,
  "excel_inserted": 0,
  "excel_updated": 0,
  "errors": []
}
```

### Schritt 2 — Parser isoliert testen (`--test-batch`)

Parst die ersten N Anzeigen aus dem lokalen `data/raw_cache/` ohne Scraping und ohne Excel-Write. Nützlich zum Testen von Modell-Wechseln oder Prompt-Änderungen:
```bash
python main.py --test-batch 5
python main.py --test-batch 5 --model gemma4:26b
```

Gibt eine kompakte JSON-Liste auf stdout aus mit den Feldern `event_name`, `event_datum`, `confidence`, `modell`, `pipeline_version`, `parse_dauer_ms`, `originalpreis_pro_karte`, `angebotspreis_gesamt`.

### Schritt 3 — Vollständiger Lauf (`--once`)

Scrapt, parst, prüft OVP, schreibt Excel:
```bash
python main.py --once
```

Mit Anzeigen-Limit (nützlich für erste Tests):
```bash
python main.py --once --max-listings 20
```

### Schritt 4 — Scheduler starten (`--daemon`)

Startet eine Endlosschleife die die Pipeline regelmäßig ausführt. Intervall wird aus `config.json → schedule.scrape_interval_minutes` gelesen (Standard: 360 Minuten). Scheduling muss in der config aktiviert sein:
```json
{ "schedule": { "enabled": true, "scrape_interval_minutes": 360 } }
```
```bash
python main.py --daemon
```

---

## Tests ausführen

```bash
# Alle Tests
.venv/bin/python -m pytest tests/ -v

# Nur Parser-v2-Tests
.venv/bin/python -m pytest tests/test_v2_pipeline.py tests/test_v2_extractor.py -v

# Nur CLI-Tests
.venv/bin/python -m pytest tests/test_main_cli.py -v
```

**Was die Tests prüfen:**
- `test_main_cli.py` — CLI-Flags vorhanden, ungültige Werte ergeben Exit-Code != 0, `--max-listings` mit String-Wert schlägt fehl.
- `test_v2_pipeline.py` — Cache-Logik, StatusWriter-Integration, Fehlerbehandlung pro Anzeige.
- `test_v2_extractor.py` — Ollama-Aufruf, Retry-Logik, Fallback-Chain.
- `test_v2_postprocessing.py` — JSON-Parsing, Validierung, Metadaten-Anhang.
- `test_v2_preprocessing.py` — Category-Page-Filter, Non-Ticket-Filter.
- `test_v2_status_writer.py` — Atomares Schreiben, `finish()`, `fail()`, `error()`.
- `test_backend_*.py` — `status_monitor`, `dashboard_aggregator`, `subprocess_runner`, `launchd_manager`.
- `test_excel_new_columns.py` — v2.0-Spalten in Excel vorhanden.

**Was die Tests NICHT prüfen:**
- Echter Ollama-Aufruf gegen ein laufendes Modell (Tests mocken `extractor.extract()`).
- Echtes Playwright-Scraping (kein Test für `scraper/`).
- Google Drive Upload (`export/gdrive_upload.py`).
- GUI-Rendering (nur Logik-Tests für Tab-Backend-Module).
- End-to-End-Pipeline mit echter Excel-Ausgabe und echtem Netz.

---

## GUI starten

```bash
python main.py --gui
# oder ohne Flag (Standardverhalten):
python main.py
```

Die GUI besteht aus vier Tabs:

| Tab | Datei | Funktion |
|-----|-------|----------|
| **Pipeline** | `app/tabs/engine.py` | Pipeline manuell starten/stoppen, Modell und `--max-listings` wählen, Log-Ausgabe in Echtzeit |
| **Status** | `app/tabs/status.py` | Fortschrittsbalken, aktuelle Anzeige, Durchschnittsdauer — liest `.willhaben_status.json` |
| **Dashboard** | `app/tabs/dashboard.py` | Marktübersicht aggregiert nach Event/Datum/Kategorie (Privat vs. Händler, Margen) |
| **Zeitplan** | `app/tabs/zeitplan.py` | launchd-Job konfigurieren (Uhrzeit, Modell, Max-Listings), installieren/deinstallieren |

---

## Häufige Einsteiger-Fehler

**Ollama nicht gestartet**
```
ConnectionRefusedError: ... localhost:11434
```
Lösung: `ollama serve` im Terminal starten oder Ollama.app öffnen. Danach prüfen mit `ollama list`.

**Falsches venv / `ModuleNotFoundError`**
Wenn `import playwright` oder andere Module fehlen, läuft Python außerhalb des venv. Lösung:
```bash
source .venv/bin/activate
which python  # muss auf .venv/bin/python zeigen
```

**`Playwright nicht installiert` / Browser fehlt**
Nach `pip install -r requirements.txt` müssen die Playwright-Browser einmalig heruntergeladen werden:
```bash
.venv/bin/playwright install chromium
```

**`Kein raw_cache vorhanden` bei `--test-batch`**
`--test-batch` liest aus `data/raw_cache/`. Der Cache wird erst durch einen echten Scraping-Lauf befüllt. Zuerst ausführen:
```bash
python main.py --once --dry-run
```

**`config.json` fehlt oder ungültig**
`load_config()` fällt bei fehlendem oder defektem `config.json` auf hartcodierte Defaults zurück (`scrape_interval_minutes: 120`, `schedule.enabled: false`). Der `export_path` zeigt dann auf `data/willhaben_analyse.xlsx` statt auf den in der Datei konfigurierten Wert `data/willhaben_markt.xlsx`. Das führt dazu, dass eine zweite Excel-Datei angelegt wird.

**launchd-Installation schlägt fehl**
`launchctl load` erfordert, dass der Python-Pfad absolut und korrekt ist. Den Pfad zum venv-Python prüfen:
```bash
which python  # muss absoluter Pfad sein, z.B. /Users/name/WillhabenAnalyse/.venv/bin/python
```

**Dashboard-Tab zeigt keine Daten**
Bekannter Bug: `dashboard_aggregator.load_excel()` liest Sheet `"Angebote"`, das tatsächliche Sheet heißt aber `"Hauptübersicht"`. Das Dashboard bleibt deshalb leer bis dieser Bug behoben ist (siehe `docs/API.md` — Bekannte API-Inkonsistenzen).

---

## Code-Architektur verstehen

Der empfohlene Einstiegspunkt für neue Entwickler:

**1. `parser/v2/pipeline.py`** — Öffentliche API (`parse_ad`, `parse_ads`), Cache-Logik, StatusWriter-Integration. Zeigt den Gesamtablauf eines Parsing-Laufs in ~130 Zeilen.

**2. `parser/v2/extractor.py`** — Wie Ollama aufgerufen wird: `/api/chat` mit Structured Output, tenacity-Retry (3 Versuche), Fallback-Chain `gemma3:27b → gemma4:26b → gemma4:latest`.

**3. `parser/v2/postprocessing.py`** — Was nach dem Ollama-Aufruf passiert: JSON aus dem Modell-Response extrahieren, mit Pydantic validieren, Metadaten anhängen.

**4. `parser/v2/preprocessing.py`** — Welche Anzeigen vor dem Ollama-Aufruf herausgefiltert werden (Category-Pages, Non-Ticket-Anzeigen). Hier kann man am schnellsten neue Filter hinzufügen.

**5. `parser/v2/schema.py`** — Die Pydantic-Modelle `EventResult` und `ParseResponse`. Jede Änderung am Output-Schema muss hier beginnen.

**6. `main.py`** — Orchestrierung der Schritte 1–4, CLI-Interface, Scheduling.

**7. `export/excel_writer.py`** — Upsert-Logik (nie duplizieren), Spalten-Definition (`MAIN_COLUMNS`), Farbgebung, Archivierung.

Für die GUI: `app/gui.py` als Einstieg, dann die jeweiligen Tab-Dateien in `app/tabs/`.

---

## Bekannte Bugs die Einsteiger verwirren könnten

**Dashboard leer (Sheet-Name-Bug)**
`dashboard_aggregator.load_excel()` öffnet `sheet_name="Angebote"`, aber das Sheet heißt `"Hauptübersicht"`. Die Aggregation arbeitet deshalb immer auf einem leeren DataFrame. Das Dashboard-Tab zeigt keine Tabelle an. Dieser Bug existiert in v2.1 und ist noch nicht behoben.

**`errors`-Feld zeigt immer `0` in der Status-Datei**
Selbst wenn Parsing-Fehler aufgetreten sind, steht in `.willhaben_status.json` immer `"errors_count": 0`. Die Ursache: `parse_ads()` ruft `StatusWriter.error(str(exc))` nur für Ausnahmen innerhalb des `parse_ad()`-Aufrufs auf, nicht für die `stats["errors"]`-Liste von `run_pipeline()`. Fehler sind trotzdem in `logs/pipeline.log` sichtbar.

**`kategorie` meist `"Unbekannt"` in Produktionsdaten**
Das Modell gibt für die meisten realen Anzeigen `"Unbekannt"` als Kategorie zurück, da Ticketverkäufer die Kategorie selten explizit nennen. Das ist kein Programmierfehler, sondern eine Limitation der Eingabedaten. Die Eval-Accuracy von 86,7% wurde auf kurierten Gold-Standard-Einträgen gemessen und ist im Produktionsbetrieb nicht repräsentativ.

**v2.0-Spalten fehlen in alten Excel-Dateien**
Wenn eine Excel-Datei vor dem v2.0-Update angelegt wurde, fehlen die Spalten `confidence_grund`, `modell`, `pipeline_version`, `parse_dauer_ms`. `excel_writer.py` fügt die Spalten nicht automatisch nach. Die Datei muss manuell gelöscht werden damit `upsert_events()` eine neue Datei mit vollständigem Schema anlegt.
