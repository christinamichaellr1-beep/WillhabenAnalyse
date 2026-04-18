# Phase A — app/backend/ Audit
**Geprüft:** 2026-04-18
**Findings gesamt:** 22 (CRITICAL: 1, HIGH: 4, MEDIUM: 7, LOW: 6, INFO: 4)

---

## [CRITICAL] Template-Injection über `label`, `python_path`, `project_dir`, `model` (launchd_manager.py:33)
**Dimension:** Security
**Impact:** `generate_plist()` verwendet Python's `str.format()` direkt auf dem Template. Alle Platzhalter werden ungefiltert eingesetzt. Ein bösartiger oder fehlerhafter `label`-Wert wie `{HOUR}extra` kann vorhandene Platzhalter überschreiben oder die XML-Struktur des Plists korrumpieren. Schlimmer: Enthält `project_dir` oder `label` spitze Klammern (`<`, `>`), wird valides Plist-XML erzeugt, das auf einen beliebigen Pfad zeigt — effektiv ein Path-Injection in den launchd-Agenten. `python_path` mit Payload `</string><string>/bin/bash</string><string>-c` würde eine komplett andere ProgramArguments-Liste einschleusen, die macOS beim nächsten Login ohne Rückfrage ausführt.
**Fix-Vorschlag:** Alle Werte vor dem Einsetzen mit XML-Escaping behandeln (`html.escape()` oder `xml.sax.saxutils.escape()`). Alternativ die plist-Datei programmatisch mit dem `plistlib`-Modul aus der Python-Standardbibliothek erzeugen — dann gibt es keine Template-Injection-Oberfläche.
**Aufwand:** S

---

## [HIGH] `launchctl load` ist seit macOS 13 (Ventura) deprecated — stiller Fehler im Betrieb (launchd_manager.py:57–64)
**Dimension:** Logik-Fehler
**Impact:** `launchctl load` wurde in macOS 13 Ventura durch `launchctl bootstrap` ersetzt. Auf Ventura+ gibt `launchctl load` returncode 0 zurück, aber der Agent wird nicht aktiviert (Laufzeitverhalten: kein Scheduling). Der Code prüft nur den returncode, interpretiert den Erfolg als echte Aktivierung — der Job läuft schlicht nicht. `launchctl unload` ist analog betroffen. Fehler erscheinen erst beim nächsten erwarteten Ausführungszeitpunkt.
**Fix-Vorschlag:** `launchctl bootstrap gui/$(id -u) <plist>` für install und `launchctl bootout gui/$(id -u) <plist>` für uninstall verwenden. Die macOS-Version abfragen (`platform.mac_ver()`) und je nach Version den richtigen Befehl wählen, oder ausschließlich die moderne API verwenden (setzt macOS ≥ 13 voraus).
**Aufwand:** S

---

## [HIGH] Race Condition: `uninstall_plist` prüft Existenz, dann löscht — keine atomare Operation (launchd_manager.py:76–89)
**Dimension:** Logik-Fehler
**Impact:** Zwischen `plist_path.exists()` (Z. 76) und `plist_path.unlink()` (Z. 87) kann ein anderer Prozess die Datei entfernen. `unlink()` wirft dann `FileNotFoundError`, der nicht als `OSError` gefangen wird (tatsächlich wird `OSError` gefangen, aber `FileNotFoundError` ist eine Unterklasse — hier korrekt gefangen). Kritischer: `launchctl unload` wird aufgerufen und schlägt mit einem Fehler fehl, bevor `unlink` überhaupt erreicht wird. Nach einem `unload`-Fehler wird `False` zurückgegeben, die Datei bleibt aber auf Disk — beim nächsten Start lädt launchd den verwaisten Job trotzdem.
**Fix-Vorschlag:** Nach `launchctl unload`-Fehler differenzieren: "already unloaded" ist kein fataler Fehler. `unlink()` in jedem Fall aufrufen (mit `missing_ok=True`). Reihenfolge umkehren: erst Datei löschen, dann unload — verhindert Re-Load bei Absturz.
**Aufwand:** S

---

## [HIGH] `start_pipeline` lässt `stdout`-Handle offen wenn kein `log_callback` angegeben (subprocess_runner.py:36–52)
**Dimension:** Performance / Logik-Fehler
**Impact:** Wenn `log_callback=None`, wird `stdout=subprocess.PIPE` gesetzt, aber kein Thread liest die Pipe. Der Kernel-Pipe-Buffer (typisch 64 KB) füllt sich, sobald der Prozess mehr Output erzeugt — der Kindprozess blockiert dann in seinem `write()`-Syscall. Die Pipeline hängt dauerhaft ohne Fehlermeldung. Der Parent-Prozess wartet nie auf das Kind, der Popen-Handle wird nie geschlossen → Ressourcenleck (offener Dateideskriptor).
**Fix-Vorschlag:** Wenn kein `log_callback` gewünscht ist, `stdout=subprocess.DEVNULL` (oder kein Capture) verwenden. Alternativ immer einen Reader-Thread starten und optional den Callback aufrufen. Eine `__del__`-Methode oder Context-Manager-Nutzung auf dem `Popen`-Objekt empfehlen.
**Aufwand:** S

---

## [HIGH] Division by Zero bei `preis_pro_karte`-Berechnung wenn `anzahl_karten == 0` (dashboard_aggregator.py:52)
**Dimension:** Logik-Fehler
**Impact:** `df[_PREIS_COL] = df[_GESAMT_COL] / df[_ANZAHL_COL]` — bei einem Eintrag mit `anzahl_karten=0` entsteht `inf` (float division) oder ein pandas-Warning. In der Folge propagiert `inf` durch alle `min/mean/max`-Berechnungen und erscheint im Dashboard als `inf €` oder verzerrt den Durchschnitt für die gesamte Gruppe. Ein Test für diesen Edge-Case existiert nicht.
**Fix-Vorschlag:** `df[_ANZAHL_COL].replace(0, float("nan"))` vor der Division, sodass betroffene Zeilen als `NaN` landen und durch `.dropna()` in `_stats()` automatisch ausgeschlossen werden.
**Aufwand:** XS

---

## [MEDIUM] `_marge()` wird als Closure in einer Loop-Iteration definiert — Python-Closure-Binding-Falle (dashboard_aggregator.py:106–109)
**Dimension:** Logik-Fehler
**Impact:** `_marge` wird innerhalb der `for`-Schleife definiert und liest `ovp` aus dem äußeren Scope via Closure. Das funktioniert korrekt, solange `_marge` sofort aufgerufen wird (Z. 120–121). Wird die Funktion aber jemals aus dem Loop heraus gespeichert oder verzögert aufgerufen (z.B. bei Refactoring), referenziert sie stets den letzten Wert von `ovp`. Das ist eine latente Wartbarkeits-Falle.
**Fix-Vorschlag:** `_marge` als Top-Level-Funktion mit `ovp` als Parameter definieren: `def _marge(avg: float, ovp: float) -> float`. Das entfernt die Closure-Abhängigkeit vollständig.
**Aufwand:** XS

---

## [MEDIUM] `load_excel` fängt generisches `Exception` — maskiert echte Fehler (dashboard_aggregator.py:26–27)
**Dimension:** Konsistenz / Logik-Fehler
**Impact:** `except (FileNotFoundError, Exception)` entspricht praktisch `except Exception` — `FileNotFoundError` ist redundant. Alle Exceptions (Syntaxfehler in openpyxl, MemoryError, ImportError) werden still geschluckt und durch ein leeres DataFrame ersetzt. Ein korruptes Excel mit z.B. falschem Schema gibt `pd.DataFrame()` zurück, was weiter oben als "keine Daten" interpretiert wird — der eigentliche Fehler ist unsichtbar.
**Fix-Vorschlag:** Nur die erwarteten Exceptions fangen: `ValueError` (falscher Sheet-Name), `FileNotFoundError`, `zipfile.BadZipFile` (korruptes xlsx). Alle anderen Exception-Typen nach oben durchreichen oder zumindest loggen.
**Aufwand:** XS

---

## [MEDIUM] `is_installed` prüft nur Datei-Existenz, nicht ob der Job wirklich geladen ist (launchd_manager.py:96–98)
**Dimension:** Logik-Fehler
**Impact:** Eine Plist-Datei kann auf Disk existieren, aber der launchd-Job kann nicht geladen sein (z.B. nach Neustart ohne Re-Login, oder nach manuellem `launchctl bootout`). GUI-Code, der `is_installed()` aufruft, zeigt "Installiert" an, obwohl kein Scheduling aktiv ist — irreführende Nutzerinformation.
**Fix-Vorschlag:** Den tatsächlichen Job-Status über `launchctl list {label}` (returncode 0 = geladen) prüfen. Oder `is_installed` in `plist_exists()` umbenennen und eine separate `is_loaded()` Funktion anbieten.
**Aufwand:** S

---

## [MEDIUM] `stop()` wartet nach `SIGKILL` unbegrenzt auf Child — potentieller Deadlock (subprocess_runner.py:68–69)
**Dimension:** Logik-Fehler / Performance
**Impact:** Nach `proc.kill()` folgt `proc.wait()` ohne Timeout. Ein Zombie-Prozess (der Elternprozess hat das Kind-Handle nie freigegeben) oder ein Prozess, der SIGKILL ignoriert (in einem nicht-präemptiven Kernel-Zustand wie D-State auf macOS), macht `proc.wait()` zu einem unbegrenzten Block. In einer GUI-Anwendung würde das den UI-Thread einfrieren.
**Fix-Vorschlag:** `proc.wait(timeout=3)` nach `proc.kill()` verwenden und bei `TimeoutExpired` einen Fehler loggen oder eine Exception werfen.
**Aufwand:** XS

---

## [MEDIUM] Keine Validierung von `hour` (0–23) und `minute` (0–59) in `generate_plist` (launchd_manager.py:16–41)
**Dimension:** Logik-Fehler
**Impact:** `generate_plist(hour=99, minute=-1, ...)` erzeugt ein syntaktisch valides Plist mit ungültigen `StartCalendarInterval`-Werten. launchd lädt die Datei ohne Fehler, aber der Job wird nie ausgeführt. Es gibt keinen Hinweis an den Nutzer auf die falsche Konfiguration.
**Fix-Vorschlag:** `if not (0 <= hour <= 23): raise ValueError(...)` und analog für `minute`. Tests für Boundary-Values ergänzen.
**Aufwand:** XS

---

## [MEDIUM] `read_status` nicht thread-safe: File-Read kann partiellen JSON-Inhalt lesen (status_monitor.py:14–17)
**Dimension:** Logik-Fehler / Performance
**Impact:** `status_file.read_text()` liest die gesamte Datei in einem Zug. Wenn der Pipeline-Prozess gleichzeitig in dieselbe Datei schreibt (kein Lock), kann `read_text` die Datei in einem partiellen Zustand lesen (truncated JSON). `json.JSONDecodeError` wird korrekt gefangen und `None` zurückgegeben — das verdeckt aber einen transienten Fehler, der regelmäßig im laufenden Betrieb auftreten kann, wenn Status-Updates häufig geschrieben werden.
**Fix-Vorschlag:** Atomisches Schreiben auf Schreiberseite erzwingen (Write to tmpfile, then `os.replace()`). Auf Leserseite: retry-Logik mit kurzem Backoff bei `None`-Return, oder File-Locking via `fcntl.flock`.
**Aufwand:** M

---

## [LOW] `math` importiert aber nur für `math.isnan` verwendet — `float('nan')` hat eingebaute `isnan`-Alternative (dashboard_aggregator.py:8)
**Dimension:** Dead Code / Konsistenz
**Impact:** `math.isnan(x)` ist äquivalent zu `x != x` (NaN-Eigenschaft) oder `pd.isna(x)`. Der Import ist nicht falsch, aber in einem pandas-zentrischen Modul wäre `pd.isna()` konsistenter und würde den `math`-Import überflüssig machen.
**Fix-Vorschlag:** `import math` durch `pd.isna()` in der `_marge`-Funktion ersetzen — ein Import weniger, einheitliches pandas-Idiom.
**Aufwand:** XS

---

## [LOW] Hardcoded `"Händler"`-String an zwei Stellen ohne Konstante (dashboard_aggregator.py:15, 93)
**Dimension:** Maintainability
**Impact:** `"Händler"` erscheint als Magic-String in `aggregate()` (Z. 93). `"Privat"` erscheint dreimal (Z. 58, 60, 92). Wird die Quelldaten-Bezeichnung geändert, müssen mehrere Stellen im Code gefunden und angepasst werden. Ein Tippfehler (z.B. `"Händler"` vs `"Haendler"`) würde silent zur falschen Gruppierung führen.
**Fix-Vorschlag:** Konstanten analog zu den bestehenden Column-Konstanten am Dateianfang definieren: `_TYP_PRIVAT = "Privat"` und `_TYP_HAENDLER = "Händler"`.
**Aufwand:** XS

---

## [LOW] `subprocess_runner.py` prüft nicht ob `python_path` ausführbar ist (subprocess_runner.py:26–42)
**Dimension:** Security / Maintainability
**Impact:** Enthält `python_path` Leerzeichen und wird von einem GUI-Widget als String (nicht Liste) übergeben, würde `subprocess.Popen` mit einer Liste arbeiten — hier korrekt. Das eigentliche Risiko: kein `os.access(python_path, os.X_OK)` vor dem Start. Fehlerhafte Pfade erzeugen eine `FileNotFoundError`-Exception, die vom Aufrufer unbehandelt bleiben kann.
**Fix-Vorschlag:** Vor dem `Popen`-Aufruf prüfen: `if not Path(python_path).is_file(): raise ValueError(...)`. Dem Aufrufer erlauben, auf den Fehler zu reagieren, statt eine rohe OS-Exception zu erhalten.
**Aufwand:** XS

---

## [LOW] Duplizierter Code: leeres DataFrame mit Column-Liste an zwei Stellen in `aggregate()` (dashboard_aggregator.py:40–45, 126–131)
**Dimension:** Maintainability
**Impact:** Die Liste der Spaltennamen `["Event", "Kategorie", "Datum", ...]` ist identisch an zwei Rückgabe-Punkten definiert. Bei Hinzufügen einer neuen Spalte muss die Liste an beiden Stellen gepflegt werden.
**Fix-Vorschlag:** Konstante `_RESULT_COLUMNS = [...]` am Modulanfang definieren und beide Stellen auf `pd.DataFrame(columns=_RESULT_COLUMNS)` reduzieren.
**Aufwand:** XS

---

## [LOW] `_reader`-Thread in `start_pipeline` hat keinen Namen — erschwertes Debugging (subprocess_runner.py:49)
**Dimension:** Maintainability
**Impact:** Der Thread heißt `Thread-N` im Debugger/Profiler. Bei mehreren gleichzeitig laufenden Pipelines sind die Threads nicht unterscheidbar.
**Fix-Vorschlag:** `threading.Thread(target=_reader, daemon=True, name=f"pipeline-reader-{proc.pid}")` — nach `proc.pid` bennenen, da die PID nach `Popen()` bekannt ist.
**Aufwand:** XS

---

## [INFO] Kein Timeout bei `_TEMPLATE_PATH.read_text()` in `generate_plist` — blocking auf Netzlaufwerk (launchd_manager.py:26)
**Dimension:** Performance
**Impact:** `_TEMPLATE_PATH` ist ein Pfad im App-Bundle. Bei Installation aus einem Netzlaufwerk oder SMB-Mount kann `read_text()` hängen. In einer GUI-Anwendung würde das den aufrufenden Thread blockieren.
**Fix-Vorschlag:** Template beim Modulstart einmal laden und als Modul-Konstante cachen: `_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")`. Dann tritt das Problem nur beim Import auf, nicht bei jedem `generate_plist()`-Aufruf.
**Aufwand:** XS

---

## [INFO] `test_start_pipeline_with_max_listings_adds_arg` testet nicht was behauptet wird (test_backend_subprocess_runner.py:38–59)
**Dimension:** Testabdeckung
**Impact:** Der Test startet zwei Subprozesse — einen mit `start_pipeline` (dessen Output nie gelesen wird) und einen manuell konstruierten. Es wird nur der manuelle Prozess geprüft. `start_pipeline` mit `max_listings=350` wird nie verifiziert. Der Test besteht immer, auch wenn `start_pipeline` das Argument vergisst.
**Fix-Vorschlag:** Den `log_callback` nutzen um den Output von `start_pipeline` direkt zu prüfen, oder `subprocess.Popen` mocken und `call_args` auf `--max-listings=350` prüfen.
**Aufwand:** S

---

## [INFO] `uninstall_plist`: kein Test für erfolgreichen Uninstall-Pfad (test_backend_launchd_manager.py)
**Dimension:** Testabdeckung
**Impact:** Es existiert nur ein Test für den Fall "Plist nicht gefunden". Der Happy-Path (Plist vorhanden, `launchctl unload` erfolgreich, Datei wird gelöscht) ist nicht getestet. Ein Regressionsfehler in der Erfolgs-Logik würde unentdeckt bleiben.
**Fix-Vorschlag:** Test analog zu `test_install_plist_success` hinzufügen: temporäre Plist-Datei anlegen, `subprocess.run` mocken (returncode 0), prüfen dass Datei nach `uninstall_plist()` nicht mehr existiert.
**Aufwand:** S

---

## [INFO] `avg_duration_ms` — Name suggeriert Millisekunden, Einheit wird nicht validiert (status_monitor.py:37–41)
**Dimension:** Konsistenz
**Impact:** Die Funktion gibt den Durchschnitt der Werte in `last_10_durations` zurück und dokumentiert "ms" im Namen. Die Einheit der Werte im JSON ist aber nicht spezifiziert — wenn der Schreiber Sekunden einträgt, gibt die Funktion "ms" zurück, obwohl es Sekunden sind. Kein Typ-Check, keine Docstring-Warnung.
**Fix-Vorschlag:** Docstring präzisieren: Einheit der Eingabewerte explizit nennen. Oder die Einheit aus dem Funktionsnamen entfernen und sie zur Verantwortung des Aufrufers machen.
**Aufwand:** XS

---

## [INFO] Kein `EnvironmentError`/`OSError` Handling in `generate_plist` wenn Template fehlt (launchd_manager.py:26)
**Dimension:** Konsistenz
**Impact:** `_TEMPLATE_PATH.read_text()` wirft `FileNotFoundError` wenn das Template nicht vorhanden ist (z.B. nach unvollständiger Installation). Diese Exception wird nicht gefangen und propagiert unkontrolliert bis zur GUI-Schicht, die dafür keine spezifische Behandlung hat.
**Fix-Vorschlag:** `try/except FileNotFoundError` mit einer aussagekräftigen Exception-Nachricht: `raise RuntimeError(f"plist template not found at {_TEMPLATE_PATH}") from exc`.
**Aufwand:** XS

---

## [INFO] `WorkingDirectory` im Plist stimmt mit `cwd` in `subprocess_runner.py` überein — Kopplung nicht dokumentiert (launchd_manager.py / subprocess_runner.py)
**Dimension:** Maintainability
**Impact:** Beide Module setzen `project_dir` als Arbeitsverzeichnis. Wird das Konzept in einem Modul geändert (z.B. auf ein separates Log-Dir), wird das andere nicht automatisch angepasst. Es gibt keinen gemeinsamen Konfigurationspunkt.
**Fix-Vorschlag:** Eine zentrale Konfigurationsklasse oder ein `config.py`-Modul einführen, das `project_dir` als Single Source of Truth hält. In Docstrings explizit auf die Abhängigkeit hinweisen.
**Aufwand:** M
