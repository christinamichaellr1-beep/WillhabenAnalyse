# Phase B — Regression-Check
**Geprüft:** 2026-04-18  
**Branch geprüft:** `claude/xenodochial-hofstadter-16be42` (gemergt nach main als `43869b4`)  
**Testlauf-Basis:** `logs/test_frisch_50_v2.log` (primär, 226 gescrapt / 50 geparst), `logs/testlauf_v21_350.log` (0 Anzeigen — CRITICAL)

---

## CRITICAL: Fehlender 350-Anzeigen-Testlauf

**Behauptung im Report:** `REPORT_v2.1_nachtlauf.md` (Phase G) beschreibt einen laufenden Testlauf mit `--max-listings=350`, der "bis zu 350 Anzeigen verarbeitet" sobald ein raw_cache vorhanden ist.

**Tatsächlicher Befund:**

`logs/testlauf_v21_350.log` enthält nur **26 Zeilen** und endet nach 38 Sekunden:

```
[2026-04-18 06:03:30]   (1) Anzeige 2053989000 vom 2026-03-04 ist älter als cutoff 2026-04-17 → stoppe.
[2026-04-18 06:03:30] Scraping abgeschlossen. 0 Anzeigen verarbeitet, 454 übersprungen.
Keine Anzeigen – Pipeline abgebrochen.
{"scraped": 0, "parsed_events": 0, "ovp_checked": 0, ...}
```

**Ursache:** Der Lauf verwendete `sort=5` (älteste zuerst) statt `sort=3` (neueste zuerst). Die erste Anzeige war vom 2026-03-04 — weit älter als der cutoff 2026-04-17. Damit wurden alle 454 Anzeigen beim Alters-Check übersprungen, **0 Anzeigen wurden gescrapt, 0 geparst**.

**Warum das ein Problem ist:**

1. Der Report bezeichnet diesen Lauf als erfolgreichen Beweis für Early-Stop-Funktionalität bei 350 Listings — das ist faktisch falsch. Es wurde kein einziges Listing verarbeitet.
2. Der Parsing-Pfad (Parser v2, StatusWriter, try/finally, max_listings-Truncation in `main.py`) wurde in diesem Lauf **nicht durchlaufen**. Es gibt keinen Live-Beweis, dass 350 Anzeigen fehlerfrei geparst werden.
3. Das `.willhaben_status.json` zeigt `"total": 1, "current": 1, "status": "done"` — dieser Snapshot stammt offensichtlich aus einem Mini-Testlauf, nicht aus einem 350-Anzeigen-Run.
4. Der eigentliche valide Testlauf (`test_frisch_50_v2.log`) hat mit `sort=3` gearbeitet und 50 Anzeigen geparst. Er ist primäre Evidenzquelle, deckt aber nur ~14% des behaupteten Umfangs ab.

---

## Regression-Check: 5 ursprüngliche Fehlerfälle

### FC1: JSON-Parse-Fehler in Ollama-Responses

**Status:** NICHT VERIFIZIERBAR (kein direkter Fehlerfall im Testlauf ausgelöst)

**Hintergrund:** Parser v2 nutzt Ollama Structured Output (JSON-Schema-erzwungenes Format über `format=`-Parameter). Das eliminiert rohe JSON-Parse-Fehler strukturell, weil das Modell schemakonformen Output liefern muss.

**Code-Evidenz (`parser/v2/pipeline.py`, Zeile 85–90):**
```python
try:
    events = parse_ad(ad, model=model, use_cache=False)
except Exception as exc:
    writer.error(str(exc))
    logger.warning("Fehler beim Parsen von %s: %s", ad_id, exc)
    events = []
```
Jede Exception beim Parsen einer einzelnen Anzeige wird gefangen, als Fehler im StatusWriter vermerkt, und die Pipeline läuft weiter.

**Log-Evidenz:** `logs/test_frisch_50_v2.log` — Zeile 2611: `'errors': []` im finalen Stats-Dict. Kein einziger Parse-Fehler in 50 verarbeiteten Anzeigen.

**Risiko:** Wenn Ollama einen Structured-Output-Fehler zurückgibt (Netzwerkfehler, Modell-Timeout, leere Response), greift der except-Block korrekt. Strukturelles Risiko besteht bei unbekannten Modell-Varianten die `format=`-Schema nicht unterstützen — nicht getestet für `gemma4:26b` oder `gemma4:latest`.

---

### FC2: StatusWriter fehlte bei Abbrüchen (kein fail()-Aufruf)

**Status:** BEHOBEN — durch Code-Review vor Commit `8a0e17b` korrigiert

**Code-Evidenz (`parser/v2/pipeline.py`, Zeilen 71–104):**
```python
writer = StatusWriter(total=total, model=model or extractor.PRIMARY_MODEL)
try:
    for i, ad in enumerate(ads, 1):
        ...
    writer.finish()
except Exception as exc:
    writer.fail(str(exc))
    raise
```
Der äußere `try/finally`-Block (korrekt als `try/except` mit `raise` implementiert — semantisch equivalent zu try/finally für den fail()-Aufruf) stellt sicher, dass bei jeder unkontrollierten Exception `writer.fail()` aufgerufen wird, bevor die Exception weiterpropagiert.

**Report-Evidenz:** `REPORT_v2.1_nachtlauf.md`, Qualitätssicherung: *"`try/finally` um `parse_ads()`-Schleife für `writer.fail()` bei Absturz"* — explizit als behobenes Issue aus Code-Review dokumentiert.

**Log-Evidenz:** Kein unkontrollierter Abbruch im 50er-Testlauf. `.willhaben_status.json` zeigt `"status": "done"` — kein `"error"`-Status aufgetreten.

**Risiko:** Hinweis: Der Code verwendet `try/except ... raise` statt `try/finally`. Das bedeutet: Bei einem normalen `return` innerhalb der Schleife (falls zukünftig eingebaut) würde `writer.fail()` nicht gerufen. Der aktuelle Code hat keinen solchen Pfad — das Risiko ist theoretisch.

---

### FC3: Concurrent Spawn (mehrfacher Prozessstart ohne Guard)

**Status:** BEHOBEN — in Commit `ec02dae` implementiert

**Code-Evidenz `app/tabs/engine.py`, Zeilen 132–134:**
```python
def _start_test(self) -> None:
    if self._proc is not None and subprocess_runner.is_running(self._proc):
        messagebox.showwarning("Läuft bereits", "Ein Test-Lauf ist bereits aktiv.")
        return
```

**Code-Evidenz `app/tabs/status.py`, Zeilen 149–151:**
```python
def _start_pipeline(self) -> None:
    if self._proc is not None and subprocess_runner.is_running(self._proc):
        messagebox.showwarning("Läuft bereits", "Die Pipeline ist bereits aktiv.")
        return
```

Beide Tabs prüfen vor dem Prozessstart ob `_proc` bereits läuft. Der Guard ist identisch aufgebaut.

**Risiko:** Schwache Stelle: Der Guard greift nur wenn `_proc` im selben Tab-Objekt gesetzt ist. Wenn ein Benutzer gleichzeitig über `EngineTab` und `StatusTab` startet, können zwei Subprozesse parallel laufen — tabs-übergreifende Koordination fehlt. `subprocess_runner.is_running()` prüft nur den lokalen Prozess-Handle.

---

### FC4: ValueError in GUI bei leerem Input

**Status:** BEHOBEN — in Commit `ec02dae` implementiert

**Code-Evidenz `app/tabs/engine.py`, Zeilen 162–167:**
```python
def _save_settings(self) -> None:
    self.config_data["model"] = self._model_var.get()
    raw = self._max_listings_var.get().strip()
    try:
        self.config_data["max_listings"] = None if raw == "Alle" else int(raw)
    except ValueError:
        messagebox.showerror("Fehler", "Ungültige Anzahl — bitte Zahl oder 'Alle' eingeben.")
        return
```

Leere oder nicht-numerische Eingaben im Max-Listings-Spinbox erzeugen keinen unkontrollierten `ValueError` mehr, sondern eine benutzerfreundliche Fehlermeldung. Die Hilfsmethode `compute_max_listings()` (Zeile 176–181) für Unit-Tests ist konsistent implementiert.

**Zusätzliche Evidenz:** `REPORT_v2.1_nachtlauf.md` nennt explizit *"`ValueError`-Schutz in `EngineTab._save_settings()`"* als behobenes Review-Issue.

**Risiko:** Der `_start_test`-Guard (Zeilen 136–139) hat ebenfalls einen ValueError-Schutz für das Test-Batch-Spinbox:
```python
try:
    n = int(self._test_batch_var.get())
except ValueError:
    messagebox.showerror("Fehler", "Ungültige Test-Batch-Anzahl.")
    return
```
Beide Input-Pfade sind gesichert.

---

### FC5: after_cancel bei Fenster-Destroy fehlte

**Status:** BEHOBEN — in Commit `ec02dae` implementiert

**Code-Evidenz `app/tabs/status.py`, Zeilen 166–170:**
```python
def destroy(self) -> None:
    if self._after_id is not None:
        self.after_cancel(self._after_id)
        self._after_id = None
    super().destroy()
```

`_after_id` wird in `__init__` mit `None` initialisiert (Zeile 38) und in `_refresh()` gesetzt wenn Auto-Refresh geplant wird (Zeile 138). Beim Zerstören des Widgets wird der ausstehende `after()`-Call korrekt gecancelt, bevor `super().destroy()` aufgerufen wird.

**Log-Evidenz:** Kein `TclError: invalid command name` im 50er-Testlauf-Log. (Der Testlauf lief als `--once` ohne GUI; der Fix ist GUI-spezifisch und daher nur durch manuelle Tests vollständig verifizierbar.)

**Risiko:** Nur `StatusTab` hat eine `destroy()`-Override. `EngineTab` nutzt keine `after()`-Calls (Log-Streaming läuft über `after(0, ...)` in `_append_log` — einmalig, kein wiederkehrender `after`-ID). Das ist korrekt — kein Regression-Risiko.

---

## Neue Fehlerkategorien aus dem 50er-Testlauf

### NF1: OVP-Checker — Massenhafte Navigation-Interruptions

**Schweregrad:** MEDIUM  
**Beobachtung:** Im OVP-Check-Abschnitt (`logs/test_frisch_50_v2.log`, Zeilen ~1800–2600) treten für alle Events massenhaft Playwright-Fehler auf:
```
Page.goto: Navigation to "https://www.oeticket.com/..." is interrupted by another navigation
```
Für fast jedes der 50 Events schlagen alle ~10 OVP-Quellen (oeticket, eventim, myticket, barracuda, wien-ticket, konzerthaus, stadthalle, szene-wien, gasometer, ticketmaster) fehl.

**Auswirkung:** Nur 31 von 50 Events haben `originalpreis_pro_karte` gefunden — die Trefferquote ist trotz der Fehler akzeptabel, aber die Log-Flut (>1900 WARNING-Zeilen allein für OVP) verdeckt echte Fehler. Die Navigation-Interruptions deuten auf asynchrone Race-Conditions im OVP-Checker hin.

**Kein Blocker:** Pipeline läuft durch (`'errors': []`), OVP-Fehler sind als nicht-kritisch behandelt.

### NF2: szene-wien.com — DNS-Auflösungsfehler

**Schweregrad:** LOW  
**Beobachtung:** `ERR_NAME_NOT_RESOLVED at https://www.szene-wien.com/` tritt konsistent bei jedem OVP-Check auf. Die Domain existiert nicht mehr oder ist nicht erreichbar.  
**Empfehlung:** `szene-wien.com` aus der OVP-Quellenliste entfernen.

### NF3: Datums-Cutoff-Diskrepanz zwischen sort=3 und sort=5

**Schweregrad:** HIGH (bezogen auf testlauf_v21_350.log)  
**Beobachtung:** `test_frisch_50_v2.log` verwendet `sort=3` (neueste zuerst, cutoff 2026-04-15), `testlauf_v21_350.log` verwendete `sort=5` (älteste zuerst, cutoff 2026-04-17). Mit sort=5 trifft die erste Anzeige bereits den Cutoff → 0 Ergebnisse.  
**Ursache unklar:** Ob `sort=5` in einem älteren Config-Snapshot eingetragen war oder der Testlauf mit anderem Config ausgeführt wurde, ist nicht nachvollziehbar. Die aktuelle `willhaben_scraper.py` verwendet korrekt `sort=3` in `TARGET_URL`.

---

## Zusammenfassung

| Fehlerfall | Fix-Commit | Code-Evidenz | Log-Evidenz | Status |
|---|---|---|---|---|
| FC1: JSON-Parse-Fehler Ollama | strukturell (v2 format=) | `pipeline.py:87-90` | `errors: []` in final stats | NICHT VERIFIZIERBAR (kein Fehler ausgelöst) |
| FC2: StatusWriter fail() bei Abbruch | `8a0e17b` | `pipeline.py:71-104` | status="done" in JSON | BEHOBEN |
| FC3: Concurrent-Spawn-Guard | `ec02dae` | `engine.py:132-134`, `status.py:149-151` | kein Doppelstart | BEHOBEN |
| FC4: ValueError bei leerem Input | `ec02dae` | `engine.py:162-167` | — (GUI-Test) | BEHOBEN |
| FC5: after_cancel bei destroy | `ec02dae` | `status.py:166-170` | kein TclError | BEHOBEN |
| **CRITICAL: 350er-Testlauf** | — | 26-zeiliges Log | 0 Anzeigen, 0 Parses | FEHLENDER NACHWEIS |

**Gesamtbewertung:** 4 von 5 Fehlerfällen sind durch Code-Review und Commits nachweislich behoben. FC1 (JSON-Parse) ist strukturell adressiert aber im Testlauf nicht ausgelöst worden. Der kritische Mangel ist der fehlende echte 350-Anzeigen-Parsingleauf — der einzige valide Testlauf (`test_frisch_50_v2.log`) zeigt eine fehlerfreie Pipeline mit 50 Anzeigen, ist aber nicht repräsentativ für Langläufe unter Last.

**Empfohlene Folgeaktion:** Testlauf mit `--max-listings=100 --parser-version=v2 --once` auf main mit vorhandenem raw_cache durchführen, um den Parsing-Pfad unter realistischen Bedingungen zu verifizieren.
