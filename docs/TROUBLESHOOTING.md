# Troubleshooting: WillhabenAnalyse v2.1

Dieses Handbuch ist zweistufig aufgebaut: Die Diagnose-Übersicht ermöglicht schnelle Orientierung,
die Abschnitte darunter erklären Ursachen und geben reproduzierbare Lösungsschritte.

---

## Diagnose-Übersicht

| Symptom | Wahrscheinlichste Ursache | Abschnitt |
|---|---|---|
| Dashboard zeigt keine Daten | Sheet-Name-Bug in `dashboard_aggregator` | [#dashboard-leer](#dashboard-leer) |
| Pipeline startet nicht / Timeout | Ollama nicht erreichbar oder Modell nicht geladen | [#ollama](#ollama) |
| 0 Anzeigen gescrapt, alle übersprungen | Cutoff-Datum zu eng oder falscher `sort`-Parameter | [#cutoff](#cutoff) |
| Parse-Dauer > 2 Stunden | Zu viele Anzeigen mit `gemma3:27b` — normal | [#performance](#performance) |
| launchd-Job startet nicht / schlägt fehl | Volume nicht gemountet, falscher venv-Pfad | [#launchd](#launchd) |
| GUI zeigt "Fehler: 0" trotz Fehlern | `errors` vs. `errors_count` Feldname-Mismatch | [#gui-fehler](#gui-fehler) |
| Tests schlagen fehl (Import-Fehler) | venv nicht aktiviert | [#tests](#tests) |
| Pipeline bricht mitten durch ab | StatusWriter `fail()` nicht aufgerufen | [#absturz](#absturz) |

---

## Abschnitte

### dashboard-leer

**Dashboard zeigt keine Daten**

**Symptom:** Der Dashboard-Tab in der GUI bleibt leer, obwohl `data/willhaben_markt.xlsx`
Einträge enthält. Kein Fehler wird angezeigt.

**Ursache:** `app/backend/dashboard_aggregator.py` versucht in `load_excel()`, das Sheet
`"Angebote"` zu lesen. Dieses Sheet existiert in der Excel-Datei nicht — die Daten liegen in
Sheet `"Hauptübersicht"`. Der `except`-Block fängt den `KeyError` still ab und gibt einen leeren
DataFrame zurück, ohne den Fehler anzuzeigen.

Zusätzlich weichen die internen Spalten-Konstanten des Aggregators von den tatsächlichen
Spaltenbezeichnungen in der Excel-Datei ab (z. B. erwartet der Aggregator andere Bezeichner als
`"Angebotspreis pro Karte"`, `"Verkäufertyp"`, `"Event-Name"`). Selbst nach Korrektur des
Sheet-Namens würden ohne Anpassung der Spalten-Konstanten weiterhin leere Aggregate erzeugt.

**Status:** Bekannter Bug (CRITICAL, Phase-B-Audit). Noch nicht behoben in v2.1.

**Workaround bis zur Behebung:**

1. Aggregation manuell aus der Excel-Datei durchführen:
   ```bash
   .venv/bin/python3 -c "
   import pandas as pd
   df = pd.read_excel('data/willhaben_markt.xlsx', sheet_name='Hauptübersicht')
   print(df.columns.tolist())
   print(df.head())
   "
   ```

2. Um zu prüfen, welche Sheets tatsächlich vorhanden sind:
   ```bash
   .venv/bin/python3 -c "
   import pandas as pd
   xl = pd.ExcelFile('data/willhaben_markt.xlsx')
   print(xl.sheet_names)
   "
   ```

---

### ollama

**Ollama nicht erreichbar — Pipeline startet nicht oder bricht sofort ab**

**Symptom:** Pipeline gibt sofort einen Verbindungsfehler aus, oder alle Parsing-Versuche
schlagen mit Timeout fehl. Im Log erscheinen Meldungen wie `ConnectionRefusedError` oder
`httpx.ConnectError`.

**Schritt 1 — Ist Ollama überhaupt gestartet?**

```bash
curl -s http://localhost:11434/api/tags | python3 -m json.tool | head -20
```

Erwartete Ausgabe: JSON mit `"models": [...]`. Bei `Connection refused` ist Ollama nicht aktiv.

**Schritt 2 — Ollama starten:**

```bash
ollama serve
```

Ollama läuft danach im Vordergrund. Für Hintergrundbetrieb:

```bash
nohup ollama serve > /tmp/ollama.log 2>&1 &
```

**Schritt 3 — Modell vorhanden?**

```bash
ollama list
```

`gemma3:27b` muss in der Liste erscheinen. Falls nicht:

```bash
ollama pull gemma3:27b
```

Der Download ist ca. 17 GB groß. Ausreichend Speicher und Zeit einplanen.

**Schritt 4 — Modell testweise laden:**

```bash
ollama run gemma3:27b "Antworte nur mit: OK"
```

Wenn die Antwort nicht innerhalb von 3 Minuten erscheint, ist das Modell zu groß für den
verfügbaren RAM. In diesem Fall mit dem kleineren Fallback-Modell arbeiten:

```bash
python main.py --once --model gemma4:latest
```

**Hinweis für macOS:** Nach einem Neustart muss Ollama manuell neu gestartet werden, außer ein
launchd-Job ist eingerichtet (siehe [#launchd](#launchd)).

---

### cutoff

**0 Anzeigen gescrapt — alle Anzeigen werden übersprungen**

**Symptom:** Log zeigt `0 Anzeigen verarbeitet, N übersprungen`. Pipeline bricht direkt nach dem
Scraping mit `Keine Anzeigen – Pipeline abgebrochen` ab.

**Häufigste Ursache 1 — sort=5 (älteste zuerst):**

Der bekannte Bug: Wenn willhaben.at mit `sort=5` (älteste zuerst) sortiert, ist die erste
angezeigte Anzeige mehrere Wochen alt und wird sofort vom Alters-Filter (`max_age_days`)
abgewiesen. Da der Early-Stop greift, werden alle weiteren Anzeigen ebenfalls übersprungen.

Überprüfung im Log:
```
Anzeige vom 2026-03-04 — älter als cutoff 2026-04-17 → übersprungen
```

Lösung: Sicherstellen, dass der Scraper mit `sort=3` (neueste zuerst) läuft. Im Code
`scraper/willhaben_scraper.py` den `sort`-Parameter prüfen.

**Häufigste Ursache 2 — max_age_days zu eng:**

Der Standard-Cutoff (`max_age_days=3`) verwirft alle Anzeigen, die älter als 3 Tage sind.
Nach einem langen Ausfall der Pipeline kann `raw_cache/` veraltet sein.

Debug-Schritt: Welche Anzeigen liegen im Cache?

```bash
ls -lt data/raw_cache/ | head -20
```

Wenn alle Dateien älter als 3 Tage sind, hilft ein Scraping-Lauf ohne Cache-Nutzung oder
mit erweitertem Cutoff-Fenster.

**Häufigste Ursache 3 — leerer raw_cache:**

Auf einem frischen Checkout oder Worktree ist `data/raw_cache/` leer. Die Pipeline überspringt
den Parse-Schritt mangels Eingabedaten. Erst ein vollständiger Scraping-Lauf befüllt den Cache.

Prüfen:
```bash
ls data/raw_cache/ | wc -l
```

---

### performance

**Scraping oder Parsing sehr langsam**

**Erwartete Laufzeiten:**

| Konfiguration | Anzeigen | Geschätzte Dauer |
|---|---|---|
| `gemma3:27b` (Standard) | 50 | ~70 Minuten |
| `gemma3:27b` (Standard) | 100 | ~2,5 Stunden |
| `gemma3:27b` (Standard) | 350 | ~8 Stunden |
| `gemma4:latest` (8B, Fallback) | 100 | ~45 Minuten |

83 Sekunden pro Anzeige mit `gemma3:27b` sind normal und kein Fehler. Das Modell benötigt
auf typischer Hardware (Mac, 32 GB RAM) diese Zeit für Structured Output mit vollständigem Schema.

**Empfehlungen:**

1. `--max-listings N` setzen, um die Anzahl zu begrenzen:
   ```bash
   python main.py --once --max-listings 50
   ```

2. Live-Fortschritt in der GUI beobachten (Status-Tab, Auto-Refresh alle 2 Sekunden), oder
   direkt im Status-File:
   ```bash
   cat .willhaben_status.json | python3 -m json.tool
   ```
   Das Feld `last_10_durations` zeigt die letzten 10 Parse-Dauern in Millisekunden.
   `avg_duration_ms` ist im Modul `app/backend/status_monitor.py` berechenbar.

3. Für schnelle Tests: `--test-batch N` parst nur N Einträge aus dem Cache ohne Excel-Schreib:
   ```bash
   python main.py --test-batch 5
   ```

4. Für Nachtläufe: launchd einrichten (siehe [#launchd](#launchd)), sodass die Pipeline
   unbeaufsichtigt durchläuft.

**Hinweis:** Die Latenzsteigerung von ~25s (v1/gemma4:8B) auf ~90s (v2/gemma3:27b) ist der
Preis für 100 % JSON-Parse-Rate und 92 % Event-Count-Accuracy. Mit v1 und dem kleineren Modell
kann auf Kosten der Datenqualität deutlich schneller gescrapt werden.

---

### launchd

**launchd-Job startet nicht oder schlägt beim Ausführen fehl**

**Schritt 1 — Ist der Job registriert?**

```bash
launchctl list | grep willhaben
```

Erwartete Ausgabe: Zeile mit dem Job-Label (z. B. `com.willhaben.analyser`). Fehlt die Zeile,
ist der Job nicht installiert oder wurde deinstalliert.

**Schritt 2 — Job-Status und Fehlercode prüfen:**

```bash
launchctl list com.willhaben.analyser
```

Ausgabe enthält `"LastExitStatus"`. Ein Wert ungleich 0 bedeutet, dass der letzte Lauf fehlschlug.

**Schritt 3 — Log-Dateien prüfen:**

Die launchd-Logs werden in die im Plist konfigurierten Dateien geschrieben:

```bash
# Stdout-Log (Pipeline-Ausgabe)
tail -50 logs/launchd_stdout.log

# Stderr-Log (Python-Fehler, Traceback)
tail -50 logs/launchd_stderr.log
```

**Häufige Fehlerursachen:**

**a) Volume nicht gemountet (OLLAMA_MODELS nicht gefunden):**

Wenn Ollama-Modelle auf einem externen Volume oder einem nicht standardmäßigen Pfad liegen, muss
dieses Volume beim macOS-Login gemountet sein. launchd startet beim Login — oft bevor externe
Volumes verfügbar sind.

Lösung: Im Plist eine `WaitForDebugger`-Verzögerung einbauen oder `StartCalendarInterval` auf
eine Uhrzeit setzen, zu der das Volume sicher gemountet ist.

**b) Falscher venv-Pfad:**

launchd verwendet absoluten Pfad zum Python-Interpreter. Prüfen, ob der Pfad stimmt:

```bash
cat ~/Library/LaunchAgents/com.willhaben.analyser.plist | grep ProgramArguments -A 5
```

Der Python-Pfad muss auf `.venv/bin/python3` im Projektverzeichnis zeigen. Bei neu erzeugtem
venv hat sich der Pfad möglicherweise geändert.

Korrektur: In der GUI (Zeitplan-Tab) auf "Deinstallieren" und dann "Installieren" klicken —
das erzeugt ein frisches Plist mit aktuellem Pfad.

**c) Ollama beim Job-Start nicht aktiv:**

launchd startet die Pipeline zur konfigurierten Uhrzeit, aber Ollama muss separat laufen.
Entweder Ollama ebenfalls über launchd starten oder sicherstellen, dass es als macOS-Service
(aus der Ollama-App oder per LaunchAgent) dauerhaft aktiv ist.

**Schritt 4 — Job manuell triggern (Test):**

```bash
launchctl start com.willhaben.analyser
```

Danach sofort Log beobachten:

```bash
tail -f logs/launchd_stdout.log
```

---

### gui-fehler

**GUI zeigt immer "Fehler: 0" — auch wenn Fehler aufgetreten sind**

**Symptom:** Im Status-Tab der GUI zeigt das Feld "Fehler:" konstant `0`, unabhängig davon,
wie viele Parse-Fehler tatsächlich aufgetreten sind.

**Ursache:** Feldname-Mismatch zwischen `StatusWriter` und `StatusTab`:

- `parser/v2/status_writer.py` schreibt das Feld `"errors_count"` ins Status-JSON
- `app/tabs/status.py` liest `status.get("errors", 0)` — also das Feld `"errors"`, das nie gesetzt wird

Da `dict.get()` bei fehlendem Schlüssel den Default-Wert zurückgibt, wird immer `0` angezeigt.

**Status:** Bekannter Bug (CRITICAL C5, Phase-A-Audit). Noch nicht behoben in v2.1.

**Workaround — Fehleranzahl direkt im Status-File ablesen:**

```bash
python3 -c "
import json
with open('.willhaben_status.json') as f:
    s = json.load(f)
print('errors_count:', s.get('errors_count', 'n/a'))
print('last_error:', s.get('last_error', 'keiner'))
print('status:', s.get('status'))
"
```

**Erläuterung der Status-Felder:**

| Feld | Bedeutung |
|---|---|
| `status` | `"running"`, `"done"`, `"failed"` |
| `errors_count` | Anzahl fehlgeschlagener Parsing-Versuche (kein JSON, Timeout, etc.) |
| `last_error` | Fehlermeldung des letzten Fehlers (String oder `null`) |
| `current` | Zähler der aktuell verarbeiteten Anzeige |
| `total` | Gesamtanzahl geplanter Anzeigen |
| `last_10_durations` | Liste der letzten 10 Parse-Dauern in Millisekunden |

---

### tests

**Tests schlagen fehl — Import-Fehler oder ModuleNotFoundError**

**Häufigste Ursache:** Tests werden ohne aktiviertes virtualenv ausgeführt. Die Abhängigkeiten
(`pandas`, `tenacity`, `openpyxl` etc.) sind nur im `.venv` installiert.

**Lösung:**

```bash
# Option 1: venv aktivieren, dann pytest
source .venv/bin/activate
pytest tests/

# Option 2: direkt mit venv-Python aufrufen (kein Aktivieren nötig)
.venv/bin/python -m pytest tests/

# Option 3: einzelne Testdatei
.venv/bin/python -m pytest tests/test_v2_status_writer.py -v
```

**Erwartetes Ergebnis:** `143 passed, 2 warnings in 0.88s`

**Häufige Fehlersituationen:**

| Fehlermeldung | Ursache | Lösung |
|---|---|---|
| `ModuleNotFoundError: No module named 'pandas'` | venv nicht aktiv | `.venv/bin/python -m pytest` |
| `ModuleNotFoundError: No module named 'tenacity'` | venv nicht aktiv | `.venv/bin/python -m pytest` |
| `FileNotFoundError: data/...` | Test läuft im falschen Verzeichnis | `cd /Users/Boti/WillhabenAnalyse` |
| `collected 0 items` | Kein `test_`-Präfix oder falscher Pfad | `pytest tests/` statt `pytest .` |

**Test-Suite-Struktur:**

| Testdatei | Testet | Anzahl Tests |
|---|---|---|
| `test_v2_status_writer.py` | `StatusWriter`, JSON-Heartbeat, atomares Schreiben | 10 |
| `test_main_cli.py` | CLI-Parameter (`--max-listings`, `--parser-version` etc.) | 8 |
| `test_backend_status_monitor.py` | `read_status`, `is_running`, `format_progress` | 12 |
| `test_backend_launchd_manager.py` | Plist-Generierung, `install`/`uninstall` | 11 |
| `test_backend_dashboard_aggregator.py` | `load_excel`, `aggregate`, `export_csv` | 12 |
| `test_backend_subprocess_runner.py` | `start_pipeline`, `is_running`, `stop` | 7 |
| `test_tabs_engine.py` | `EngineTab` GUI-Logik | 5 |
| `test_tabs_zeitplan.py` | `ZeitplanTab` GUI-Logik | 5 |
| `test_tabs_status.py` | `StatusTab` Auto-Refresh | 6 |
| `test_tabs_dashboard.py` | `DashboardTab` Filter + Sortierung | 6 |
| Bestehende v2-Tests | Pipeline, Schema, Preprocessing, Postprocessing | 61 |

---

### absturz

**Pipeline bricht mitten durch ab — Status bleibt auf "running"**

**Symptom:** Pipeline wurde abgebrochen (Ctrl+C, Systemabsturz, OOM), aber
`.willhaben_status.json` zeigt weiterhin `"status": "running"`. Beim nächsten Start
könnte der `is_running()`-Check einen laufenden Prozess vortäuschen.

**Ursache:** `StatusWriter.fail()` wurde nicht aufgerufen. Seit v2.1 ist `fail()` in einem
`try/finally`-Block in `parse_ads()` gesichert — bei hartem Kill (`kill -9`) oder Stromausfall
greift auch das nicht.

**Lösung:** Status-File manuell zurücksetzen:

```bash
python3 -c "
import json, pathlib
p = pathlib.Path('.willhaben_status.json')
if p.exists():
    s = json.loads(p.read_text())
    s['status'] = 'failed'
    s['last_error'] = 'Manuell zurückgesetzt nach Absturz'
    p.write_text(json.dumps(s, ensure_ascii=False, indent=2))
    print('Status zurückgesetzt.')
else:
    print('Keine Status-Datei gefunden.')
"
```

Danach kann die Pipeline normal neu gestartet werden.

---

## Logs analysieren

Welches Log für welches Problem:

| Problem | Relevante Log-Datei | Wichtige Schlüsselwörter |
|---|---|---|
| Pipeline-Ablauf allgemein | `logs/pipeline.log` | `ERROR`, `WARNING`, `abgebrochen` |
| launchd-Start / Systemjob | `logs/launchd_stdout.log`, `logs/launchd_stderr.log` | `Traceback`, `Exit` |
| Testläufe / Benchmark | `logs/test_frisch_*.log` | `gescrapt`, `übersprungen`, `parsed` |
| 350-Anzeigen-Testlauf | `logs/testlauf_v21_350.log` | `sort=`, `0 Anzeigen` |
| Parser-Debug (einzelne Anzeige) | `data/parse_cache_v2/<id>.json` | `confidence_grund`, `modell` |

**Schnelle Fehlersuche im Log:**

```bash
# Alle Fehler der letzten Pipeline
grep -E "ERROR|Traceback|abgebrochen" logs/pipeline.log | tail -30

# Parse-Erfolgsrate im Testlauf
grep -E "gescrapt|übersprungen|parsed" logs/test_frisch_50_v2.log

# Durchschnittliche Parse-Dauer aus Status
python3 -c "
import json
s = json.load(open('.willhaben_status.json'))
durs = s.get('last_10_durations', [])
if durs:
    print(f'Ø Parse-Dauer: {sum(durs)/len(durs)/1000:.1f}s')
"
```

---

## Rollback auf Parser v1

Falls v2 unerwartetes Verhalten zeigt (Parsing-Fehler, falsches Schema, Modell nicht verfügbar):

```bash
python main.py --once --parser-version v1
```

v1 verwendet `parser/gemma_parser.py` (gemma4:8B, /api/generate, ohne Structured Output).
Der v1-Cache unter `data/parse_cache/` bleibt dauerhaft erhalten und wird nie überschrieben.

**Wann Rollback sinnvoll ist:**

- `gemma3:27b` nicht verfügbar oder zu langsam für den aktuellen Bedarf
- Parse-Ergebnisse von v2 zeigen systematische Fehler (Feld-Mapping, falsches Schema)
- Schneller Testlauf zur Verifikation der Scraping-Logik ohne LLM-Overhead

**Zurück zu v2:**

```bash
python main.py --once --parser-version v2
```

Der v2-Parser ist seit Phase 5 der Standard und muss nicht explizit angegeben werden.

---

## Bekannte offene Bugs (Stand v2.1)

Diese Bugs sind dokumentiert aber noch nicht behoben:

| ID | Komponente | Beschreibung | Workaround |
|---|---|---|---|
| C2 (Audit) | `dashboard_aggregator` | Sheet `"Angebote"` statt `"Hauptübersicht"` → Dashboard dauerhaft leer | Manuell per pandas lesen |
| C3 (Audit) | `dashboard_aggregator` | Spalten-Konstanten stimmen nicht mit Excel-Headern überein | Manuell per pandas lesen |
| C5 (Audit) | `status.py` | `status.get("errors", 0)` statt `"errors_count"` → GUI zeigt immer 0 Fehler | Status-JSON direkt lesen |
| H2 (Audit) | `status_writer.py` | Statischer `.tmp`-Dateiname bei Parallelausführung → Race Condition | Nie zwei Instanzen parallel starten |
| B-C1 (Audit) | `testlauf_v21_350.log` | 350-Anzeigen-Testlauf lief mit `sort=5` → 0 Anzeigen verarbeitet | `--max-listings=100` auf main mit vollem raw_cache wiederholen |
