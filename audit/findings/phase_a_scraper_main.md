# Phase A — scraper/ + main.py Audit
**Geprüft:** 2026-04-18
**Dateien:** scraper/willhaben_scraper.py, main.py, scraper/willhaben_tracker_original.py
**Findings gesamt:** 19 (CRITICAL: 1, HIGH: 4, MEDIUM: 6, LOW: 4, INFO: 4)

---

## [CRITICAL] `scrape` Coroutine wird in Test-Monkeypatch nie awaited (main.py:83)
**Dimension:** 1 — Logik-Fehler / async/await
**Impact:**
In `tests/test_main_cli.py` Zeile 83 wird `asyncio.run` durch ein Lambda ersetzt:
```python
monkeypatch.setattr("main.asyncio.run", lambda coro: _fake_scrape())
```
Das Lambda ruft `_fake_scrape()` auf — ignoriert aber `coro` vollständig. Das übergebene Coroutine-Objekt `scrape(max_listings=max_listings)` wird dadurch **nie awaited** und nie geschlossen. Python gibt dann genau die gemeldete `RuntimeWarning: coroutine 'scrape' was never awaited` aus.

In Produktion ist `asyncio.run(scrape(...))` korrekt (main.py:93), der Fehler liegt ausschliesslich im Test-Monkeypatch. ABER: Die RuntimeWarning zeigt an, dass die Coroutine real erzeugt, dann das Event-Loop aber mit dem Fake-Return ersetzt wird — d. h. der **Test beweist nicht, was er beweisen soll**: Er mockt `asyncio.run` falsch und schützt damit nicht vor einem defekten Scraping-Aufruf. Gleichzeitig hinterlässt er offene Coroutinen im GC, was in Python 3.12+ zu `ResourceWarning` eskaliert und Testsessions zum Absturz bringen kann.
**Fix-Vorschlag:**
Entweder `asyncio.run` durch einen korrekt schliessenden Wrapper ersetzen:
```python
import asyncio as _asyncio
def _fake_run(coro):
    coro.close()  # Coroutine sauber schliessen
    return _fake_scrape()
monkeypatch.setattr("main.asyncio.run", _fake_run)
```
Oder besser: `scraper.willhaben_scraper.scrape` direkt patchen statt `asyncio.run` zu überschreiben — das ist robuster und schützt vor Seiteneffekten auf andere asyncio-Calls im selben Testlauf (z. B. OVP-Check).
**Aufwand:** S

---

## [HIGH] `page.set_default_timeout` ohne `await` — fire-and-forget-Aufruf (willhaben_scraper.py:368, willhaben_tracker_original.py:134)
**Dimension:** 1 — Logik-Fehler / async/await
**Impact:**
```python
page.set_default_timeout(90000)   # kein await
```
`set_default_timeout()` ist in der Playwright Python-API eine **synchrone** Methode und sollte tatsächlich ohne `await` aufgerufen werden — das ist korrekt. Allerdings: In einem `async`-Kontext ohne `await` gibt Playwright-Python für manche Methoden trotzdem Coroutinen zurück, wenn die Version wechselt. Aktuell: kein unmittelbarer Bug, aber ein Konsistenz-Risiko. Das eigentliche HIGH hier ist, dass der Timeout nur für das **page**-Objekt gilt — **nicht** für den Browser-Context. Neue Pages aus demselben Context erben **keinen** Timeout. Für den aktuellen einzigen-Page-Ansatz kein Problem, aber bei zukünftigen Refactorings ein stiller Fehler.
**Fix-Vorschlag:** `context.set_default_timeout(90000)` statt nur `page.set_default_timeout(90000)`, damit alle zukünftigen Pages den Timeout erben.
**Aufwand:** XS

---

## [HIGH] Cutoff-Logik überspringt Anzeige, zählt sie aber als Fehler-Fallback (willhaben_scraper.py:430–463)
**Dimension:** 1 — Logik-Fehler
**Impact:**
Im Detailseiten-Loop gilt: Wenn eine Anzeige zu alt ist (`ad_date < cutoff_date`), wird `ok = True` gesetzt und `break` ausgeführt — die Anzeige wird **nicht** in `results` aufgenommen (korrekt). Nach dem inneren Retry-Loop wird `if not ok` geprüft — da `ok = True`, kein Fehler-Fallback (korrekt).

**ABER:** Die Anzeige wird auch **nicht** in `stop_scraping`-Logik einbezogen. Da Anzeigen nach `sort=3` (neueste zuerst) sortiert sind, bedeutet das erste Überschreiten des Cutoffs, dass **alle folgenden Anzeigen ebenfalls zu alt sind** — trotzdem werden alle restlichen URLs weiterhin besucht (HTTP-Request + DOM-Parse). Das ist ein unnötiger Performance-Verlust von bis zu mehreren hundert Requests pro Lauf.

Zudem: `skipped`-Berechnung am Ende (Zeile 473) ist falsch:
```python
skipped = len(all_ad_urls) - len(results)
```
„Zu alte" Anzeigen zählen weder als Ergebnis noch als übersprungen — die Variable ist damit irreführend und unterschätzt den tatsächlichen Umfang des Runs systematisch.
**Fix-Vorschlag:** Nach dem ersten Cutoff-Treffer `stop_scraping = True` setzen — bei sort=3 sind alle folgenden Anzeigen garantiert älter. Alternativ einen separaten `skipped_age`-Counter führen.
**Aufwand:** S

---

## [HIGH] `asyncio.run` doppelt im selben Thread in Daemon-Modus (main.py:93, main.py:129)
**Dimension:** 1 — Logik-Fehler / async/await
**Impact:**
`run_pipeline()` ruft `asyncio.run(scrape(...))` auf (Zeile 93) und danach `asyncio.run(check_events(...))` (Zeile 129). Beide Aufrufe erzeugen jeweils ein neues Event-Loop, was in Python 3.10+ mit `asyncio.run` im selben Thread grundsätzlich erlaubt ist (altes Loop wird geschlossen). Das Problem: Wenn `run_pipeline()` aus einem bereits laufenden Async-Context aufgerufen wird (z. B. beim GUI-Backend, das asyncio verwendet), schlägt `asyncio.run` mit `RuntimeError: This event loop is already running` fehl.

In der aktuellen Daemon-Loop (`while True: schedule.run_pending()`) ist es kein Problem — aber die GUI ruft `run_pipeline` über `subprocess_runner` auf, was die Einschränkung umgeht. Dennoch ist der Doppel-`asyncio.run`-Ansatz in `run_pipeline` strukturell fragil.
**Fix-Vorschlag:** `run_pipeline` als `async def run_pipeline_async()` anlegen und intern `await scrape(...)` sowie `await check_events(...)` aufrufen. Der synchrone `run_pipeline()` bleibt als dünner Wrapper mit `asyncio.run(run_pipeline_async())`.
**Aufwand:** M

---

## [HIGH] Hardcodierte E-Mail-Adresse als Default-Wert im Production-Code (willhaben_tracker_original.py:15, old_tracker.py:15)
**Dimension:** 3 — Security
**Impact:**
```python
ACCOUNT = os.getenv("GOG_ACCOUNT", "christina.michael.l.r.1@gmail.com")
```
Eine echte E-Mail-Adresse ist als Fallback-Default direkt im Quellcode committed. Dies ist ein Security- und Privacy-Finding: Die Adresse liegt dauerhaft in der Git-History, wird bei jedem `git log`/`git blame` sichtbar und bei einem Public-Repo-Leak exponiert.
**Fix-Vorschlag:** Default auf `""` oder `None` setzen; im Code prüfen ob ACCOUNT gesetzt ist, bevor Upload versucht wird. Wenn es eine Test-Adresse ist: trotzdem aus dem Code entfernen, da sie in der Git-History bleibt.
**Aufwand:** XS

---

## [MEDIUM] `_is_first_run()` ist race-condition-anfällig und semantisch inkonsistent (willhaben_scraper.py:62–64)
**Dimension:** 1 — Logik-Fehler / Edge-Cases
**Impact:**
```python
def _is_first_run() -> bool:
    return not any(RAW_CACHE.glob("*.json"))
```
"Erster Lauf" wird als "leeres Cache-Verzeichnis" definiert. Das ist falsch in zwei Szenarien:
1. Wenn der Cache manuell geleert oder gelöscht wird, behandelt der Scraper den nächsten Lauf fälschlicherweise als ersten Lauf und lädt deutlich mehr Seiten.
2. Wenn zwei Prozesse gleichzeitig starten (Daemon + manueller CLI-Run), können beide `_is_first_run() == True` sehen und dann beide `first_run_max_age_days` verwenden — doppelter Scraping-Aufwand.
**Fix-Vorschlag:** Eine dedizierte Sentinel-Datei (z. B. `data/.initialized`) anlegen, die beim ersten erfolgreichen Abschluss geschrieben wird. Nur deren Abwesenheit = erster Lauf.
**Aufwand:** S

---

## [MEDIUM] `pages_to_load`-Berechnung kann zu `0` werden (willhaben_scraper.py:372)
**Dimension:** 1 — Logik-Fehler / Edge-Cases
**Impact:**
```python
pages_to_load = min(max_pages, (max_listings // 90) + 2) if max_listings else max_pages
```
Wenn `max_listings=1` wird `(1 // 90) + 2 = 2`, korrekt. Wenn `max_listings=0`, wird `(0 // 90) + 2 = 2`, auch noch korrekt. Aber der `if max_listings`-Branch ist trügerisch: `if max_listings` ist `False` wenn `max_listings=0`, also wird `max_pages` verwendet — das ist kontraintuitiv. Wichtiger: `max_listings=0` als Eingabe erzeugt keine Warnung und scrapet trotzdem alle Seiten.

Zusätzlich: `min(max_pages, ...)` kann nie `0` werden wenn `max_pages >= 1`, aber wenn jemand `max_pages=0` übergibt, ergibt `range(1, 1)` = leer — kein Fehler, kein Log, keine Anzeigen, `results = []`. Stille Fehler.
**Fix-Vorschlag:** Am Funktionsanfang validieren: `if max_listings is not None and max_listings <= 0: raise ValueError(...)`. Separate Behandlung von `max_listings=0` vs. `None`.
**Aufwand:** XS

---

## [MEDIUM] Regex-Fallback für Preis matcht ungewollte Strings (willhaben_scraper.py:211)
**Dimension:** 1 — Logik-Fehler
**Impact:**
```python
m = re.search(r"(\d[\d\.,]* ?€|\€ ?\d[\d\.,]*)", text_komplett)
```
Dieser Regex ist zu locker: Er matched "Versand: 3,90 €", "MwSt. 20 €" oder "1.000.000 €" aus beliebigem Seitentext, wenn kein DOM-Selektor erfolgreich war. Preise aus Navigationselementen, Footer oder Werbebannern können fälschlicherweise als Anzeigenpreis übernommen werden. Der `text_komplett` ist der gesamte `document.body.innerText` — unkontrolliert.
**Fix-Vorschlag:** Regex nur auf strukturierte Bereiche (z. B. erste 2000 Zeichen des Texts) anwenden, oder mit einem engeren Kontextmuster: `r"Preis[:\s]+(\d[\d\.,]* ?€)"`.
**Aufwand:** S

---

## [MEDIUM] `skipped`-Statistik am Ende des Scrapers ist strukturell falsch (willhaben_scraper.py:473)
**Dimension:** 5 — Konsistenz
**Impact:**
```python
skipped = len(all_ad_urls) - len(results)
```
Diese Berechnung zählt "übersprungen" als Differenz zwischen allen URLs und allen Ergebnissen. Sie vermischt aber drei verschiedene Kategorien:
- Anzeigen, die zu alt waren (bewusst übersprungen)
- Cache-Hits (kommen in `results` rein, reduzieren `skipped` fälschlicherweise)
- Anzeigen, die wegen Fehler nicht geladen werden konnten (kommen auch in `results` mit Fehler-Dict rein)

Dadurch ist die Log-Ausgabe ("X Anzeigen verarbeitet, Y übersprungen") irreführend und nicht verlässlich für Monitoring.
**Fix-Vorschlag:** Separate Counter `cache_hits`, `age_skipped`, `errors` führen und am Ende klar loggen.
**Aufwand:** S

---

## [MEDIUM] Import von `Callable` aus `typing` unnötig (Python 3.10+) (main.py:12)
**Dimension:** 2 — Dead Code
**Impact:**
```python
from typing import Callable
```
Ab Python 3.10 kann `collections.abc.Callable` direkt verwendet werden; `typing.Callable` ist deprecated (PEP 585). Das Projekt verwendet Python 3.14 (laut `.venv`-Pfad). Kein funktionaler Bug, aber ein Hinweis auf veralteten Code-Stil.
**Fix-Vorschlag:** `from collections.abc import Callable` oder `Callable` aus der Type-Annotation entfernen und `... | None` direkt nutzen.
**Aufwand:** XS

---

## [LOW] `willhaben_tracker_original.py` und `old_tracker.py` sind identische Dateien — Dead Code (beide Dateien)
**Dimension:** 2 — Dead Code / Rollback-Artefakte
**Impact:**
`scraper/willhaben_tracker_original.py` und `/old_tracker.py` sind **byte-identisch** (253 Zeilen, gleicher Inhalt). Beide enthalten den alten Scraper ohne Caching, ohne Alters-Filter und mit hartkodiertem Google-Drive-Upload via `gog` CLI. Diese Logik ist vollständig durch `willhaben_scraper.py` ersetzt. Die Dateien werden nirgendwo importiert (`__init__.py` im scraper-Package ist leer) und dienen nur als Rollback-Referenz. Sie sollten archiviert, nicht im aktiven Repo gehalten werden — sie erhöhen die kognitive Komplexität und führen neue Entwickler irre.
**Fix-Vorschlag:** Dateien in ein `archive/` Verzeichnis verschieben oder per Git-Tag markieren und aus dem Haupt-Branch entfernen. Eine `ROLLBACK.md`-Notiz mit dem Commit-SHA reicht als Referenz.
**Aufwand:** XS

---

## [LOW] `_log`-Funktion im Scraper und `logger` in main.py — zwei parallele Logging-Systeme ohne Brücke (willhaben_scraper.py:42–44, main.py:20–28)
**Dimension:** 5 — Konsistenz
**Impact:**
`willhaben_scraper.py` verwendet `print()` mit Zeitstempel (`_log`-Funktion). `main.py` verwendet `logging.Logger` mit FileHandler. Beim `run_pipeline()`-Aufruf werden Scraper-Logs auf stdout ausgegeben, aber **nicht** in `logs/pipeline.log` geschrieben. Debugging eines nächtlichen Daemon-Runs erfordert damit stdout-Capture (z. B. launchd-Log) und die Pipeline-Log-Datei gleichzeitig.
**Fix-Vorschlag:** `willhaben_scraper.py` soll einen optionalen `log_callback`-Parameter entgegennehmen (wie `run_pipeline` es bereits selbst macht) und diesen statt `print()` aufrufen. Oder: Scraper auf `logging.getLogger` umstellen.
**Aufwand:** S

---

## [LOW] Cookie-Banner-Selektor-Liste in Scraper und Original unterschiedlich — Divergenz (willhaben_scraper.py:116–120, willhaben_tracker_original.py:57–61)
**Dimension:** 2 — Dead Code / Konsistenz
**Impact:**
`willhaben_tracker_original.py` hat `"button#didomi-notice-agree-button span"` als zweiten Selektor; `willhaben_scraper.py` fehlt dieser. Es ist unklar ob das eine bewusste Entscheidung oder ein versehentliches Weglassen ist. Da `_dismiss_cookies` den ersten Treffer verwendet und der Parent-Button (`button#didomi-notice-agree-button`) zuerst kommt, ist kein funktionaler Bug — aber es ist ein Hinweis auf inkonsistente Wartung.
**Fix-Vorschlag:** Selektoren-Liste in eine Konstante `COOKIE_SELECTORS` auslagern und zentral pflegen.
**Aufwand:** XS

---

## [LOW] `--ovp`-Branch in `main.py` importiert `gemma_parser` direkt — ignoriert `--parser-version` (main.py:303)
**Dimension:** 5 — Konsistenz
**Impact:**
```python
from parser.gemma_parser import parse_ads   # hardcodiert v1
```
Der `--ovp`-Branch verwendet immer den v1-Parser, auch wenn `--parser-version v2` angegeben wird. Das Argument `args.parser_version` wird in diesem Branch nicht ausgewertet. Für isolierte OVP-Tests ein stilles, inkonsistentes Verhalten.
**Fix-Vorschlag:** `parse_ads = _select_parse_ads(args.parser_version)` auch im `--ovp`-Branch verwenden.
**Aufwand:** XS

---

## [INFO] Kein Test für `scrape()`-Funktion selbst — nur Integration via Monkeypatch (tests/)
**Dimension:** 6 — Testabdeckung
**Impact:**
Es gibt keine Unit-Tests für `willhaben_scraper.py`. Die Funktionen `_parse_willhaben_date`, `_normalize_url`, `_extract_id_from_url`, `_is_first_run`, `_collect_listing_urls` und `_parse_detail_page` haben null Testabdeckung. Insbesondere `_parse_willhaben_date` mit seinen 4 Parsing-Pfaden (JSON-LD, "Heute", "Gestern", "vor X Tagen", DD.MM.YYYY) ist fehleranfällig und ungetestet.
**Fix-Vorschlag:** Mindestens `_parse_willhaben_date` und `_normalize_url` mit parametrisierten Unit-Tests abdecken — keine Playwright-Instanz erforderlich, da reine Python-Funktionen.
**Aufwand:** M

---

## [INFO] `max_listings`-Truncation in `main.py` ist nach `scrape()` redundant (main.py:105–107)
**Dimension:** 4 — Performance / Logik
**Impact:**
```python
if max_listings is not None:
    ads = ads[:max_listings]
```
`scrape()` implementiert `max_listings` bereits intern (Zeile 443–446 in scraper). Das zweite Truncating in `main.py` ist daher immer ein No-Op — `len(ads) <= max_listings` ist nach dem Scraper garantiert. Kein Bug, aber toter Code der Verwirrung stiftet: Leser könnten annehmen, `scrape()` implementiert das Limit nicht.
**Fix-Vorschlag:** Entweder das Truncating in `main.py` entfernen (mit einem Kommentar, dass `scrape()` das bereits macht), oder `scrape()` auf das Limit verlassen und den Check in main entfernen.
**Aufwand:** XS

---

## [INFO] Keine Timeout-Begrenzung für den Gesamtlauf — Daemon kann bei hängendem Browser ewig blockieren (willhaben_scraper.py:360–471)
**Dimension:** 3 — Security / Performance
**Impact:**
`page.set_default_timeout(90000)` begrenzt individuelle Playwright-Aktionen. Aber `async with async_playwright()` selbst hat keinen Gesamttimeout. Wenn der Browser-Prozess sich aufhängt (OOM, Chromium-Bug) und alle Playwright-Calls intern fehlschlagen, kann `scrape()` theoretisch unbegrenzt laufen. In einem `schedule`-Daemon-Modus bedeutet das: nachfolgende Runs stauen sich auf.
**Fix-Vorschlag:** `asyncio.wait_for(scrape(...), timeout=600)` in `run_pipeline()` wrappen oder einen `SCRAPER_MAX_SECONDS`-Parameter einführen.
**Aufwand:** S

---

## [INFO] `TARGET_URL` enthält `sort=3` — undokumentierte Abhängigkeit (willhaben_scraper.py:25–29)
**Dimension:** 7 — Maintainability
**Impact:**
Die Cutoff-Logik (frühzeitiger Stop bei zu alten Anzeigen — Finding #3) ist konzeptuell nur korrekt, wenn die Anzeigen nach Datum absteigend sortiert sind. Das wird durch `sort=3` in der URL garantiert — aber **nirgendwo im Code dokumentiert**. Wenn jemand `TARGET_URL` anpasst oder `sort=` entfernt, bricht die Cutoff-Stop-Logik still.
**Fix-Vorschlag:** Kommentar direkt neben `TARGET_URL`: `# sort=3 = neueste zuerst — Cutoff-Early-Stop hängt davon ab!`
**Aufwand:** XS

---

## [INFO] `gemma3:27b` im `--model`-Argument-Choices aber kein `gemma3:4b` oder `gemma3:12b` — unvollständige Choices-Liste (main.py:222–225)
**Dimension:** 7 — Maintainability
**Impact:**
```python
choices=["gemma3:27b", "gemma4:26b", "gemma4:latest"],
```
Die Choices-Liste ist willkürlich und muss bei jedem neuen Modell manuell erweitert werden. Wenn ein Nutzer `gemma3:12b` (lokal verfügbar) verwenden möchte, schlägt argparse fehl — obwohl Ollama jedes valide Modell akzeptieren würde. Dies ist ein Maintainability-Problem: Die Validierung ist restriktiver als notwendig.
**Fix-Vorschlag:** `choices` entfernen und stattdessen zur Laufzeit via `ollama list` validieren, oder Choices als Konstante `SUPPORTED_MODELS` extern definieren.
**Aufwand:** XS

---

# Zusammenfassung nach Datei

| Datei | CRITICAL | HIGH | MEDIUM | LOW | INFO |
|---|---|---|---|---|---|
| `tests/test_main_cli.py` | 1 | — | — | — | — |
| `scraper/willhaben_scraper.py` | — | 2 | 4 | 2 | 2 |
| `main.py` | — | 2 | 1 | 2 | 2 |
| `scraper/willhaben_tracker_original.py` + `old_tracker.py` | — | 1 | — | 1 | — |

# Priorisierte Fix-Reihenfolge

1. **CRITICAL** — Test-Monkeypatch Coroutine-Leak (test_main_cli.py:83) — sofort
2. **HIGH** — Cutoff-Early-Stop fehlt bei zu alten Anzeigen (scraper.py:430) — unnötige Requests
3. **HIGH** — Doppel-`asyncio.run` in `run_pipeline` — Strukturproblem für zukünftige async-Integration
4. **HIGH** — Hardcodierte E-Mail-Adresse in committed Code (tracker_original.py:15, old_tracker.py:15)
5. **MEDIUM** — `_is_first_run()` Sentinel-Logik ersetzen
6. **MEDIUM** — `skipped`-Statistik korrekt führen
7. **LOW** — Dead-Code-Dateien archivieren (tracker_original + old_tracker)
