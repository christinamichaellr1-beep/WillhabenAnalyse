# API-Referenz: WillhabenAnalyse v2.1

## CLI-Interface (`main.py`)

### Flags

| Flag | Typ | Default | Beschreibung |
|------|-----|---------|--------------|
| `--gui` | bool (store_true) | `False` | GUI starten (tkinter). Standardverhalten wenn kein anderer Flag gesetzt. |
| `--once` | bool (store_true) | `False` | Einmaliger Pipeline-Run (Scraping → Parsing → OVP → Excel). |
| `--daemon` | bool (store_true) | `False` | Scheduling-Daemon starten. Liest `config.json → schedule.enabled`; wenn `false`, einmaliger Run. |
| `--ovp` | bool (store_true) | `False` | Nur OVP-Check auf den letzten 20 raw_cache-Einträgen (Debugging). |
| `--model` | str (choices) | `None` | Ollama-Modell überschreiben. Erlaubte Werte: `gemma3:27b`, `gemma4:26b`, `gemma4:latest`. Nur wirksam in Kombination mit `--parser-version v2`. |
| `--parser-version` | str (choices) | `v2` | Parser-Version. `v2` = `parser/v2/` (Standard), `v1` = `parser/gemma_parser.py` (Rollback). |
| `--test-batch N` | int | — | Parst die ersten N Einträge aus `data/raw_cache/` ohne Excel-Write. Gibt JSON auf stdout aus. |
| `--dry-run` | bool (store_true) | `False` | Komplette Pipeline ohne Excel-Write und ohne Google Drive Upload. Gibt Stats-JSON auf stdout aus. |
| `--max-listings N` | int | `None` (kein Limit) | Begrenzt die Anzahl zu parsender Anzeigen auf N. Wirksam sowohl im Scraper als auch nach dem Scraping. |

### Exit-Codes

| Code | Bedeutung |
|------|-----------|
| `0` | Erfolg. |
| `1` | Fehler bei `--test-batch`: kein raw_cache vorhanden (Meldung auf stdout). |
| `2` | argparse-Fehler: ungültiger Flag-Wert (z.B. `--model unknown`, `--parser-version v99`, `--max-listings notanumber`). argparse schreibt Fehlermeldung auf stderr. |

Hinweis: `run_pipeline()` fängt interne Fehler (Scraping, Parsing, Excel) als Ausnahmen ab und gibt sie im `stats["errors"]`-Dict zurück, ohne den Prozess mit Exit-Code != 0 zu beenden. Der Prozess endet mit Code 0 auch wenn Pipeline-Schritte fehlgeschlagen sind.

---

## `run_pipeline()` — programmatische API

```python
def run_pipeline(
    log_callback: Callable[[str], None] | None = None,
    parser_version: str = "v2",
    model_override: str | None = None,
    dry_run: bool = False,
    max_listings: int | None = None,
) -> dict
```

Führt die komplette Pipeline aus: Scraping → Parsing → OVP-Check → Excel-Update.

**Parameter:**
- `log_callback` — optionale Funktion, die zusätzlich zu `logging.info()` für jede Log-Zeile aufgerufen wird (z.B. GUI-Textbox-Update).
- `parser_version` — `"v2"` (Standard) oder `"v1"` (Rollback).
- `model_override` — Ollama-Modell-Name; wird an `parse_ads(model=...)` weitergegeben, nur wenn `parser_version == "v2"`.
- `dry_run` — wenn `True`, wird Schritt 4 (Excel-Write + Google Drive) übersprungen.
- `max_listings` — Obergrenze für Anzeigen nach dem Scraping.

**Rückgabe:**
```python
{
    "scraped":         int,   # Anzahl gescrapte Anzeigen
    "parsed_events":   int,   # Anzahl extrahierter Events
    "ovp_checked":     int,   # Events mit gefundenem Originalpreis
    "excel_inserted":  int,   # Neu eingefügte Excel-Zeilen
    "excel_updated":   int,   # Aktualisierte Excel-Zeilen
    "errors":          list[str],  # Fehlermeldungen pro Pipeline-Schritt
    "gdrive_upload":   bool,  # nur vorhanden wenn dry_run=False
}
```

---

## `parser/v2` — Parse-Pipeline

### `parse_ad(ad: dict, model: str | None, use_cache: bool) → list[dict]`

```python
def parse_ad(
    ad: dict,
    model: str | None = None,
    use_cache: bool = True,
) -> list[dict]
```

Parst eine einzelne Willhaben-Anzeige mit Parser v2.0.

**Parameter:**
- `ad` — Rohdaten-Dict einer Anzeige (aus `data/raw_cache/*.json`). Pflichtfelder: `id` (str), `title` (str), weitere von `preprocessing.build_context()` genutzten Felder.
- `model` — Ollama-Modell-Override. `None` = Primärmodell (`gemma3:27b`).
- `use_cache` — wird in `parse_ad()` direkt **nicht ausgewertet** (Dead Code, siehe Abschnitt "Bekannte API-Inkonsistenzen"). Der Parameter existiert nur für Signatur-Kompatibilität mit dem v1-Rollback-Interface.

**Rückgabe:** Liste von Event-Dicts (kann leer sein, z.B. bei Category-Pages oder Non-Ticket-Anzeigen). Jedes Dict enthält die Felder aus `EventResult` plus Metadaten: `modell`, `pipeline_version`, `parse_dauer_ms`, `fallback_used`.

**Raises:** Kann Ausnahmen von `extractor.extract()` weitergeben, wenn Ollama nicht erreichbar ist und alle Retry-Versuche erschöpft sind (tenacity `RetryError`).

**Beispiel:**
```python
from parser.v2 import parse_ad
ad = {"id": "2123545129", "title": "2x Linkin Park Wien 09.06", "beschreibung": "..."}
events = parse_ad(ad, model="gemma3:27b")
# events = [{"event_name": "Linkin Park", "event_datum": "2026-06-09", ...}]
```

---

### `parse_ads(ads: list[dict], use_cache: bool, model: str | None) → list[dict]`

```python
def parse_ads(
    ads: list[dict],
    use_cache: bool = True,
    model: str | None = None,
) -> list[dict]
```

Verarbeitet eine Liste von Anzeigen sequenziell.

**Parameter:**
- `ads` — Liste von Anzeigen-Dicts.
- `use_cache` — wenn `True`, werden Anzeigen mit bereits vorhandenem `data/parse_cache_v2/<id>.json` übersprungen (Cache-Hit). Ergebnisse werden nach dem Parsen ebenfalls gecacht.
- `model` — Ollama-Modell-Override, wird an jeden `parse_ad()`-Aufruf weitergegeben.

**Rückgabe:** Flache Liste aller extrahierten Events aus allen Anzeigen.

**Seiteneffekte:**
- Schreibt/liest `data/parse_cache_v2/<id>.json`.
- Schreibt Heartbeat-Updates in `.willhaben_status.json` via `StatusWriter`.

**Raises:** Interne Fehler pro Anzeige werden gefangen und über `StatusWriter.error()` protokolliert; die Verarbeitung läuft weiter. Ein fataler Fehler (z.B. `KeyboardInterrupt`) ruft `StatusWriter.fail()` auf und wird dann re-raised.

---

### `StatusWriter`

Schreibt atomare JSON-Heartbeat-Datei nach `BASE_DIR/.willhaben_status.json` während eines Parsing-Laufs. Wird von `parse_ads()` intern instanziiert.

```python
class StatusWriter:
    def __init__(
        self,
        total: int,
        model: str,
        run_id: str | None = None,
        _status_file: Path | None = None,
    ) -> None
```

Beim Initialisieren wird die Status-Datei mit `status="running"` geschrieben.

- `total` — Gesamtanzahl der zu parsenden Anzeigen.
- `model` — Name des verwendeten Ollama-Modells (für Anzeige in der GUI).
- `run_id` — optionale UUID; wird automatisch generiert wenn `None`.
- `_status_file` — nur für Tests: alternativer Pfad statt `BASE_DIR/.willhaben_status.json`.

**Methoden:**

```python
def update(self, current: int, ad_id: str, title: str, duration_ms: int | None = None) -> None
```
Aktualisiert Fortschritt. `duration_ms` wird in einen gleitenden Puffer der letzten 10 Werte eingetragen.

```python
def error(self, msg: str) -> None
```
Inkrementiert `errors_count`, setzt `last_error`. Status bleibt `"running"`.

```python
def finish(self) -> None
```
Setzt `status = "done"`. Wird am Ende eines erfolgreichen Laufs aufgerufen.

```python
def fail(self, msg: str) -> None
```
Setzt `status = "error"` und `last_error`. Wird bei fatalen Ausnahmen aufgerufen.

Alle Schreib-Operationen sind best-effort: Fehler beim Schreiben werden still ignoriert, damit die Pipeline nie durch Datei-I/O blockiert wird.

---

## `app/backend` — Backend-Module

### `status_monitor`

**Pfad:** `app/backend/status_monitor.py`

```python
def read_status(base_dir: Path) -> dict | None
```
Liest `base_dir/.willhaben_status.json`. Gibt geparsten Dict zurück oder `None` wenn Datei fehlt oder ungültiges JSON.

```python
def is_running(status: dict) -> bool
```
Gibt `True` zurück wenn `status["status"] == "running"`.

```python
def format_progress(status: dict) -> str
```
Gibt menschenlesbaren Fortschritts-String zurück, z.B. `"42/350 (12%)"`. Bei `total=0` oder fehlendem Feld wird `"0/0 (0%)"` zurückgegeben.

```python
def avg_duration_ms(status: dict) -> float | None
```
Berechnet Durchschnitt der `status["last_10_durations"]`-Liste. Gibt `None` zurück wenn die Liste leer ist.

---

### `dashboard_aggregator`

**Pfad:** `app/backend/dashboard_aggregator.py`

```python
def load_excel(path: Path) -> pd.DataFrame
```
Liest Sheet `"Angebote"` aus der Excel-Datei. Gibt leeren DataFrame zurück wenn Datei fehlt oder Sheet nicht existiert.

**Bekannte Inkonsistenz:** Das Haupt-Sheet heißt tatsächlich `"Hauptübersicht"`, nicht `"Angebote"`. `load_excel()` wird deshalb immer einen leeren DataFrame zurückgeben solange dieser Sheet-Name nicht korrigiert wird (siehe Abschnitt "Bekannte API-Inkonsistenzen").

```python
def aggregate(df: pd.DataFrame) -> pd.DataFrame
```
Gruppiert nach `(event_name, event_datum, kategorie)`. Trennt `"Privat"`- und `"Händler"`-Verkäufer anhand der Spalte `anbieter_typ`. Berechnet pro Gruppe: Anzahl, Min/Avg/Max von `preis_pro_karte`, Median-OVP, Marge-Prozent. Gibt leeren DataFrame mit den korrekten Spalten zurück wenn Input leer ist.

**Ausgabe-Spalten:**

| Spalte | Typ | Beschreibung |
|--------|-----|--------------|
| `Event` | str | Event-Name |
| `Kategorie` | str | Ticket-Kategorie |
| `Datum` | str | Event-Datum |
| `Venue` | str | Veranstaltungsort |
| `Stadt` | str | Stadt |
| `Privat_Anzahl` | int | Anzahl Privatverkäufer-Angebote |
| `Privat_Min` | float | Mindestpreis Privatverkäufer |
| `Privat_Avg` | float | Durchschnittspreis Privatverkäufer |
| `Privat_Max` | float | Höchstpreis Privatverkäufer |
| `Haendler_Anzahl` | int | Anzahl Händler-Angebote |
| `Haendler_Min` | float | Mindestpreis Händler |
| `Haendler_Avg` | float | Durchschnittspreis Händler |
| `Haendler_Max` | float | Höchstpreis Händler |
| `OVP` | float | Median-Originalpreis pro Karte |
| `Marge_Haendler_Pct` | float | `(OVP - Haendler_Avg) / OVP * 100` |
| `Marge_Privat_Pct` | float | `(OVP - Privat_Avg) / OVP * 100` |

```python
def export_csv(df: pd.DataFrame, path: Path) -> None
```
Schreibt den aggregierten DataFrame als UTF-8-CSV ohne Index.

---

### `subprocess_runner`

**Pfad:** `app/backend/subprocess_runner.py`

```python
def start_pipeline(
    python_path: str,
    project_dir: str,
    parser_version: str = "v2",
    model: str = "gemma3:27b",
    max_listings: int | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> subprocess.Popen
```
Startet `python_path main.py --once --parser-version=... --model=... [--max-listings=N]` als Subprocess in `project_dir`. Stdout und Stderr werden zu PIPE gemergt. Wenn `log_callback` angegeben, wird ein Daemon-Thread gestartet der stdout-Zeilen liest und `log_callback(line)` aufruft. Gibt das `Popen`-Objekt zurück.

```python
def is_running(proc: subprocess.Popen) -> bool
```
Gibt `True` zurück wenn der Prozess noch läuft (`proc.poll() is None`).

```python
def stop(proc: subprocess.Popen) -> None
```
Sendet `SIGTERM`, wartet 5 Sekunden. Bei Timeout: `SIGKILL` + `wait()`. Kein Fehler wenn Prozess bereits beendet.

---

### `launchd_manager`

**Pfad:** `app/backend/launchd_manager.py`

```python
def generate_plist(
    label: str,
    python_path: str,
    project_dir: str,
    model: str,
    max_listings: int | None,
    hour: int,
    minute: int,
) -> str
```
Rendert das plist-Template aus `app/templates/launchd.plist.template` mit den übergebenen Parametern. Gibt den fertigen plist-XML-String zurück. Bei `max_listings=None` wird `MAX_LISTINGS_ARG` als Leerstring eingesetzt (kein `--max-listings`-Flag in der plist).

```python
def install_plist(plist_xml: str, label: str) -> tuple[bool, str]
```
Schreibt die plist nach `~/Library/LaunchAgents/{label}.plist` und ruft `launchctl load` auf. Gibt `(True, Erfolgsmeldung)` oder `(False, Fehlermeldung)` zurück.

```python
def uninstall_plist(label: str) -> tuple[bool, str]
```
Ruft `launchctl unload` auf und löscht `~/Library/LaunchAgents/{label}.plist`. Gibt `(False, Fehlermeldung)` zurück wenn die Datei nicht existiert.

```python
def is_installed(label: str) -> bool
```
Gibt `True` zurück wenn `~/Library/LaunchAgents/{label}.plist` existiert.

---

## Daten-Schemas

### Parse-Cache-Eintrag (`data/parse_cache_v2/<id>.json`)

Jede Datei enthält eine JSON-Liste von Event-Dicts (das Ergebnis eines `parse_ad()`-Aufrufs für eine Anzeige). Die Liste kann leer sein (z.B. bei gefilterten Non-Ticket-Anzeigen).

```json
[
  {
    "event_name":              "string | null",
    "event_datum":             "string | null",
    "venue":                   "string | null",
    "stadt":                   "string | null",
    "kategorie":               "Stehplatz | Sitzplatz | VIP | Front-of-Stage | Gemischt | Unbekannt",
    "anzahl_karten":           "integer | null",
    "angebotspreis_gesamt":    "float | null",
    "preis_ist_pro_karte":     "boolean | null",
    "originalpreis_pro_karte": "float | null",
    "confidence":              "hoch | mittel | niedrig",
    "confidence_grund":        "string | null",
    "modell":                  "string",
    "pipeline_version":        "string",
    "parse_dauer_ms":          "integer",
    "fallback_used":           "boolean"
  }
]
```

Feldtypen entsprechen dem Pydantic-Modell `EventResult` aus `parser/v2/schema.py`, ergänzt um die Metadaten-Felder die `postprocessing.attach_metadata()` hinzufügt.

---

### Status-File (`.willhaben_status.json`)

Wird von `StatusWriter` atomar in `BASE_DIR/.willhaben_status.json` geschrieben.

```json
{
  "run_id":             "string (UUID4)",
  "started_at":         "string (ISO 8601, UTC, z.B. '2026-04-18T08:00:00+00:00')",
  "model":              "string (Ollama-Modell-Name)",
  "total":              "integer (Gesamtanzahl zu parsender Anzeigen)",
  "current":            "integer (zuletzt verarbeiteter Index, 1-basiert)",
  "current_id":         "string | null (Willhaben-ID der aktuellen Anzeige)",
  "current_title":      "string | null (Titel der aktuellen Anzeige, max 80 Zeichen)",
  "last_10_durations":  "array[integer] (Parsing-Dauern in ms, maximal 10 Einträge)",
  "errors_count":       "integer (Anzahl Fehler seit Run-Start)",
  "last_error":         "string | null (letzte Fehlermeldung)",
  "status":             "running | done | error"
}
```

---

### Excel-Zeile (Sheet `Hauptübersicht`)

Die Ausgabedatei liegt standardmäßig unter `data/willhaben_markt.xlsx` (konfigurierbar via `config.json → export_path`).

| Interner Feldname | Header-Anzeigename | Typ | Beschreibung |
|-------------------|--------------------|-----|--------------|
| `scan_datum` | Scan-Datum | str | Zeitstempel des Scans, Format `YYYY-MM-DD HH:MM` |
| `willhaben_link` | Willhaben-Link | str | URL zur Anzeige |
| `willhaben_id` | Anzeigen-ID | str | Primärschlüssel für Upsert-Logik |
| `verkäufer_id` | Verkäufer-ID | str | Willhaben-Profil-ID |
| `verkäufername` | Verkäufername | str | Anzeigename des Verkäufers |
| `verkäufertyp` | Verkäufertyp | str | `"Privat"` oder `"Händler"` |
| `mitglied_seit` | Mitglied seit | str | Registrierungsdatum des Verkäufers (z.B. `"03/2018"`) |
| `event_name` | Event-Name | str | Name des Events (vom Modell extrahiert) |
| `event_datum` | Event-Datum | str | Datum des Events (ISO 8601 oder Rohtext) |
| `venue` | Venue | str | Veranstaltungsort |
| `stadt` | Stadt | str | Stadt |
| `kategorie` | Kategorie | str | Enum-Wert aus `Kategorie` |
| `anzahl_karten` | Anzahl Karten | int | Anzahl angebotener Karten |
| `angebotspreis_gesamt` | Angebotspreis gesamt | float | Gesamtpreis des Angebots in EUR |
| `preis_ist_pro_karte` | Preis ist pro Karte | str | `"ja"` / `"nein"` (aus bool konvertiert) |
| `angebotspreis_pro_karte` | Angebotspreis pro Karte | float | Berechnet: `angebotspreis_gesamt / anzahl_karten` |
| `originalpreis_pro_karte` | Originalpreis pro Karte | float | OVP in EUR (aus OVP-Check oder Anzeigentext) |
| `ovp_quelle` | OVP-Quelle | str | z.B. `"oeticket"`, `"Anzeige"` |
| `marge_eur` | Marge EUR | float | Berechnet: `angebotspreis_pro_karte - originalpreis_pro_karte` |
| `marge_pct` | Marge % | float | Berechnet: `(angebotspreis_pro_karte - OVP) / OVP * 100` |
| `ausverkauft` | Ausverkauft beim Anbieter | str | `"ja"` / `"nein"` / `"unbekannt"` |
| `watchlist` | Watchlist | str | `"ja"` / `"nein"` |
| `confidence` | Confidence | str | `"hoch"` / `"mittel"` / `"niedrig"` |
| `review_nötig` | Review nötig | str | `"ja"` wenn `confidence == "niedrig"`, sonst `"nein"` |
| `confidence_grund` | Confidence-Grund | str | Freitext-Begründung des Modells (seit v2.0) |
| `modell` | Modell | str | Verwendetes Ollama-Modell (seit v2.0) |
| `pipeline_version` | Pipeline-Version | str | z.B. `"v2.0"` (seit v2.0) |
| `parse_dauer_ms` | Parse-Dauer ms | int | Ollama-Antwortzeit in ms (seit v2.0) |

Spalten 1–24 sind im Sheet immer vorhanden. Spalten 25–28 (`confidence_grund`, `modell`, `pipeline_version`, `parse_dauer_ms`) wurden mit v2.0 hinzugefügt; ältere Zeilen lassen diese Zellen leer.

---

## Bekannte API-Inkonsistenzen (aus Audit)

**1. `use_cache`-Parameter in `parse_ad()` ist Dead Code**
`parse_ad()` nimmt `use_cache: bool = True` entgegen, wertet den Parameter aber intern nie aus. Cache-Logik (Lesen und Schreiben) liegt ausschließlich in `parse_ads()`. Beim direkten Aufruf von `parse_ad()` wird unabhängig von `use_cache` immer ein frischer Ollama-Request gemacht.

**2. `errors` vs. `errors_count` — Feldname-Mismatch zwischen Pipeline und StatusWriter**
`run_pipeline()` zählt interne Fehler in `stats["errors"]` (eine Liste von Strings). `StatusWriter` führt hingegen `errors_count` (int) und `last_error` (str) als separate Felder. `status_monitor.py` liest nur `errors_count` aus der Status-Datei. Ein Code-Pfad der `stats["errors"]` in `errors_count` übersetzt existiert nicht — der Wert im Status-File ist deshalb immer `0`, auch wenn Pipeline-Fehler aufgetreten sind.

**3. Dashboard-Sheet-Name-Bug**
`dashboard_aggregator.load_excel()` liest explizit `sheet_name="Angebote"`. Das tatsächliche Haupt-Sheet in der Excel-Datei heißt `"Hauptübersicht"` (definiert in `excel_writer.py`). Deshalb gibt `load_excel()` immer einen leeren DataFrame zurück, und das Dashboard-Tab zeigt keine Daten an.

**4. `kategorie` meist `"Unbekannt"`**
Das Modell gibt für viele Anzeigen `Kategorie.unbekannt` zurück. Das Eval-Ergebnis (`kategorie`-Accuracy: 86,7%) bezieht sich auf Gold-Standard-Einträge mit klaren Kategorieangaben; im realen Produktionsbetrieb mit unstrukturierten Beschreibungen ist die Quote deutlich niedriger.
