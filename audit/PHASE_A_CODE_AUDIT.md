# Phase A — Code-Audit Report: WillhabenAnalyse v2.1
**Datum:** 2026-04-18
**Auditiert von:** 5 parallele Modul-Agents + Konsolidierung
**Gesamte Codebase:** ~3.042 Zeilen Produktionscode + 143 Tests

---

## Executive Summary

WillhabenAnalyse v2.1 ist eine funktionsfähige, lokal betriebene Scraping- und Analyse-Pipeline mit einem Tkinter-GUI und LLM-basiertem Parser. Die Codebase zeigt solides Grunddesign in einzelnen Modulen, ist aber noch nicht produktionsreif. Es existieren **6 CRITICAL Findings**, von denen zwei (Hardcoded PII in der Git-History und ein aktiver Produktions-Datenfehler durch `errors` vs. `errors_count` Field-Mismatch) sofortigen Handlungsbedarf haben. Security-Schwachstellen ziehen sich durch drei Layer (Prompt-Injection, Command-Injection, Template-Injection mit Plist-Eskalation auf macOS). Die Testabdeckung ist strukturell lückenhaft: mehrere Tests sind falsch-positiv und schützen nicht vor den Bugs, die sie testen sollen. Für einen stabilen Produktionsbetrieb sind mindestens die CRITICAL und HIGH Findings zu beheben, bevor Phase B (Ausbau/Deployment) beginnt.

---

## Findings-Übersicht

| Severity   | parser/v2 | app/tabs | app/backend | scraper/main | tests  | GESAMT  |
|------------|-----------|----------|-------------|--------------|--------|---------|
| CRITICAL   | 1         | 1        | 1           | 1            | 2      | **6**   |
| HIGH       | 5         | 5        | 4           | 4            | 5      | **23**  |
| MEDIUM     | 8         | 7        | 7           | 6            | 7      | **35**  |
| LOW        | 6         | 6        | 6           | 4            | 5      | **27**  |
| INFO       | 4         | 3        | 4           | 4            | 3      | **18**  |
| **Total**  | **24**    | **22**   | **22**      | **19**       | **22** | **109** |

> Hinweis: Nach Deduplizierung layer-übergreifender Doppelbefunde (RuntimeWarning/Coroutine-Bug taucht in scraper/main UND tests auf; Race Condition StatusWriter in parser/v2 UND app/backend) reduziert sich die effektive Zahl auf **~100 eigenständige Findings**.

---

## CRITICAL Findings (Produktions-Blocker)

### C1: Prompt-Injection via unkontrollierten Anzeigentext — parser/v2
**Datei:** `parser/v2/prompt.py:131`, `parser/v2/preprocessing.py:110–123`
**Impact:** `build_context()` bettet rohen Anzeigentext direkt per `str.replace("{context}", context)` in den Prompt ein. Enthält der Anzeigentext selbst den String `{context}`, erfolgt eine rekursive Ersetzung und erzeugt einen malformed Prompt. LLM-Steuermarkierungen im Anzeigentext können den Prompt-Aufbau korrumpieren.
**Fix-Vorschlag:** Template-Variablen mit `str.format_map` + vorherigem Escape (`context.replace("{", "{{")`) oder Jinja2 mit Autoescape; Kontext-Übergabe unabhängig vom Template-Literal halten.
**Aufwand:** S

---

### C2: Template-Injection in Plist-Generierung — macOS-Persistence-Eskalation — app/backend
**Datei:** `app/backend/launchd_manager.py:33`
**Impact:** `generate_plist()` setzt alle Werte via `str.format()` ungefiltert ins Plist-XML ein. Ein bösartiger `python_path`-Wert wie `</string><string>/bin/bash</string><string>-c` würde eine alternative `ProgramArguments`-Liste einschleusen, die macOS beim nächsten Login ohne Rückfrage ausführt. Effektiv: beliebige Code-Ausführung über launchd-Persistence.
**Fix-Vorschlag:** Alle Werte mit `html.escape()` / `xml.sax.saxutils.escape()` behandeln, oder das Plist programmatisch via `plistlib`-Modul (Stdlib) erzeugen — eliminiert die Template-Injection-Oberfläche vollständig.
**Aufwand:** S

---

### C3: Command-Injection via model-String und parser_version aus Config — app/tabs
**Datei:** `app/tabs/engine.py:149`, `app/tabs/status.py:157`
**Impact:** `model` und `parser_version` aus `config.json` werden ohne Validierung in Subprocess-Argumente eingesetzt. `state="readonly"` in der Combobox verhindert nur Tastatureingaben, nicht programmatische `StringVar.set()`-Aufrufe aus einer manipulierten Config. Schreibzugriff auf `config.json` = beliebige Argumente beim nächsten GUI-Start.
**Fix-Vorschlag:** Allowlist für `model` und `parser_version` vor jedem Subprocess-Aufruf erzwingen; `project_dir` gegen Path-Traversal absichern (must be absolute + must exist).
**Aufwand:** S

---

### C4: Hardcoded PII in Git-History — scraper/main
**Datei:** `scraper/willhaben_tracker_original.py:15`, `old_tracker.py:15`
**Impact:** Eine echte E-Mail-Adresse ist als `os.getenv()`-Fallback-Default direkt im Quellcode committed und liegt dauerhaft in der Git-History. Wird das Repository je öffentlich zugänglich gemacht oder geleakt, ist die Adresse permanent exponiert. `git log`/`git blame` macht sie für jeden Repo-Zugriff sichtbar.
**Fix-Vorschlag:** Default auf `""` oder `None` setzen; im Code prüfen ob die Variable gesetzt ist. Die Git-History muss durch `git filter-repo` oder BFG Repo Cleaner bereinigt werden — ein einfaches Commit reicht nicht, da der Commit-Hash bereits in der History liegt.
**Aufwand:** XS (Code-Fix) + M (History-Bereinigung)

---

### C5: `errors` vs. `errors_count` Field-Mismatch — GUI zeigt immer "Fehler: 0" — tests
**Datei:** `parser/v2/status_writer.py` (schreibt `errors_count`), `app/tabs/status.py` (liest `errors`)
**Impact:** Aktiver Produktionsbug: Die GUI-Statusanzeige liest `status.get("errors", 0)`, aber `StatusWriter` schreibt `errors_count`. Im Betrieb zeigt das Dashboard immer null Fehler an, unabhängig von der tatsächlichen Fehlerrate. Die Testsuite maskiert diesen Bug, weil sie handgestrickte Test-Dicts mit `"errors": 1` verwendet statt echte `StatusWriter`-Ausgaben.
**Fix-Vorschlag:** In `status.py` `status.get("errors_count", 0)` verwenden ODER `status_writer.py` auf `"errors"` umbenennen. Tests müssen reale `StatusWriter`-Output-Dicts verwenden.
**Aufwand:** S

---

### C6: Test beweist nicht was er beweist — `start_pipeline` max_listings ungetestet — tests
**Datei:** `tests/test_backend_subprocess_runner.py:38`
**Impact:** Der Test assertiert auf die Ausgabe eines manuell konstruierten zweiten Prozesses, nicht auf den Output von `start_pipeline()`. `start_pipeline()` könnte `max_listings` komplett ignorieren und der Test wäre weiterhin grün. Ein echter Produktionsfehler (Scraping ohne Limit) würde unentdeckt bleiben.
**Fix-Vorschlag:** `out` aus `proc.communicate()` für die Assertion verwenden; den zweiten Prozess (`proc2`) entfernen. Assertion: `assert "--max-listings=350" in out`.
**Aufwand:** XS

---

## HIGH Findings

### H1: `parse_ads()` ignoriert Cache-Schreib-Fehler still; korrupte Cache-Dateien akkumulieren — parser/v2
**Datei:** `parser/v2/pipeline.py:120–132`
**Impact:** `_load_cache()` fängt alle Exceptions mit `pass` und gibt `None` zurück. Korrupte Dateien bleiben persistent auf Disk und werden bei jedem Lauf ignoriert, aber nie repariert. Im Betrieb wächst ein stiller Fehler-Bestand.
**Fix-Vorschlag:** Korrupte Cache-Datei in `_load_cache()` nach fehlgeschlagenem Parse löschen (`path.unlink(missing_ok=True)`) + WARNING-Log. In `_save_cache()` unvollständige Datei bei Fehler ebenfalls entfernen.
**Aufwand:** XS

---

### H2: Race Condition StatusWriter — statischer `.tmp`-Dateiname bei Parallelausführung — parser/v2
**Datei:** `parser/v2/status_writer.py:75–84`
**Impact:** Mehrere parallele Prozesse/Threads überschreiben dieselbe `.json.tmp`-Datei; der letzte `rename()` gewinnt, frühere Status-Updates gehen verloren oder erzeugen ein gemischtes Bild.
**Fix-Vorschlag:** Temporär-Dateinamen prozess-eindeutig machen: `f"{stem}_{os.getpid()}.tmp"`.
**Aufwand:** XS

---

### H3: Greedy-Regex `\{.*?\}` mit `re.DOTALL` bricht bei verschachteltem JSON — parser/v2
**Datei:** `parser/v2/postprocessing.py:104–116`
**Impact:** Non-greedy Regex bricht bei Werten mit `]` oder `}` in Strings (z. B. `"beschreibung": "Reihe [5]"`) vorzeitig ab und liefert invalides JSON → unnötiger Fallback zu `EMPTY_EVENT`.
**Fix-Vorschlag:** `json.JSONDecoder().raw_decode()` ab der Position des ersten `[`/`{` verwenden — robust gegenüber verschachteltem JSON.
**Aufwand:** S

---

### H4: Bis zu 36 Minuten Blockzeit pro Anzeige durch Retry+Timeout-Multiplikation — parser/v2
**Datei:** `parser/v2/extractor.py:36–78`
**Impact:** 3 Modelle × 3 Versuche × 240 s Timeout = 36 Minuten Worst-Case für eine einzige Anzeige. Pipeline ist synchron; Batches von 100+ Anzeigen sind in schlechtem Netzwerk ein Produktions-Blocker.
**Fix-Vorschlag:** Timeout auf 60–90 s reduzieren und/oder globalen Deadline-Parameter für die gesamte Fallback-Chain einführen.
**Aufwand:** S

---

### H5: `fallback_used`-Flag inkonsistent — falscher Parsing-Pfad bei Primary-Override-Fehler — parser/v2
**Datei:** `parser/v2/extractor.py:96–105`
**Impact:** Bei `model_override`-Fehler gibt `extract()` `fallback_used=True` zurück, auch wenn Primary benutzt wurde. `pipeline.py` wählt daraufhin den langsamen Regex-Fallback statt den strukturierten Parser.
**Fix-Vorschlag:** `fallback_used` semantisch klären: soll nur True sein wenn ein Nicht-Primary-Modell verwendet wurde. Separates `error`-Flag für Fehlerfall.
**Aufwand:** S

---

### H6: Race Condition `_proc` — doppelter Prozessstart bei Mehrfachklick möglich — app/tabs
**Datei:** `app/tabs/engine.py:143–157`, `app/tabs/status.py:153–161`
**Impact:** `_proc` wird im Background-Thread gesetzt, im UI-Thread geprüft. Zwischen Check und tatsächlichem Setzen kann ein zweiter Klick durch den Guard fallen; erster Prozess verliert seine Referenz und ist unkillbar.
**Fix-Vorschlag:** Button während des Laufs auf `state="disabled"` setzen und erst nach Prozessende reaktivieren.
**Aufwand:** S

---

### H7: `_refresh`-Schleife bricht bei Fehler lautlos ab — keine Nutzerbenachrichtigung — app/tabs
**Datei:** `app/tabs/status.py:97–138`
**Impact:** Bei unerwarteten Fehlern in `_refresh()` stoppt die Status-Aktualisierung ohne sichtbare Benachrichtigung; der Nutzer sieht schlicht keine aktualisierten Werte mehr.
**Fix-Vorschlag:** `_after_id` zu Beginn von `_refresh()` auf `None` zurücksetzen; expliziten letzten Refresh nach Prozessende triggern.
**Aufwand:** XS

---

### H8: `messagebox` nicht importiert — `NameError` beim Doppelklick auf "Pipeline starten" — app/tabs
**Datei:** `app/tabs/status.py:10–19`, Nutzung bei Zeile 150
**Impact:** `messagebox.showwarning(...)` in `_start_pipeline()` wirft `NameError: name 'messagebox' is not defined` — der "Läuft bereits"-Guard ist broken.
**Fix-Vorschlag:** `from tkinter import scrolledtext, ttk, messagebox` in den try-Block von `status.py` ergänzen.
**Aufwand:** XS

---

### H9: `_apply_filters` — KeyError bei fehlendem "Event"-Spalte ohne try/except — app/tabs
**Datei:** `app/tabs/dashboard.py:155`
**Impact:** Bei leerem DataFrame oder abweichender Excel-Struktur wirft `df["Event"]` einen unkomprimierten `KeyError` und bricht den gesamten Ladevorgang ab.
**Fix-Vorschlag:** Vor dem Zugriff prüfen: `if "Event" not in df.columns: return`.
**Aufwand:** XS

---

### H10: Path-Traversal via launchd-Label-Dateiname — app/tabs / app/backend
**Datei:** `app/tabs/zeitplan.py:131`, `app/backend/launchd_manager.py:50`
**Impact:** Label wird direkt als Dateiname verwendet: `plist_path = _LAUNCH_AGENTS_DIR / f"{label}.plist"`. Ein Wert wie `../../evil` schreibt außerhalb von `~/Library/LaunchAgents/`. Leerer Label erzeugt `.plist` im LaunchAgents-Ordner.
**Fix-Vorschlag:** Label gegen Regex `^[a-zA-Z0-9._-]+$` validieren; Pfad explizit auf `_LAUNCH_AGENTS_DIR` begrenzen.
**Aufwand:** S

---

### H11: `launchctl load` deprecated seit macOS 13 — Job wird stillschweigend nicht aktiviert — app/backend
**Datei:** `app/backend/launchd_manager.py:57–64`
**Impact:** `launchctl load` gibt auf Ventura+ returncode 0 zurück, aktiviert den Agent aber nicht. Der Code interpretiert Erfolg falsch — der nächtliche Job läuft schlicht nie. Analoges Problem mit `launchctl unload`.
**Fix-Vorschlag:** `launchctl bootstrap gui/$(id -u) <plist>` für Install und `launchctl bootout` für Uninstall verwenden, oder macOS-Version abfragen und Befehl dynamisch wählen.
**Aufwand:** S

---

### H12: `start_pipeline` — offener stdout-Handle blockiert bei >64 KB Output — app/backend
**Datei:** `app/backend/subprocess_runner.py:36–52`
**Impact:** Wenn `log_callback=None`, wird `stdout=PIPE` gesetzt aber nie gelesen. Kernel-Pipe-Buffer (64 KB) füllt sich; Kindprozess blockiert dauerhaft in `write()`-Syscall. Popen-Handle bleibt offen → Ressourcenleck.
**Fix-Vorschlag:** Ohne `log_callback` `stdout=subprocess.DEVNULL` verwenden.
**Aufwand:** S

---

### H13: Division by Zero bei `preis_pro_karte` wenn `anzahl_karten == 0` — app/backend
**Datei:** `app/backend/dashboard_aggregator.py:52`
**Impact:** `df[preis] / df[anzahl]` erzeugt bei `anzahl=0` `inf`, das durch alle Aggregationen propagiert und im Dashboard als `inf €` erscheint oder Durchschnitte verzerrt.
**Fix-Vorschlag:** `df[_ANZAHL_COL].replace(0, float("nan"))` vor der Division.
**Aufwand:** XS

---

### H14: Cutoff-Logik überspringt Anzeige, beendet Loop aber nicht — scraper/main
**Datei:** `scraper/willhaben_scraper.py:430–463`
**Impact:** Nach dem ersten Cutoff-Treffer (zu alte Anzeige) werden alle restlichen URLs trotzdem besucht, obwohl bei `sort=3` alle folgenden garantiert älter sind. Unnötiger Performance-Verlust von hunderten Requests pro Lauf.
**Fix-Vorschlag:** Nach erstem Cutoff-Treffer `stop_scraping = True` setzen.
**Aufwand:** S

---

### H15: Doppel-`asyncio.run` in `run_pipeline` — strukturell fragil für async-Integration — scraper/main
**Datei:** `main.py:93`, `main.py:129`
**Impact:** Zwei `asyncio.run()`-Aufrufe in derselben Funktion. Wird `run_pipeline()` je aus einem async-Kontext aufgerufen, scheitert es mit `RuntimeError: This event loop is already running`.
**Fix-Vorschlag:** `run_pipeline` als `async def run_pipeline_async()` mit `await scrape(...)` und `await check_events(...)` anlegen; synchronen Wrapper `run_pipeline()` als dünne Schicht behalten.
**Aufwand:** M

---

### H16: RuntimeWarning "coroutine was never awaited" — falsches Mock-Design, kein Artefakt — tests
**Datei:** `tests/test_main_cli.py:83`, `tests/test_main_cli.py:119`
**Impact:** `monkeypatch.setattr("main.asyncio.run", lambda coro: _fake_scrape())` ignoriert das `coro`-Argument. Die Coroutinen `scrape(...)` und `check_events(...)` werden nie awaited und nie geschlossen. In Python 3.12+ eskaliert das zu `ResourceWarning` und kann Testsessions zum Absturz bringen.
**Fix-Vorschlag:** `scraper.willhaben_scraper.scrape` direkt patchen statt `asyncio.run` zu ersetzen. Alternativ: Coroutine sauber schliessen via `coro.close()`.
**Aufwand:** M

---

### H17: Integration-Test für StatusWriter → status_monitor → status_to_display Kette fehlt — tests
**Datei:** `tests/test_v2_status_writer.py`, `tests/test_backend_status_monitor.py`, `tests/test_tabs_status.py`
**Impact:** Der CRITICAL-Mismatch C5 (`errors` vs. `errors_count`) wurde nur entdeckt weil alle drei Komponenten isoliert getestet werden. Ein End-to-End-Test hätte ihn sofort aufgedeckt.
**Fix-Vorschlag:** Integrationstest: `writer.error(...)` → `read_status(tmp_path)` → `status_to_display()` → `result["errors_count"]` assertieren.
**Aufwand:** S

---

### H18: `uninstall_plist` Erfolgsfall komplett ungetestet — tests
**Datei:** `tests/test_backend_launchd_manager.py:125`
**Impact:** Nur der "not found"-Pfad ist abgedeckt. Fehler im Happy-Path (fehlerhafter launchctl-Aufruf, OSError beim Löschen) werden nicht erkannt.
**Fix-Vorschlag:** Test hinzufügen: Plist erstellen, `launchctl unload` mocken (returncode 0), assertieren dass ok=True und Datei gelöscht.
**Aufwand:** S

---

## MEDIUM Findings (Zusammenfassung)

| #  | Titel                                                              | Layer        | Aufwand |
|----|--------------------------------------------------------------------|--------------|---------|
| M1 | `PARSE_CACHE_DIR.mkdir()` auf Modul-Ebene: Side-Effect beim Import | parser/v2    | XS      |
| M2 | `use_cache`-Parameter in `parse_ad()` deklariert aber ignoriert    | parser/v2    | XS      |
| M3 | LLM-Felder außerhalb Schema werden still verworfen, keine Drift-Detection | parser/v2 | S    |
| M4 | `datetime.now()` ohne Timezone in `attach_metadata()` — inkonsistent mit StatusWriter | parser/v2 | XS |
| M5 | `strip_nav_prefix()` O(n²)-ähnlich bei langen Texten              | parser/v2    | S       |
| M6 | Few-Shot-Beispiele im Prompt sind invalides JSON (unquoted Keys)  | parser/v2    | S       |
| M7 | `_call_chat` und `_call_generate` identisch strukturiert — Code-Duplizierung | parser/v2 | S |
| M8 | Kein `build()`-Aufruf in `__init__` — fehlendes Lifecycle-Pattern, AttributeError-Risiko | app/tabs | S |
| M9 | Unbegrenztes Wachstum des Log-ScrolledText — potenzieller Memory-Leak | app/tabs  | S       |
| M10| `_sort_and_apply` ist leerer Wrapper — tote Indirektion           | app/tabs     | XS      |
| M11| `_update_status_label()` in `build()` — fragile Widget-Aufbau-Reihenfolge | app/tabs | XS   |
| M12| `config_data` direkt mutiert, kein Lock/Observer — Tab-übergreifende Interferenz | app/tabs | M |
| M13| `hour`/`minute` Spinbox akzeptiert ungültige Werte (z. B. hour=99) | app/tabs    | XS      |
| M14| `_marge()` als Closure in Loop — Python-Closure-Binding-Falle bei Refactoring | app/backend | XS |
| M15| `load_excel` fängt generisches `Exception` — maskiert echte Fehler | app/backend | XS      |
| M16| `is_installed()` prüft nur Datei-Existenz, nicht ob Job wirklich geladen | app/backend | S   |
| M17| `stop()` wartet nach `SIGKILL` unbegrenzt — potenzieller UI-Deadlock | app/backend | XS    |
| M18| Keine Validierung von hour/minute in `generate_plist()` — silently ungültiges Plist | app/backend | XS |
| M19| `read_status` nicht thread-safe: partieller JSON-Read bei gleichzeitigem Write | app/backend | M |
| M20| `_is_first_run()` Race-Condition-anfällig und semantisch inkonsistent | scraper/main | S    |
| M21| `pages_to_load`-Berechnung trügerisch bei `max_listings=0` — stille Fehler | scraper/main | XS |
| M22| Regex-Fallback für Preis matcht ungewollte Strings aus dem gesamten Body | scraper/main | S  |
| M23| `skipped`-Statistik strukturell falsch — vermischt zu-alte, cache-hit, Fehler | scraper/main | S |
| M24| `typing.Callable` deprecated seit Python 3.10, Projekt läuft auf 3.14+ | scraper/main | XS |
| M25| `test_build_context_truncates` Assertion zu loose (`< 700` statt exakt `<= 500`) | tests | XS |
| M26| `test_run_pipeline_max_listings_truncates` beweist nur zweite Truncation, nicht erste | tests | M |
| M27| `test_parse_ads_uses_cache` mutiert globalen Modulzustand — fragil bei Parallelisierung | tests | S |
| M28| `test_extract_falls_back_to_gemma4` ignoriert Retry-Logik — kein Test für transiente ConnectionError | tests | S |
| M29| Kein Test für `uninstall_plist` wenn launchctl fehlschlägt oder OSError beim Löschen | tests | S |
| M30| `filter_df` gibt inkonsistent `None` oder DataFrame zurück — Test zementiert Bug | tests | S |
| M31| `test_invalid_model_choice_errors` startet echte Prozesse — Timeout-Risiko auf langsamen CI | tests | S |

---

## LOW / INFO Findings (Zusammenfassung)

**LOW (27 Findings):**
- Diverse ungenutzte Imports: `Any` (pipeline.py, postprocessing.py), `time` (extractor.py), `sys` (zeitplan.py), `math` (dashboard_aggregator.py), `import datetime` (test_excel_new_columns.py)
- `EMPTY_EVENT` ist mutierbares dict — sollte `MappingProxyType` sein (postprocessing.py)
- `_RETRY_EXCEPTIONS` PEP-8-Verletzung (Import-Reihenfolge, extractor.py)
- Inkonsistente Feldnamen `titel` vs. `title`, Umlaute in Keys (preprocessing.py, pipeline.py, postprocessing.py)
- Undokumentiertes `\beur\b`-Pattern (preprocessing.py)
- Tote State-Variablen `_filter_text`, `_sort_col` in dashboard.py
- Modellnamen nicht als Konstante ausgelagert (engine.py)
- `_search_var`/`_sort_var` in `build()` statt `__init__` erstellt — IDEs erkennen AttributeError nicht
- `subprocess_runner.stop()` existiert aber kein "Abbrechen"-Button in der GUI
- `willhaben_tracker_original.py` und `old_tracker.py` byte-identische Dead-Code-Dateien
- Zwei parallele Logging-Systeme: `print()` im Scraper, `logging.Logger` in main.py
- Cookie-Banner-Selektor-Listen zwischen Scraper und Original divergent
- `--ovp`-Branch ignoriert `--parser-version`-Argument — immer v1
- Dead Code: `_fake_scrape_async` definiert aber nie genutzt (test_main_cli.py)
- `time.sleep(0.1)` als Synchronisation im Test — klassischer Flaky-Test
- Inkonsistentes Import-Pattern (inner-function vs. module-level) in test_v2_*.py
- `conftest.py` enthält nur sys.path — könnte durch `pyproject.toml pythonpath` ersetzt werden
- Hardcoded `"Händler"`/`"Privat"` ohne Konstanten (dashboard_aggregator.py)
- `subprocess_runner` prüft nicht ob `python_path` ausführbar ist
- Duplizierter leerer-DataFrame-Rückgabecode an zwei Stellen (dashboard_aggregator.py)
- `_reader`-Thread ohne Namen (subprocess_runner.py)
- `test_excel_new_columns.py` fehlende Isolation, ungenutztes `import datetime`

**INFO (18 Findings):**
- Kein einziges Test-File in parser/v2/ — gesamte Parse-Logik ungetestet
- Kein Test für app/tabs Lifecycle (build → Widget-State), Settings-Pfad, Install-Pfad
- `StatusWriter._write()` verschluckt alle Exceptions lautlos — keine Diagnose bei Disk-Fehlern
- `build_context()` kann mid-sentence truncaten (semantisch, kein Bug)
- Kein Ollama-Modell-Version-Pinning — Ausgabeverhalten kann sich ohne Code-Änderung ändern
- `__init__.py` in app/tabs leer — kein explizites `__all__`
- Kein Timeout bei `_TEMPLATE_PATH.read_text()` — blockiert bei Netzlaufwerk
- `test_start_pipeline_with_max_listings_adds_arg` testet falschen Prozess (auch als CRITICAL C6 geführt)
- `uninstall_plist` hat keinen Test für den Erfolgsfall (auch als HIGH H18 geführt)
- `avg_duration_ms` — Einheit undokumentiert, kann Sekunden sein
- Keine Exception-Behandlung wenn Plist-Template fehlt (generate_plist)
- `WorkingDirectory` zwischen launchd_manager und subprocess_runner ungekoppelt
- Kein Test für `scrape()`-Funktion selbst (0 Unit-Tests für willhaben_scraper.py)
- `max_listings`-Truncation in main.py nach scrape() ist No-Op — toter Code
- Kein Gesamttimeout für den Scraping-Run — Daemon kann bei hängendem Browser ewig blockieren
- `TARGET_URL` enthält undokumentierte `sort=3`-Abhängigkeit (Cutoff-Logik hängt davon ab)
- Security: Kein Test für Path-Traversal bei Plist-Label-Input
- Security: Kein Test für fehlerhafte/bösartige JSON-Inputs im Status-File
- Kein Test für `--test-batch` CLI-Pfad

---

## Deduplizierung / Layer-übergreifende Patterns

### Pattern 1: RuntimeWarning / Coroutine-Bug — scraper/main + tests (C: scraper CRITICAL + H16 tests HIGH)
Derselbe Fehler erscheint in zwei Layers: `scraper/main` identifiziert, dass der Test-Monkeypatch `asyncio.run` falsch ersetzt; `tests` beschreibt dasselbe als HIGH-Finding mit detaillierter Mock-Analyse. Nach Deduplizierung: 1 Findings-Cluster, Fix in den Tests.

### Pattern 2: Race Condition — parser/v2 + app/backend + app/tabs (H2 + M19 + H6)
Race Conditions tauchen in drei unabhängigen Layers auf: StatusWriter (parser/v2), status_monitor read/write (app/backend), und _proc-Attribut-Handling im GUI-Thread (app/tabs). Kein einheitliches Locking-Pattern existiert in der Codebase. Empfehlung: Locking-Strategie als Standard definieren.

### Pattern 3: Kein einheitliches Error-Handling — alle 5 Layers
`except Exception: pass` (pipeline.py, status_writer.py), generisches `except Exception` das leeres DataFrame zurückgibt (dashboard_aggregator.py), unkontrolliertes Propagieren von OS-Exceptions (launchd_manager.py), silent `None`-Return bei JSON-Fehler (status_monitor.py). Kein Error-Handling-Pattern ist definiert oder dokumentiert.

### Pattern 4: Timezone-Naivität — parser/v2 + app/backend (M4)
`datetime.now()` ohne Timezone in `attach_metadata()` vs. `datetime.now(timezone.utc)` in `StatusWriter`. Gemischte naive/aware Datetimes im selben Datensatz führen bei Zeitvergleichen zu stillen Fehlern.

### Pattern 5: Dead Code Akkumulation — scraper/main + tests + parser/v2
`willhaben_tracker_original.py` und `old_tracker.py` (byte-identisch), `_fake_scrape_async` (nie genutzt), `_filter_text`/`_sort_col` (nie geschrieben), ungenutzter `time`-Import, `typing.Any`-Import — mehrere unaufgeräumte Artefakte früherer Entwicklungsiterationen.

### Pattern 6: Fehlende Eingabevalidierung an Systemgrenzen — app/tabs + app/backend
`hour`/`minute` nicht validiert (tabs: M13 + backend: M18 identisch), `python_path` nicht auf Ausführbarkeit geprüft (backend: LOW), `label` nicht gegen Path-Traversal geschützt (tabs: H10 + backend: M-Bereich). Systemgrenzen-Validierung fehlt konsistent.

### Pattern 7: Tests falsch-positiv / testen das Falsche — tests (CRITICAL C5, C6, HIGH H16)
Mindestens 3 Tests sind strukturell falsch: sie sind grün, obwohl sie den Bug den sie testen sollen nicht aufdecken. Das ist gefährlicher als fehlende Tests — es erzeugt falsches Sicherheitsgefühl.

---

## Risiko-Heatmap

| Layer        | Logik         | Security      | Performance  | Tests         | Maintainability | Gesamt-Risiko |
|--------------|---------------|---------------|--------------|---------------|-----------------|---------------|
| parser/v2    | 🟡 MITTEL     | 🔴 HOCH       | 🟡 MITTEL    | 🔴 HOCH       | 🟡 MITTEL       | **HOCH**      |
| app/tabs     | 🔴 HOCH       | 🔴 HOCH       | 🟡 MITTEL    | 🔴 HOCH       | 🟡 MITTEL       | **HOCH**      |
| app/backend  | 🔴 HOCH       | 🔴 HOCH       | 🟡 MITTEL    | 🔴 HOCH       | 🟡 MITTEL       | **HOCH**      |
| scraper/main | 🟡 MITTEL     | 🔴 HOCH       | 🟡 MITTEL    | 🔴 HOCH       | 🟡 MITTEL       | **HOCH**      |
| tests        | 🔴 HOCH       | 🟡 MITTEL     | 🟢 NIEDRIG   | 🔴 HOCH       | 🟡 MITTEL       | **HOCH**      |

> Alle 5 Layer landen bei HOCH — getrieben durch Security-Findings in 4 von 5 Layers und falsch-positive Tests die Produktionsbugs maskieren.

---

## Top-10 Empfehlungen (nach ROI sortiert: Impact / Aufwand)

1. **`errors` vs. `errors_count` Field-Mismatch beheben** (C5) — Aktiver Produktionsbug; 1-Zeilen-Fix; sofortige Wirkung: GUI zeigt endlich echte Fehlerzahlen. Aufwand XS, Impact CRITICAL.

2. **`messagebox`-Import in status.py ergänzen** (H8) — 1-Zeilen-Fix behebt NameError beim Doppelklick. Aufwand XS, Impact HIGH.

3. **Hardcoded PII aus Code entfernen + Git-History bereinigen** (C4) — Code-Fix ist XS; History-Bereinigung mit BFG/filter-repo ist M. Ohne History-Bereinigung bleibt die PII in der History; bloßes Commit reicht nicht.

4. **`launchctl load` → `launchctl bootstrap` migrieren** (H11) — Auf macOS 13+ läuft der nächtliche Job still nie. Aufwand S, Impact HIGH (gesamte Scheduling-Funktion kaputt).

5. **`generate_plist` auf `plistlib` umstellen** (C2) — Eliminiert Template-Injection vollständig. Aufwand S, Impact CRITICAL Security; `plistlib` ist Stdlib, kein neuer Dependency.

6. **Korrektes Test-Mock für asyncio.run / Coroutine-Bug** (H16) — Verhindert `ResourceWarning`-Eskalation in Python 3.12+; macht die Test-Suite ehrlicher. Aufwand M, Impact HIGH.

7. **Integration-Test StatusWriter → status_monitor → status_to_display** (H17) — Hätte C5 präventiv verhindert; schützt vor zukünftigen Field-Mismatches. Aufwand S, langfristig hoher Wert.

8. **Allowlist-Validierung für model und parser_version vor Subprocess** (C3) — Schließt Command-Injection-Vektor. Aufwand S, Impact CRITICAL Security.

9. **`stop_scraping = True` nach erstem Cutoff-Treffer** (H14) — Reduziert überflüssige HTTP-Requests bei jedem Produktionslauf; einfache Änderung mit direktem Performance-Gewinn. Aufwand S.

10. **`_apply_filters` KeyError absichern + Division-by-Zero in Aggregator beheben** (H9 + H13) — Beide je XS-Aufwand; verhindert Dashboard-Crashs bei Edge-Case-Daten. Kombiniert hoher ROI.

---

## GO-Gate Phase A → Phase B

**Kriterium:** Sind CRITICAL Findings Produktions-Blocker die Phase B blockieren?

| Finding | Typ | Phase-B-relevant? | Einschätzung |
|---------|-----|-------------------|--------------|
| C1: Prompt-Injection (parser/v2) | Security | Ja — jede Produktion mit realen Anzeigen | **BLOCKER** |
| C2: Template-Injection → macOS-Persistence (app/backend) | Security | Ja — launchd-Installation ist Phase-B-Feature | **BLOCKER** |
| C3: Command-Injection via Config (app/tabs) | Security | Ja — Config-basiertes Deployment ist Phase-B-Feature | **BLOCKER** |
| C4: Hardcoded PII in Git-History (scraper) | Security/Privacy | Ja — bei Repo-Sharing oder Public-Deployment sofort kritisch | **BLOCKER** |
| C5: errors vs. errors_count Mismatch (GUI) | Aktiver Produktionsbug | Ja — Monitoring-Funktion komplett broken | **BLOCKER** |
| C6: Falscher Test (tests) | Testqualität | Nein — technisch kein Produktions-Blocker | NICHT-BLOCKER |

**5 von 6 CRITICAL Findings sind Produktions-Blocker für Phase B.**

**Empfehlung: NO-GO für Phase B.**

Begründung: Drei Security-Findings (C1, C2, C3) betreffen Deployment-Infrastruktur, die in Phase B ausgebaut werden soll — sie bei laufendem Ausbau zu beheben ist aufwändiger als jetzt. C4 (PII in History) ist vor jeglichem Repo-Sharing nicht verhandelbar. C5 ist ein aktiver Bug der das Monitoring bricht. Der Code-Fix-Aufwand für alle 5 Blocker beträgt zusammen schätzungsweise 1–2 Tage (Aufwände: XS, S, S, XS+M, S). Die Git-History-Bereinigung (C4) erfordert Koordination mit allen lokalen Klonen. **Empfehlung: Sprint "Phase A Hardening" (2–3 Tage) vor Phase-B-Start; alle 5 Blocker schließen, dann GO.**

---
*Audit durchgeführt am 2026-04-18. Alle Findings basieren auf statischer Code-Analyse der 5 Modul-Audit-Dateien. Keine Code-Änderungen wurden vorgenommen.*
