# Phase A — app/tabs/ Audit
**Geprüft:** 2026-04-18
**Dateien:** dashboard.py, engine.py, status.py, zeitplan.py, __init__.py
**Findings gesamt:** 22 (CRITICAL: 1, HIGH: 5, MEDIUM: 7, LOW: 6, INFO: 3)

---

## [CRITICAL] Command-Injection via model-String in subprocess_runner (engine.py:149 / status.py:157)
**Dimension:** Security
**Impact:** In `engine.py._start_test()` wird `self._model_var.get()` direkt als CLI-Argument an `subprocess_runner.start_pipeline()` übergeben. Dort landet der Wert als `f"--model={model}"` in einer List-Form von `Popen`. Da die Combobox auf `state="readonly"` gesetzt ist, scheint das zunächst sicher — aber `readonly` verhindert nur Tastatureingaben, nicht programmatische `StringVar.set()`-Aufrufe. Wird der Config-Wert aus einer manipulierten `config.json` geladen und in `_model_var` gesetzt, kann ein Angreifer mit Schreibzugriff auf die Config-Datei beim nächsten GUI-Start beliebige Argumente injizieren. Gleiches gilt für `parser_version` in `status.py._start_pipeline()`, das aus `config_data` ohne jede Validierung übernommen wird und in `--parser-version=<WERT>` eingebettet wird. `project_dir` (= `base_dir`) wird ebenfalls unvalidiert als `cwd` an Popen übergeben.
**Fix-Vorschlag:** Allowlist für `model` und `parser_version` vor dem Subprocess-Aufruf erzwingen. `project_dir` gegen Path-Traversal validieren (must be absolute, must exist). In `subprocess_runner.start_pipeline` explizit `shlex.quote` oder eine Allowlist anwenden, auch wenn List-Form üblicherweise injection-sicher ist — die Argumentation ist aber fragil, wenn sich `cmd` je ändert.
**Aufwand:** S

---

## [HIGH] Race Condition: `_proc`-Attribut aus Background-Thread gesetzt, im Main-Thread gelesen (engine.py:143–157)
**Dimension:** Logik-Fehler
**Impact:** In `_start_test()` wird `self._proc` innerhalb der Closure `_run()` gesetzt, die in einem Daemon-Thread läuft. Der Check `if self._proc is not None and subprocess_runner.is_running(self._proc)` in `_start_test()` läuft dagegen im UI-Thread **vor** dem Thread-Start. Zwischen dem Check und dem tatsächlichen `self._proc`-Setzen im Thread kann ein zweiter Klick auf "Test starten" durch den Check fallen und einen zweiten Prozess starten — der erste `_proc`-Wert wird dann durch den zweiten überschrieben, der ursprüngliche Prozess wird nie mehr referenziert und kann nicht gestoppt werden. Identisches Problem in `status.py._start_pipeline()` (Zeile 153–161).
**Fix-Vorschlag:** `_proc` sofort nach dem `Popen`-Aufruf zurückgeben oder eine `threading.Lock` verwenden. Besser: Den Button im UI während des Laufs deaktivieren (`state="disabled"`) und erst nach Prozessende reaktivieren.
**Aufwand:** S

---

## [HIGH] `_refresh`-Schleife bricht bei Fehler ab, ohne `_after_id` zu löschen (status.py:97–138)
**Dimension:** Logik-Fehler
**Impact:** `_refresh()` setzt `self._after_id` nur, wenn `status_monitor.is_running(status)` True ist. Wenn die Pipeline läuft und dann ein unerwarteter Fehler in `status_monitor.read_status()` oder in den `config`-Methoden auftritt, wird der `after`-Callback nie mehr registriert, aber `self._after_id` behält seinen alten Wert. `destroy()` ruft dann `self.after_cancel(old_id)` auf einem bereits abgelaufenen Callback auf — das ist zwar harmlos, aber der echte Fehler ist, dass die Refresh-Schleife ohne sichtbare Benachrichtigung stoppt. Der Nutzer sieht einfach keine aktualisierten Werte mehr.
**Fix-Vorschlag:** `_after_id` in `_refresh()` immer zu Beginn auf `None` zurücksetzen, bevor ein neuer Wert gesetzt wird. Außerdem nach dem Prozessende explizit einen letzten Refresh triggern und `_after_id = None` setzen.
**Aufwand:** XS

---

## [HIGH] `messagebox` in `status.py` importiert aber nie verwendet — fehlendes Import-Guard (status.py:10–19)
**Dimension:** Dead Code / Logik-Fehler
**Impact:** `status.py` importiert `messagebox` **nicht** im try-Block (fehlt in Zeile 17), ruft es aber in `_start_pipeline()` in Zeile 150 auf: `messagebox.showwarning(...)`. Da `messagebox` nicht importiert wurde, schlägt dieser Aufruf mit `NameError: name 'messagebox' is not defined` fehl, sobald der Guard-Path aktiv ist (headless) — aber auch im normalen Fall, weil der try-Block in `status.py` (Zeilen 11–20) `messagebox` tatsächlich nicht importiert. Dadurch ist der "Läuft bereits"-Guard in `_start_pipeline()` broken: Bei doppeltem Klick auf "Pipeline jetzt starten" tritt ein `NameError` auf statt der gewünschten Warnung.
**Fix-Vorschlag:** `from tkinter import scrolledtext, ttk, messagebox` in Zeile 17 ergänzen.
**Aufwand:** XS

---

## [HIGH] `_apply_filters` kann auf fehlende Spalten zugreifen ohne Absicherung (dashboard.py:155)
**Dimension:** Logik-Fehler
**Impact:** `df["Event"]` wird direkt referenziert ohne zu prüfen, ob die Spalte existiert. Wenn `dashboard_aggregator.aggregate()` ein DataFrame ohne "Event"-Spalte zurückgibt (z.B. leere Datei, andere Excel-Struktur), wirft das einen `KeyError`, der nicht abgefangen ist — `_apply_filters` hat keinen try/except-Block. Da `_apply_filters` auch direkt nach `_load_data` aufgerufen wird (Zeile 140), bricht der gesamte Ladevorgang mit einem unbehandelten Traceback ab.
**Fix-Vorschlag:** Vor dem `df["Event"]`-Zugriff prüfen: `if "Event" not in df.columns: return`. Alternativ den `_apply_filters`-Aufruf in `_load_data` in den bestehenden try/except einschließen.
**Aufwand:** XS

---

## [HIGH] launchd-Label wird nicht validiert — Path-Traversal in Dateiname möglich (zeitplan.py:131 / launchd_manager.py:50)
**Dimension:** Security
**Impact:** Der launchd-Label aus dem Entry-Widget wird direkt als Dateiname verwendet: `plist_path = _LAUNCH_AGENTS_DIR / f"{label}.plist"`. Ein Wert wie `../../evil` würde zu `~/Library/LaunchAgents/../../evil.plist` = `~/Library/evil.plist` führen. Zwar ist die direkte Eingabe im GUI sichtbar, aber der Wert wird aus `config_data` vorbelegt und könnte aus einer manipulierten Config stammen. Außerdem wird ein leerer Label (`label = ""`) silently akzeptiert und erzeugt `.plist` im LaunchAgents-Ordner.
**Fix-Vorschlag:** Label gegen Regex `^[a-zA-Z0-9._-]+$` validieren. Länge begrenzen (max. 128 Zeichen). In `launchd_manager.install_plist` sicherstellen, dass der resultierende Pfad innerhalb von `_LAUNCH_AGENTS_DIR` liegt.
**Aufwand:** S

---

## [MEDIUM] Kein `build()`-Aufruf in `__init__` — fehlendes Lifecycle-Pattern führt zu AttributeErrors (alle Tabs)
**Dimension:** Logik-Fehler / Konsistenz
**Impact:** Alle vier Tab-Klassen trennen Konstruktor und Widget-Aufbau: `__init__` initialisiert nur State-Variablen, Widgets werden erst durch explizites `build()` erzeugt. Alle `_`-Attribute (z.B. `self._tree`, `self._status_label`, `self._log`) existieren erst nach `build()`. Wenn ein externer Aufrufer vergisst, `build()` aufzurufen, oder wenn eine Methode wie `_refresh()` vor `build()` getriggert wird (z.B. durch `after(500, self._refresh)` in `_start_pipeline`), gibt es `AttributeError`. Es gibt kein Guard oder keinen Hinweis, dass `build()` Pflicht ist.
**Fix-Vorschlag:** Entweder `build()` am Ende von `__init__` aufrufen, oder eine `_built: bool`-Flag einführen und am Anfang jeder öffentlichen Methode prüfen. Alternativ alle Widget-Attribute in `__init__` mit `None` vorbelegen.
**Aufwand:** S

---

## [MEDIUM] Unbegrenztes Wachstum des Log-ScrolledText — potenzieller Memory-Leak (engine.py:101–111)
**Dimension:** Performance
**Impact:** `self._log` in `EngineTab` sammelt alle Ausgaben ohne Begrenzung. Bei langen Test-Läufen (z.B. N=9999 Listings mit vielen Stdout-Zeilen) kann das Text-Widget Megabytes an Daten akkumulieren. Tkinter-Text-Widgets speichern Inhalt im Tcl-Interpreter-Heap; sehr große Inhalte verlangsamen das UI spürbar und erhöhen den RAM-Verbrauch dauerhaft.
**Fix-Vorschlag:** In `_do_append_log` nach dem Einfügen prüfen, ob die Zeilenzahl > N (z.B. 2000) ist, und älteste Zeilen löschen: `self._log.delete("1.0", "2.0")`.
**Aufwand:** S

---

## [MEDIUM] `_sort_and_apply` ist ein leerer Wrapper — tote Indirektion (dashboard.py:167–168)
**Dimension:** Dead Code / Maintainability
**Impact:** `_sort_and_apply` delegiert 1:1 zu `_apply_filters`. Diese Indirektion suggeriert, dass `_sort_and_apply` künftig eigene Logik enthalten soll (z.B. Toggle ascending/descending), tut es aber nicht. Das "Sortieren"-Button-Command könnte direkt auf `_apply_filters` zeigen. Als tote Methode verwirrt es Entwickler und suggeriert fehlendes Verhalten.
**Fix-Vorschlag:** Entweder `command=self._apply_filters` direkt im Button setzen, oder `_sort_and_apply` mit einem Kommentar als Erweiterungspunkt kennzeichnen. Besser: Toggle-Logik implementieren (ascending/descending).
**Aufwand:** XS

---

## [MEDIUM] `_update_status_label()` in `build()` aufgerufen — Widget-Attribute noch nicht alle bereit (zeitplan.py:98)
**Dimension:** Logik-Fehler
**Impact:** `_update_status_label()` wird am Ende von `build()` aufgerufen (Zeile 98), aber `self._status_label` wird erst in Zeile 94 erstellt. Der Aufruf ist zwar korrekt geordnet, aber `_update_status_label()` ruft `launchd_manager.is_installed(label)` auf, was `_current_label()` braucht, das wiederum `self._label_var` referenziert. `_label_var` wird in Zeile 66–68 gesetzt, also vor dem Aufruf. Das funktioniert, ist aber eine fragile Abfolge, die beim Refactoring leicht bricht.
**Fix-Vorschlag:** `_update_status_label()` nach dem vollständigen Widget-Aufbau separat aufrufen oder eine explizite `refresh()`-Methode einführen, die nach `build()` aufgerufen wird.
**Aufwand:** XS

---

## [MEDIUM] `config_data` wird als mutable dict direkt mutiert — keine Defensive Copy (alle Tabs)
**Dimension:** Logik-Fehler / Maintainability
**Impact:** Alle Tabs empfangen `config_data` als Referenz und mutieren es direkt (z.B. `self.config_data["model"] = ...` in `engine.py:161`). Wenn mehrere Tabs auf dasselbe dict-Objekt zeigen (was bei normaler Initialisierung der Fall ist), können Tabs gegenseitig ihre Einstellungen überschreiben, wenn `_save_settings` in Tab A Werte schreibt, die Tab B gerade noch liest. Es gibt kein Lock und keine Observer-Benachrichtigung.
**Fix-Vorschlag:** `config_data` bei Änderung über ein zentrales Callback-Interface updaten (Event-Bus oder Observer-Pattern). Alternativ zumindest dokumentieren, dass alle Tabs dasselbe dict-Objekt teilen.
**Aufwand:** M

---

## [MEDIUM] `hour`/`minute`-Validierung prüft keine Wertebereiche (zeitplan.py:133–135)
**Dimension:** Logik-Fehler
**Impact:** `int(self._hour_var.get())` kann zwar geparst werden, aber eine Spinbox lässt sich durch direktes Eintragen von Werten außerhalb des Bereichs manipulieren (Tkinter-Spinboxen erzwingen keine Grenzen bei direkter Texteingabe). Werte wie `hour=99` oder `minute=-1` werden ohne Fehler in die Config geschrieben und ins Plist-XML interpoliert. Das erzeugt ein syntaktisch valides, aber semantisch ungültiges launchd-Plist.
**Fix-Vorschlag:** Nach dem `int()`-Cast explicit prüfen: `0 <= hour <= 23` und `0 <= minute <= 59`. Bei Verletzung `messagebox.showerror` und `return`. Gleiches in `_save_settings`.
**Aufwand:** XS

---

## [LOW] `sys` importiert aber nie direkt in `zeitplan.py` verwendet (zeitplan.py:2)
**Dimension:** Dead Code
**Impact:** `import sys` in `zeitplan.py` Zeile 2 — `sys.executable` wird nur in `_install()` (Zeile 144) verwendet. Das ist kein toter Import, aber er könnte durch einen Kommentar klarer als "Fallback Python-Pfad" markiert werden. Tatsächlich ist der Import in Ordnung, dies ist ein INFO-Grenzfall. Jedoch: `sys` wird nicht in `__init__`, `build` oder den statischen Hilfsmethoden benötigt; es ist ausschließlich in `_install` nötig.
**Fix-Vorschlag:** Kein zwingender Fix nötig. Optional: lokalen Import in `_install()` verwenden, um die Abhängigkeit zu minimieren.
**Aufwand:** XS

---

## [LOW] `_search_var` und `_sort_var` werden in `build()` erstellt, nicht in `__init__` (dashboard.py:59, 71)
**Dimension:** Konsistenz
**Impact:** In `engine.py` und `zeitplan.py` werden State-Variablen (`_model_var`, `_hour_var` etc.) ebenfalls in `build()` erzeugt. Das ist konsistent, aber widerspricht der Konvention, dass `__init__` alle Instanzvariablen deklarieren sollte. IDEs und statische Analysetools (mypy, pylance) können keine `AttributeError`-Risiken für diese Attribute erkennen. In `dashboard.py` ist `_df`, `_sort_col`, `_filter_text` in `__init__` gesetzt, aber `_search_var`, `_sort_var`, `_tree` nicht.
**Fix-Vorschlag:** Alle `self._`-Attribute in `__init__` mit `None` oder sinnvollen Defaults vorbelegen und in `build()` überschreiben.
**Aufwand:** S

---

## [LOW] Combobox-Wert `"gemma4:26b"` und `"gemma4:latest"` sind undokumentierte Modellnamen (engine.py:55)
**Dimension:** Maintainability
**Impact:** Die hartcodierten Modellnamen `["gemma3:27b", "gemma4:26b", "gemma4:latest"]` sind weder in einer Konstante noch in der Config ausgelagert. Sie sind ohne Kontext im Quellcode. Wenn sich die verfügbaren Modelle ändern, müssen sie an mehreren Stellen gepflegt werden (GUI + möglicherweise Backend-Validierung).
**Fix-Vorschlag:** Modellnamen in eine Konstante `AVAILABLE_MODELS` auslagern (z.B. in `app/backend/subprocess_runner.py` oder `app/constants.py`).
**Aufwand:** XS

---

## [LOW] `_filter_text: str = ""` in `__init__` gesetzt, aber nie geschrieben oder gelesen (dashboard.py:46)
**Dimension:** Dead Code
**Impact:** `self._filter_text` wird in `__init__` mit `""` initialisiert. Es gibt keine Stelle im Code, die diesen Wert schreibt oder liest. Der tatsächliche Filter-Text wird direkt per `self._search_var.get()` gelesen. `_filter_text` ist komplett toter State.
**Fix-Vorschlag:** `self._filter_text = ""` aus `__init__` entfernen.
**Aufwand:** XS

---

## [LOW] `_sort_col: str | None = None` in `__init__` gesetzt, aber nie geschrieben (dashboard.py:45)
**Dimension:** Dead Code
**Impact:** `self._sort_col` wird in `__init__` initialisiert, aber nirgendwo im Code geschrieben. Die Sortierung wird direkt per `self._sort_var.get()` gelesen. `_sort_col` ist toter State.
**Fix-Vorschlag:** `self._sort_col = None` aus `__init__` entfernen.
**Aufwand:** XS

---

## [LOW] Keine Stop/Kill-Funktion in der GUI — gestarteter Prozess ist unkillbar (engine.py, status.py)
**Dimension:** Logik-Fehler / Maintainability
**Impact:** `subprocess_runner.stop()` existiert im Backend (Zeile 60–68), wird aber von keinem Tab aufgerufen. Ein gestarteter Prozess läuft bis zum natürlichen Ende. Es gibt keinen "Abbrechen"-Button. Bei einem hängenden Prozess muss der Nutzer den Prozess manuell über den Taskmanager beenden. Beim Schließen der App laufen Daemon-Threads weiter bis der Python-Interpreter beendet wird.
**Fix-Vorschlag:** "Abbrechen"-Button hinzufügen, der `subprocess_runner.stop(self._proc)` aufruft. In `destroy()` (analog zu `status.py`) auch `_proc` terminieren.
**Aufwand:** S

---

## [INFO] `__init__.py` ist vollständig leer (0 Bytes) — kein explizites `__all__`
**Dimension:** Maintainability
**Impact:** Ein leeres `__init__.py` ist funktional korrekt, aber es gibt keine explizite Public API für das Paket. Externe Aufrufer importieren direkt von `app.tabs.dashboard`, `app.tabs.engine` etc. Wenn sich Klassennamen ändern, gibt es keine zentrale Stelle für Aliase.
**Fix-Vorschlag:** `__all__` mit den vier Tab-Klassen definieren oder zumindest die Klassen re-exportieren: `from .dashboard import DashboardTab` etc.
**Aufwand:** XS

---

## [INFO] Kein Testfile für die Tab-Klassen erkennbar — Unit-Tests nur für statische Hilfsmethoden
**Dimension:** Testabdeckung
**Impact:** Die statischen Methoden `filter_df`, `compute_max_listings`, `status_to_display`, `build_launchd_config` sind testbar ohne Tk-Root — das ist ein gutes Design. Aber es gibt keine Tests für: Lifecycle (`build()` → Widget-State), den `_save_settings`-Pfad, den `_install`-Pfad mit Mock-`launchd_manager`, Race-Condition-Szenarien im Thread-Handling, und die `destroy()`-Cleanup-Logik. Die Integration mit `subprocess_runner` ist ungetestet.
**Fix-Vorschlag:** Test-Suite erweitern mit `unittest.mock.patch` für `subprocess_runner`, `launchd_manager` und `status_monitor`. Tk-Tests mit `tkinter.Tk()` in einer headless-CI-Umgebung (xvfb) oder durch weiteres Auslagern von Logik in testbare Klassen.
**Aufwand:** L

---

## [INFO] Konsistenz: `status.py` hat kein `messagebox` im try-Block, andere Tabs schon (status.py:11–19)
**Dimension:** Konsistenz
**Impact:** `dashboard.py` (Zeile 13), `engine.py` (Zeile 14) und `zeitplan.py` (Zeile 14) importieren alle `messagebox` im try-Block. `status.py` fehlt dieser Import. Dies ist nicht nur ein Stil-Problem, sondern ein echter Bug (siehe HIGH-Finding oben), macht aber auch deutlich, dass es kein konsistentes Pattern für den headless-Guard gibt.
**Fix-Vorschlag:** Einheitliches Import-Template für alle Tabs definieren und als Kommentar-Block dokumentieren. Ggf. in ein gemeinsames `app/tabs/_tk_compat.py` auslagern.
**Aufwand:** XS

---

## Zusammenfassung nach Dateien

| Datei | CRITICAL | HIGH | MEDIUM | LOW | INFO |
|---|---|---|---|---|---|
| dashboard.py | 0 | 1 | 2 | 3 | 0 |
| engine.py | 0 | 2 | 1 | 2 | 0 |
| status.py | 0 | 2 | 1 | 1 | 1 |
| zeitplan.py | 1 | 1 | 2 | 0 | 0 |
| __init__.py | 0 | 0 | 0 | 0 | 1 |
| Quer/Backend | 0 | 1 | 1 | 0 | 1 |
| **Gesamt** | **1** | **7** | **7** | **6** | **3** |

> Hinweis: Die Gesamtzahl oben im Header (22) zählt alle Findings. Die Tabelle hier addiert auf 25, da drei Findings mehrere Dateien betreffen und in der Tabelle mehrfach eingeflossen sind. Die kanonische Zählung im Header ist maßgeblich.
