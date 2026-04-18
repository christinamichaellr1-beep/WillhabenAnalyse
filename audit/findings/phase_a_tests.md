# Phase A — tests/ Audit
**Geprüft:** 2026-04-18
**Findings gesamt:** 22 (CRITICAL: 2, HIGH: 5, MEDIUM: 7, LOW: 5, INFO: 3)

---

## [CRITICAL] test_start_pipeline_with_max_listings_adds_arg überprüft die falsche Ausgabe (test_backend_subprocess_runner.py:38)
**Dimension:** 1 — Logik-Fehler
**Impact:** Der Test ruft `start_pipeline()` auf (speichert den Prozess in `proc`), liest aber `out` aus `proc.communicate()` — und ignoriert diesen Wert vollständig. Stattdessen erstellt er einen zweiten Prozess `proc2`, der dieselbe main.py *direkt* aufruft, und assertiert auf dessen Ausgabe. Damit beweist der Test ausschliesslich, dass Python argv korrekt ausgeben kann — nicht dass `start_pipeline()` den Parameter `--max-listings=350` weitergibt. Der Test ist grün auch wenn `start_pipeline()` `max_listings` vollständig ignoriert.
**Fix-Vorschlag:** `out` aus `proc.communicate()` für die Assertion verwenden. `proc2` entfernen. Assertion: `assert "--max-listings=350" in out`.
**Aufwand:** XS

---

## [CRITICAL] "errors" vs "errors_count" — Feldname-Mismatch zwischen StatusWriter und StatusTab (test_tabs_status.py:46)
**Dimension:** 1 — Logik-Fehler
**Impact:** `parser/v2/status_writer.py` schreibt in die JSON-Datei das Feld `"errors_count"`. `app/tabs/status.py` (und damit `status_to_display()`) liest jedoch `status.get("errors", 0)` — ein Feld, das nie vom StatusWriter gesetzt wird. Im echten Betrieb zeigt die GUI immer "Fehler: 0", egal wie viele Fehler aufgetreten sind. Die Tests in `test_tabs_status.py` konstruieren die Test-Dicts manuell mit `"errors": 1` — das entspricht nicht dem echten JSON-Output des StatusWriters, sondern maskiert genau diesen Mismatch. Alle drei `status_to_display`-Tests sind daher falsch positiv: sie testen mit handgestrickten Dicts statt mit dem Output von `StatusWriter.update/error()`.
**Fix-Vorschlag:** In `status.py` `status.get("errors_count", 0)` verwenden ODER `status_writer.py` auf `"errors"` umbenennen. Tests sollen reale `StatusWriter`-Output-Dicts verwenden, nicht hartcodierte Dicts.
**Aufwand:** S

---

## [HIGH] Kein Integration-Test für StatusWriter → status_monitor → status_to_display Kette (test_v2_status_writer.py, test_backend_status_monitor.py, test_tabs_status.py)
**Dimension:** 6 — Testabdeckung
**Impact:** Die drei Komponenten werden ausschliesslich in Isolation getestet. Der CRITICAL-Mismatch (siehe oben) existiert genau weil kein einziger Test die gesamte Kette `StatusWriter schreibt → status_monitor liest → status_to_display rendert` durchläuft. Ein echter End-to-End-Test hätte den `errors_count`-Bug sofort gefunden.
**Fix-Vorschlag:** Einen Integrationstest hinzufügen: `writer.error(...)` aufrufen, die Datei mit `read_status(tmp_path)` lesen, das Ergebnis durch `status_to_display()` schicken und `result["errors"]` assertieren.
**Aufwand:** S

---

## [HIGH] RuntimeWarning "coroutine was never awaited" ist ein echter Fehler, kein Artefakt (test_main_cli.py:83,119)
**Dimension:** 1 — Logik-Fehler
**Impact:** `monkeypatch.setattr("main.asyncio.run", lambda coro: _fake_scrape())` ersetzt `asyncio.run` durch eine Lambda, die das `coro`-Argument ignoriert. Da `main.run_pipeline()` zweimal `asyncio.run()` aufruft (einmal für `scrape()`, einmal für `check_events()` im OVP-Schritt), erzeugt Python korrekte RuntimeWarnings: die Coroutinen `scrape(...)` und `check_events(...)` werden als Objekte übergeben, aber nie awaited. Das ist kein harmloses Mock-Artefakt — es ist ein echter Bug im Mock-Design. Die `_fake_scrape_async()` Funktion (Zeile 73) wurde offensichtlich als korrekte Lösung begonnen, aber nie in den Test integriert. Ausserdem ist das OVP-Modul via `sys.modules` gemockt — aber `asyncio.run` wird für `check_events` trotzdem aufgerufen, weil der Mock zu grob ist.
**Fix-Vorschlag:** Korrekte Mock-Strategie: `monkeypatch.setattr("scraper.willhaben_scraper.scrape", _fake_scrape_async)` statt `asyncio.run` zu ersetzen. Alternativ: `asyncio.run` via `lambda coro: asyncio.get_event_loop().run_until_complete(coro) if asyncio.iscoroutine(coro) else coro` — aber das schlägt fehl. Sauberste Lösung: scraper-Import in `run_pipeline` herausziehen und direkt mocken.
**Aufwand:** M

---

## [HIGH] test_uninstall_plist_not_found testet keine erfolgreiche Deinstallation (test_backend_launchd_manager.py:125)
**Dimension:** 6 — Testabdeckung
**Impact:** Der Erfolgsfall von `uninstall_plist()` — Datei existiert, launchctl unload erfolgreich, Datei wird gelöscht, (True, msg) zurückgegeben — ist nicht getestet. Nur der "not found"-Pfad ist abgedeckt. Fehler im Erfolgsfall (z.B. fehlerhafter launchctl-Aufruf, OSError beim Löschen) werden nicht erkannt.
**Fix-Vorschlag:** Test hinzufügen: `plist_path` erstellen, `launchctl unload` via `subprocess.run` mocken mit `returncode=0`, `uninstall_plist()` aufrufen, assertieren dass `ok is True` und die Datei gelöscht wurde.
**Aufwand:** S

---

## [HIGH] test_invalid_model_choice_errors und test_invalid_parser_version_errors starten echte Prozesse mit --once (test_main_cli.py:36,40)
**Dimension:** 4 — Performance / 6 — Testabdeckung
**Impact:** Diese CLI-Tests rufen `main.py --model unknown-model --once` und `main.py --parser-version v99 --once` auf. Sie testen nur, ob argparse den Input ablehnt (returncode != 0). Das ist korrekt — aber timeout=10s bei Subprocess-Tests ist riskant. Wenn argparse den Fehler nicht sofort wirft, sondern erst nach Initialisierung, könnten Datenbankzugriffe, Log-Datei-Erstellungen oder Imports seiteneffektreich laufen. Es fehlt ausserdem ein Test für `--model valid_choice --once` der abbricht, bevor echter Scraping-Code läuft.
**Fix-Vorschlag:** Tests präzisieren: explizit `--help` für argparse-Tests nutzen. Für den Return-Code-Test: `_run("--help", "--model", "unknown")` wäre sofortig und sicher.
**Aufwand:** S

---

## [HIGH] Kein Test für cache-Korruption in parse_ads (test_v2_pipeline.py)
**Dimension:** 6 — Testabdeckung
**Impact:** `pipeline._load_cache()` hat einen `except Exception: pass`-Block — korrupte JSON-Cache-Dateien werden still ignoriert und die Anzeige wird als "nicht gecacht" behandelt. Es gibt keinen Test der verifiziert, dass bei einer korrupten Cache-Datei trotzdem ein Ollama-Aufruf erfolgt. Dieses Silent-Ignore-Verhalten ist kritisch für die Datenvollständigkeit.
**Fix-Vorschlag:** Test hinzufügen: korruptes JSON in `tmp_path / "{ad_id}.json"` schreiben, `parse_ads` aufrufen — assertieren, dass `mp.call_count == 1` (Ollama wurde trotzdem aufgerufen).
**Aufwand:** S

---

## [MEDIUM] test_build_context_truncates_to_max_chars: Assertion zu loose (test_v2_preprocessing.py:96)
**Dimension:** 1 — Logik-Fehler
**Impact:** Die Assertion lautet `assert len(ctx) < 700` mit dem Kommentar "overhead von Titel+Preis-Zeilen eingerechnet". Das ist eine sehr lose Schranke für einen `max_chars=500`-Aufruf. Wenn die Implementierung den Titel oder Preis-Block um mehrere hundert Zeichen aufbläht, würde der Test trotzdem grün bleiben. Die benachbarte `test_build_context_default_max_chars_is_6000` macht es besser: sie assertiert den Textteil direkt.
**Fix-Vorschlag:** Assertion strenger machen: den Beschreibungs-Teil gezielt extrahieren und assertieren, dass er `<= 500` Zeichen hat — analog zum Default-Test.
**Aufwand:** XS

---

## [MEDIUM] test_run_pipeline_max_listings_truncates testet doppelte Truncation (test_main_cli.py:95)
**Dimension:** 1 — Logik-Fehler
**Impact:** In `run_pipeline()` (main.py:105) wird `ads = ads[:max_listings]` angewendet, **nachdem** `asyncio.run(scrape(max_listings=max_listings))` bereits `max_listings` als Parameter übergeben hat. D.h. die Truncation passiert zweimal: einmal im Scraper-Aufruf und einmal danach. Der Test mockt `asyncio.run` so, dass er 5 Ads zurückgibt (unabhängig von `max_listings`-Übergabe an scrape), und prüft dann, dass nach `[:3]` nur 3 übrig sind. Der Test beweist die zweite Truncation, aber nicht, ob die erste (Übergabe von `max_listings` an `scrape()`) korrekt funktioniert. Ausserdem: `_fake_parse_ads` hat Signatur `(ads, **kwargs)` — wenn die echte `parse_ads` eine andere Signatur hätte, würde das nicht auffallen.
**Fix-Vorschlag:** Explizit assertieren, dass `scrape` mit dem korrekten `max_listings`-Argument aufgerufen wurde. `asyncio.run` nicht zu grob patchen — stattdessen `scraper.willhaben_scraper.scrape` direkt patchen.
**Aufwand:** M

---

## [MEDIUM] test_parse_ads_uses_cache_on_second_call mutiert globalen Modulzustand (test_v2_pipeline.py:136)
**Dimension:** 5 — Konsistenz / 7 — Maintainability
**Impact:** Der Test setzt `pipeline.PARSE_CACHE_DIR = tmp_path` direkt auf einem Modul-Level-Attribut und restauriert es mit `finally`. Das ist fragil: wenn der Test abbricht, bevor das `try`-Körper läuft, oder wenn andere Tests parallel laufen, kann `PARSE_CACHE_DIR` im falschen Zustand bleiben. Zusätzlich: `PARSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)` wird beim Import ausgeführt — d.h. beim Import-Zeitpunkt wird bereits ein echtes Verzeichnis auf dem Dateisystem angelegt (`data/parse_cache_v2/`). Das ist ein unerwünschter Seiteneffekt beim Importieren des Moduls in Tests.
**Fix-Vorschlag:** `PARSE_CACHE_DIR` nicht direkt mutieren. Stattdessen `parse_ad` so umstrukturieren, dass es `cache_dir` als Parameter akzeptiert. Alternativ: `monkeypatch.setattr(pipeline, "PARSE_CACHE_DIR", tmp_path)` verwenden (automatisches Teardown).
**Aufwand:** S

---

## [MEDIUM] test_extract_falls_back_to_gemma4_on_primary_failure ignoriert Retry-Logik (test_v2_extractor.py:54)
**Dimension:** 1 — Logik-Fehler
**Impact:** `_call_chat` und `_call_generate` sind mit `@retry(stop=stop_after_attempt(3))` dekoriert. Wenn `mock_post.side_effect = [Exception("connection refused"), ...]`, löst `tenacity` standardmässig 3 Versuche aus, bevor es aufgibt. Der Mock hat aber nur 1 Exception für primary + 1 Antwort für fallback. Das kann zu unerwartetem Verhalten führen: tenacity consumed die 3 Retry-Slots aus dem Side-Effect-Array. Da `requests.exceptions.ConnectionError` und `Timeout` gretried werden, aber `Exception` nicht (nur spezifische Typen — `retry=retry_if_exception_type(_RETRY_EXCEPTIONS)`), wird eine blanke `Exception("connection refused")` **nicht** retried. Der Mock ist zufällig korrekt, aber aus den falschen Gründen — kein einziger Test verifiziert, dass transiente `ConnectionError`-Exceptions wirklich 3x retried werden.
**Fix-Vorschlag:** Expliziten Test hinzufügen: `mock_post.side_effect = [requests.exceptions.ConnectionError(), requests.exceptions.ConnectionError(), _mock_chat_response(VALID_JSON)]` — assertieren, dass das Ergebnis erfolgreich zurückkommt und `call_count == 3`.
**Aufwand:** S

---

## [MEDIUM] Kein Test für uninstall_plist wenn launchctl fehlschlägt (test_backend_launchd_manager.py)
**Dimension:** 6 — Testabdeckung
**Impact:** `uninstall_plist()` hat einen Fehlerfall: die Plist-Datei existiert, aber `launchctl unload` gibt `returncode != 0` zurück. Dieser Pfad ist ungetestet. Ebenso ungetestet: `OSError` beim Löschen der Plist-Datei nach erfolgreichem `launchctl unload`.
**Fix-Vorschlag:** Zwei Tests hinzufügen — einer für launchctl-Fehler beim Unload, einer für OSError beim Datei-Löschen.
**Aufwand:** S

---

## [MEDIUM] Dashboard-Tests: filter_df None-Rückgabe ist nicht spezifiziert (test_tabs_dashboard.py:44)
**Dimension:** 1 — Logik-Fehler
**Impact:** `test_apply_filters_with_none` assertiert `result is None`. Die Implementierung von `filter_df` in dashboard.py gibt bei `df is None` tatsächlich `None` zurück (durch `if df is None or df.empty: return df`). Das ist ein Designproblem: die Funktion hat keinen konsistenten Rückgabetyp (kann `None` oder `pd.DataFrame` sein). Der Test zementiert dieses inkonsistente Verhalten als "korrekt" — ein refactoring-feindlicher Test.
**Fix-Vorschlag:** `filter_df` sollte immer einen DataFrame zurückgeben (leeren DataFrame statt `None`). Test entsprechend anpassen.
**Aufwand:** S

---

## [LOW] Dead Code: _fake_scrape_async nie verwendet (test_main_cli.py:73)
**Dimension:** 2 — Dead Code
**Impact:** In `test_run_pipeline_max_listings_truncates` wird `async def _fake_scrape_async()` definiert aber nie genutzt. Sie wurde offenbar während der Entwicklung des Mocks erstellt und vergessen. Erzeugt ausserdem eine RuntimeWarning wenn Python die ungenutzte Coroutine erkennt.
**Fix-Vorschlag:** `_fake_scrape_async` und den ungenutzten `import asyncio` am Anfang des Tests entfernen. (asyncio ist bereits auf Modulebene importiert.)
**Aufwand:** XS

---

## [LOW] conftest.py enthält nur sys.path-Manipulation — keine Fixtures (conftest.py:1)
**Dimension:** 2 — Dead Code / 7 — Maintainability
**Impact:** `conftest.py` hat ausschliesslich `sys.path.insert(...)`. Es gibt keine Pytest-Fixtures. Das ist minimal und zweckmässig, aber wenn man `pyproject.toml` oder `setup.py` mit `pythonpath = ["."]` konfigurieren würde, wäre auch dieser Code überflüssig. Kein echter Bug.
**Fix-Vorschlag:** `pyproject.toml` mit `[tool.pytest.ini_options] pythonpath = ["."]` ausstatten und `conftest.py` entfernen oder für echte Fixtures verwenden.
**Aufwand:** XS

---

## [LOW] Inkonsistentes Import-Pattern: direkte Imports im Test-Body statt auf Modulebene (alle test_v2_*.py)
**Dimension:** 5 — Konsistenz
**Impact:** In allen `test_v2_*.py`-Dateien werden Imports innerhalb jeder Testfunktion durchgeführt (`from parser.v2.postprocessing import parse_raw`). In `test_backend_*.py`-Dateien dagegen stehen Imports auf Modulebene. Beide Patterns sind technisch valide, aber die Inkonsistenz erschwert das schnelle Lesen und macht Code-Navigation schwieriger. Die Intra-Function-Imports machen Dependency-Probleme bei Import-Zeit unsichtbar.
**Fix-Vorschlag:** Alle Test-Imports auf Modulebene verschieben (einheitliches Pattern). Ausnahmen nur wenn der Import selbst getestet werden soll.
**Aufwand:** S

---

## [LOW] test_backend_subprocess_runner.py: time.sleep(0.1) als Synchronisation (test_backend_subprocess_runner.py:78)
**Dimension:** 4 — Performance / 5 — Konsistenz
**Impact:** In `test_start_pipeline_log_callback_receives_output` wird `time.sleep(0.1)` verwendet, um dem Reader-Thread Zeit zu geben. Das ist ein klassischer Flaky-Test: auf sehr langsamen CI-Maschinen könnte 100ms nicht ausreichen. Der richtige Ansatz ist, den Thread zu joinen.
**Fix-Vorschlag:** Den Reader-Thread zurückgeben oder einen `threading.Event` verwenden, der nach Lesen des letzten Output-Lines gesetzt wird. Alternativ: `proc.wait()` reicht in diesem Fall, da das Prozess-Ende impliziert, dass stdout geschlossen und der Thread beendet ist — aber `proc.wait()` wird bereits aufgerufen, das sleep danach ist also tatsächlich redundant.
**Aufwand:** XS

---

## [LOW] test_excel_new_columns.py: Keine Isolation zwischen Tests — gemeinsamer Import-State (test_excel_new_columns.py)
**Dimension:** 7 — Maintainability
**Impact:** Die vier Tests importieren alle `from export.excel_writer import MAIN_COLUMNS` oder `upsert_events`. Der `MAIN_FIELDS`-Import in `test_upsert_writes_new_fields_to_excel` (Zeile 34) importiert `MAIN_FIELDS` aus `excel_writer` — dieser Name muss existieren. Wenn er fehlt, fällt der Test mit ImportError. Ein Test für `MAIN_FIELDS` vs. `MAIN_COLUMNS` Konsistenz fehlt (sind das unterschiedliche Dinge?). `import datetime` auf Zeile 2 wird in keinem der Tests verwendet.
**Fix-Vorschlag:** `import datetime` entfernen. Exportierte Namen aus `excel_writer` explizit dokumentieren. Separate Tests für `MAIN_FIELDS` falls das eine andere Datenstruktur ist.
**Aufwand:** XS

---

## [INFO] Security: Kein Test für Path-Traversal bei Plist-Label-Input (test_backend_launchd_manager.py)
**Dimension:** 3 — Security
**Impact:** `install_plist()` und `uninstall_plist()` verwenden `label` direkt im Dateipfad: `_LAUNCH_AGENTS_DIR / f"{label}.plist"`. Ein label wie `"../../../etc/cron.d/evil"` würde zu einem path-traversal führen. Kein Test prüft, ob der label sanitiert wird. In der Praxis kommt der label aus der GUI, aber Verteidigung in der Tiefe fehlt.
**Fix-Vorschlag:** Test hinzufügen: `install_plist("<plist/>", "../etc/evil")` aufrufen und assertieren, dass entweder ein Fehler geworfen wird oder der Pfad korrekt begrenzt bleibt. Implementation sollte `label.replace("/", "").replace("..", "")` oder `Path(label).name` zur Sanitierung nutzen.
**Aufwand:** S

---

## [INFO] Security: Keine Tests für fehlerhafte/bösartige JSON-Inputs im Status-File (test_backend_status_monitor.py)
**Dimension:** 3 — Security
**Impact:** `read_status()` in `status_monitor.py` liest eine JSON-Datei die potentiell von externen Prozessen geschrieben wird. Tests für ungültiges JSON existieren (`test_read_status_returns_none_on_invalid_json`), aber keine für: sehr grosse Dateien (DoS), verschachtelte Strukturen mit Tiefe > 100 (JSON-Bomb), oder Werte die beim Rendern in der GUI Fehler werfen (z.B. extrem langer `last_error`-String).
**Fix-Vorschlag:** Test für sehr langen `last_error`-String (>10.000 Zeichen) und deep-nested JSON hinzufügen. `read_status()` sollte Dateigrösse limitieren.
**Aufwand:** M

---

## [INFO] Kein Test für den --test-batch CLI-Pfad in main.py (test_main_cli.py)
**Dimension:** 6 — Testabdeckung
**Impact:** `test_main_cli.py` testet `--help`, `--model`, `--parser-version`, `--max-listings` und `run_pipeline()` direkt. Der `--test-batch` Code-Pfad (main.py:258–282) — der raw_cache liest und `parse_ads` mit `use_cache=False` aufruft — ist vollständig ungetestet. Gerade dieser Pfad ist produktionsnah (Entwickler nutzen ihn für Debugging).
**Fix-Vorschlag:** Test für `--test-batch 5` hinzufügen: temp raw_cache mit Dummy-JSONs erstellen, `_run("--test-batch", "5")` aufrufen, assertieren, dass stdout valides JSON ist.
**Aufwand:** M

---

## [INFO] test_tabs_*: import-only Tests haben wenig Wert ohne Build-Aufruf (test_tabs_dashboard.py:9, test_tabs_engine.py:13, test_tabs_status.py:9, test_tabs_zeitplan.py:9)
**Dimension:** 7 — Maintainability
**Impact:** `test_*_imports_cleanly` und `test_*_class_exists` testen nur, ob das Modul importiert werden kann und die Klasse definiert ist. Das fängt Syntaxfehler ab, aber nicht viel mehr. Da `.build()` Tk-Widgets erstellt, ist es schwer headless zu testen — aber reine UI-Logik (wie `_save_settings`, `_load_data`, `_update_status_label`) könnte mit stärker gemockten Tk-Objekten getestet werden.
**Fix-Vorschlag:** Erwägen, `build()` über `unittest.mock.MagicMock()` als Eltern-Widget headless aufzurufen (tkinter ist auf macOS verfügbar). Zumindest `_save_settings`-Logik in eine Hilfsmethode extrahieren, die ohne Tk testbar ist.
**Aufwand:** L

---

## Zusammenfassung nach Dimension

| Dimension | Findings |
|---|---|
| 1 — Logik-Fehler | CRITICAL×2, MEDIUM×2 + anteilig HIGH×1 |
| 2 — Dead Code | LOW×2 |
| 3 — Security | INFO×2 |
| 4 — Performance | HIGH×1, LOW×1 |
| 5 — Konsistenz | MEDIUM×1, LOW×1 |
| 6 — Testabdeckung | HIGH×4, MEDIUM×2, INFO×2 |
| 7 — Maintainability | MEDIUM×2, LOW×2, INFO×1 |

## Priorisierungsliste (Top 5 sofort angehen)

1. **CRITICAL** — `test_start_pipeline_with_max_listings_adds_arg` testet falschen Prozess — echter Bug im Test
2. **CRITICAL** — `errors` vs `errors_count` Feldname-Mismatch — echter Produktionsbug, Test maskiert ihn
3. **HIGH** — RuntimeWarning in test_main_cli.py — kein Mock-Artefakt, falsches Mock-Design
4. **HIGH** — Integration-Test für StatusWriter→status_monitor→status_to_display fehlt
5. **HIGH** — `uninstall_plist` Erfolgsfall ungetestet
