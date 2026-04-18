# Phase B — Integration-Audit Report: WillhabenAnalyse v2.1
**Datum:** 2026-04-18  
**Testlauf-Basis:** logs/test_frisch_50_v2.log (50 Events, heute 09:46)  
**Produktions-Excel:** data/willhaben_markt.xlsx (483 Einträge)  
**Geprüfte Branches:** `claude/xenodochial-hofstadter-16be42` (gemergt → main `43869b4`)

---

## Executive Summary

Phase B hat vier Bereiche untersucht: Regression-Check (5 ursprüngliche Fehlerfälle), Anomalie-Detektion (483 Excel-Einträge + 50 parse_cache_v2-Dateien), Dashboard-Verifikation (Aggregator-Korrektheit) und Deployment-Integrität (launchd, Python, Ollama, Dependencies). Der Gesamtzustand ist **bedingt produktionsreif**: Die Pipeline-Kernlogik (Scraping, Parsing, Early-Stop, StatusWriter) funktioniert nachweislich korrekt für 50 Anzeigen, und 4 der 5 ursprünglichen Fehlerfälle sind durch Code-Review und Commits behoben. Jedoch blockieren zwei CRITICAL Dashboard-Bugs jeden produktiven Nutzen: `dashboard_aggregator.load_excel()` liest Sheet `"Angebote"` statt `"Hauptübersicht"` — das Dashboard ist damit seit Tag 1 dauerhaft leer, ohne Fehlermeldung. Zusätzlich fehlen 8 von 8 erwarteten Spaltenbezeichnungen im Aggregator, sodass selbst nach Behebung des Sheet-Namens keine Daten fließen würden. Ein dritter CRITICAL-Befund ist das Fehlen eines echten 350-Anzeigen-Testlaufs: der einzige kandidate Log (`testlauf_v21_350.log`) enthält 26 Zeilen mit 0 gescrapten Anzeigen (sort=5-Fehler), sodass kein Live-Nachweis für fehlerfreies Parsing unter Last existiert. Viertens enthält die Produktions-Excel mindestens einen Eintrag mit `Angebotspreis = 0 €` — ein klarer Normalisierungsfehler. Für Phase C (Dokumentations-Audit) besteht kein Blocker; die Code-Bugs müssen jedoch vor Produktions-Einsatz behoben werden.

---

## Findings-Übersicht

| Severity | Regression | Anomalien | Dashboard | Deployment | GESAMT |
|----------|-----------|-----------|-----------|------------|--------|
| CRITICAL | 1 | 1 | 2 | 0 | **4** |
| HIGH | 1 | 3 | 1 | 2 | **7** |
| MEDIUM | 2 | 2 | 3 | 3 | **10** |
| LOW | 2 | 0 | 3 | 3 | **8** |
| INFO | 0 | 1 | 0 | 3 | **4** |
| **GESAMT** | **6** | **7** | **9** | **11** | **33** |

*Dedupliziert: `szene-wien.com`-DNS-Fehler (Regression NF2 + Deployment F-B04) als ein Finding gezählt. `unbekannt`-Verkäufertyp (Anomalien + Dashboard F-3) als ein Finding. Unnamed-Spalten (Anomalien HIGH + Dashboard F-8 LOW) als ein Finding mit zwei Aspekten.*

---

## CRITICAL Findings

### C1: Fehlender echter 350-Anzeigen-Testlauf [Regression]

**Datei:** `logs/testlauf_v21_350.log` (26 Zeilen, 38 Sekunden Laufzeit)

**Was fehlt:** Der Report `REPORT_v2.1_nachtlauf.md` (Phase G) beschreibt einen Testlauf mit `--max-listings=350` als Beweis für Early-Stop-Funktionalität und Parser-v2-Stabilität. Das Log enthält jedoch ausschliesslich diesen Abbruch-Eintrag:

```
[2026-04-18 06:03:30] Scraping abgeschlossen. 0 Anzeigen verarbeitet, 454 übersprungen.
Keine Anzeigen – Pipeline abgebrochen.
{"scraped": 0, "parsed_events": 0, "ovp_checked": 0, ...}
```

**Ursache:** Der Lauf verwendete `sort=5` (älteste zuerst) statt `sort=3` (neueste zuerst). Die erste Anzeige war vom 2026-03-04 — weit älter als cutoff 2026-04-17 — sodass alle 454 Anzeigen beim Alters-Check übersprungen wurden.

**Warum Blocker:** Der Parsing-Pfad (Parser v2, StatusWriter, try/finally, max_listings-Truncation in `main.py`) wurde im gesamten `testlauf_v21_350.log` **nicht ein einziges Mal** durchlaufen. Es gibt keinen Live-Nachweis, dass 350 Anzeigen fehlerfrei geparst werden. Das `.willhaben_status.json` mit `"total": 1, "current": 1, "status": "done"` stammt aus einem Mini-Testlauf, nicht aus dem behaupteten 350-Anzeigen-Run.

**Behebung:** Testlauf mit `--max-listings=100 --parser-version=v2 --once` auf main mit vorhandenem raw_cache durchführen (`data/raw_cache/` enthält 228 Einträge, Stand 2026-04-18 08:33). Dies würde ~14 Minuten Laufzeit bei 82 Sekunden pro Anzeige erfordern.

---

### C2: Dashboard-Aggregator liest falschen Sheet-Namen [Dashboard]

**Datei:** `app/backend/dashboard_aggregator.py`, Methode `load_excel()`

**Bug:** `load_excel()` liest Sheet `"Angebote"`. Dieses Sheet existiert nicht in `data/willhaben_markt.xlsx`. Die tatsächlichen Daten liegen in Sheet `"Hauptübersicht"` (483 Zeilen). Der `except`-Block fängt den `KeyError` still ab und gibt `pd.DataFrame()` zurück.

**Auswirkung:** Das Dashboard-Aggregat ist seit dem ersten Betriebstag dauerhaft leer. Alle Aggregationsberechnungen (Min/Max/Avg/Count, OVP-Median, Gruppen-Keys) laufen auf einem leeren DataFrame. Kein Fehler wird dem Benutzer angezeigt. Die Aggregationslogik selbst rechnet nachweislich korrekt (10/10 Spot-Checks bestanden) — sie bekommt aber nie Daten.

**Behebung:** In `dashboard_aggregator.py` Sheet-Name von `"Angebote"` auf `"Hauptübersicht"` ändern. Alternativ: Sheet in der Excel-Datei umbenennen. Aufwand: XS.

---

### C3: Spalten-Namen-Mismatch Aggregator vs. Excel [Dashboard]

**Datei:** `app/backend/dashboard_aggregator.py`, interne Spalten-Konstanten

**Bug:** Der Aggregator verwendet interne Spalten-Bezeichner (z.B. `_PREIS_COL`, `_ANBIETER_TYP_COL`, `_EVENT_NAME_COL` etc.) die nicht mit den tatsächlichen Spalten-Namen in `data/willhaben_markt.xlsx` übereinstimmen. Die Excel enthält Spalten wie `"Angebotspreis pro Karte"`, `"Verkäufertyp"`, `"Event-Name"`, während der Aggregator andere Bezeichner erwartet.

**Auswirkung:** Selbst nach Behebung von C2 (korrekter Sheet-Name) würde der Aggregator keine Spalten finden und weiterhin leere Aggregate produzieren. Dies erklärt auch, warum F-2 (34 inkonsistente Marge-Zeilen) und F-3 (`unbekannt`-Verkäufertyp-Ausfall) im Dashboard nie auffielen — sie konnten nie auftreten, weil nie Daten geladen wurden.

**Behebung:** Alle 8 relevanten Spalten-Konstanten im Aggregator auf die exakten Excel-Header angleichen. Aufwand: S (mechanisch, aber risikobehaftet durch Seiteneffekte).

---

### C4: Angebotspreis = 0 € in Produktionsdaten [Anomalien]

**Datei:** `data/willhaben_markt.xlsx`, Sheet `"Hauptübersicht"`; wahrscheinliche Quelle: `parser/postprocessing.py`

**Bug:** `min(Angebotspreis pro Karte) = 0.0` — mindestens ein Eintrag hat Preis 0 €. Ein Nullpreis ist kein Gratisticket, sondern ein Normalisierungsfehler: wahrscheinlich Division durch `anzahl_karten = 0` in `postprocessing.py`.

**Auswirkung:** Verfälscht Durchschnittswerte, Marge-Berechnung und OVP-Vergleich für alle aggregierten Gruppen die diesen Eintrag enthalten. Ein Angebotspreis von 0 € könnte auch als "Händler verkauft gratis" fehlinterpretiert werden.

**Behebung:** Validierung in `postprocessing.py` ergänzen: Wenn berechneter Preis ≤ 0 → Wert auf `None` setzen statt 0 zu speichern. Aufwand: XS.

---

## HIGH Findings

### H1: Datums-Cutoff-Diskrepanz zwischen sort=3 und sort=5 [Regression]

**Datei:** `logs/testlauf_v21_350.log`; Konfigurations-Quelle unklar  
**Schweregrad:** HIGH (bezogen auf den fehlerhaften 350er-Testlauf)

Der Lauf `testlauf_v21_350.log` verwendete `sort=5` (älteste zuerst, cutoff 2026-04-17). Mit dieser Sortierung trifft die erste Anzeige (2026-03-04) sofort den Cutoff → alle 454 Anzeigen übersprungen. Die aktuelle `willhaben_scraper.py` verwendet korrekt `sort=3` in `TARGET_URL`. Es ist nicht nachvollziehbar ob `sort=5` in einem alten Config-Snapshot eingetragen war oder der Testlauf mit einem anderem Parameter ausgeführt wurde. Kein Log des `--sort`-Werts beim Ausführungszeitpunkt vorhanden. **Behebung:** Config-Audit vor jedem Testlauf; sort-Parameter im Log-Header ausgeben. Aufwand: XS.

---

### H2: Marge-Berechnung in 34 Zeilen (13.3%) inkonsistent [Dashboard]

**Datei:** `data/willhaben_markt.xlsx`, Sheet `"Hauptübersicht"`, ca. 34 Zeilen  
**Betroffene Events:** Foo Fighters, Böhse Onkelz, Tokio Hotel, Linkin Park, Die Toten Hosen, Herbert Grönemeyer, Nick Cave

34 von 255 Zeilen mit Marge-Werten zeigen Marge€/Marge%-Werte die nicht mit dem gespeicherten `Originalpreis pro Karte` übereinstimmen. Der implizierte OVP-Wert zur Marge-Berechnung ist in 19 dieser Fälle nicht in der Datei nachweisbar. Dies deutet darauf hin, dass die Marge mit einem OVP-Lookup-Ergebnis berechnet wurde, der sich später geändert hat, oder dass der gespeicherte OVP überschrieben wurde. Die `aggregate()`-Funktion berechnet ihre eigene Marge% neu auf Basis des gespeicherten `Originalpreis pro Karte` — diese Werte weichen damit von den in Excel gespeicherten Margen ab. Behebung: Marge nicht in Excel speichern, sondern immer im Aggregator berechnen. Aufwand: M.

---

### H3: v2-Metadaten-Spalten als "Unnamed: 24–27" — fehlende Header [Anomalien / Dashboard]

**Datei:** `data/willhaben_markt.xlsx`, Spalten 24–27; wahrscheinliche Quelle: `excel_writer.py` (write_only-Append-Modus)

Die 4 v2-spezifischen Spalten (Confidence-Grund, Modell, Pipeline-Version, Parse-Dauer ms) erscheinen in pandas als `Unnamed: 24`, `Unnamed: 25`, `Unnamed: 26`, `Unnamed: 27`. Nur die 50 neuen Einträge vom heutigen Lauf haben Werte (Unnamed:25–27: je 50 non-null, Unnamed:24: 12 non-null). Die 433 älteren Zeilen haben keine Werte in diesen Spalten. Ursache: `excel_writer.py` schreibt im `write_only`-Append-Modus und fügt bei Append an eine bestehende Datei keine Spalten-Header in Zeile 1 nach. `dashboard_aggregator.py` und externe Analyse können diese Spalten nicht per Name ansprechen. Behebung: Beim Öffnen einer bestehenden Datei prüfen ob alle MAIN_COLUMNS-Header in Zeile 1 vorhanden sind; fehlende nachträglich einfügen. Aufwand: M.

---

### H4: 51% der Einträge mit Kategorie "Unbekannt" [Anomalien]

**Datei:** `data/willhaben_markt.xlsx`; Quelle: `parser/prompt.py`

245 von 483 Einträgen (51%) tragen Kategorie `"Unbekannt"`. In der parse_cache_v2-Stichprobe (15 Dateien) sind 14/15 = 93% `"Unbekannt"`. Ollama mit `gemma3:27b` klassifiziert Stehplatz/Sitzplatz/VIP/Front-of-Stage selten korrekt ohne explizite Keywords im Anzeigentext. Auswirkung: Dashboard-Filterung nach Kategorie ist weitgehend nutzlos; Preisunterschiede zwischen Sitzplatz und Stehplatz sind nicht auswertbar. Behebung: Few-Shot-Beispiele in `prompt.py` mit mehr Kategorie-Variation ergänzen; Titeltext gezielter in Prompt einbeziehen. Aufwand: M.

---

### H5: 18% der Einträge ohne Event-Datum (88/483) [Anomalien]

**Datei:** `data/willhaben_markt.xlsx`; Quelle: `parser/prompt.py` oder `preprocessing.py`

88 Einträge haben kein Event-Datum. Bei vielen ist das Datum im Titel erkennbar (z.B. "Rammstein 15.06.2025") aber Ollama extrahiert es nicht. Stichprobe aus Review Queue: ID 1256790484 "Konzertkarte" — Datum fehlt obwohl im Text. In der Review Queue sind 31/32 Einträge (96.9%) ohne Event-Datum. Auswirkung: Dashboard-Sortierung nach Datum fehlerhaft; zukünftige Events nicht von vergangenen unterscheidbar. Behebung: Few-Shot-Beispiele für Datum-Extraktion aus Titel in `prompt.py` ergänzen. Aufwand: S.

---

### H6: 18% der Einträge ohne Angebotspreis pro Karte (87/483) [Anomalien]

**Datei:** `data/willhaben_markt.xlsx`; Quelle: `postprocessing.py`

87 Einträge ohne berechneten Preis pro Karte trotz vorhandenem `Angebotspreis gesamt`. Ursache: `anzahl_karten = None` verhindert die Division. Der Aggregator fällt korrekt auf `dropna()` zurück, diese Einträge fehlen aber in Min/Max/Avg-Berechnung. Zusätzlich haben 50 der 144 Händler-Einträge (34.7%) keinen Preis — werden aus der Aggregation korrekt ausgelassen, sind aber trotzdem in der Datei. Behebung: Fallback in `postprocessing.py`: Wenn `anzahl_karten = None` aber `angebotspreis_gesamt` vorhanden → `anzahl_karten = 1` annehmen. Aufwand: XS.

---

### H7: Ollama-Modelle auf externem Volume — Single-Point-of-Failure [Deployment]

**Datei:** `~/Library/LaunchAgents/com.willhabenanalyse.pipeline.plist` — `OLLAMA_MODELS=/Volumes/MacMiniMich/KI`

Das externe Volume `/Volumes/MacMiniMich/KI` ist der einzige Speicherort für alle 7 Ollama-Modelle (primär: `gemma3:27b`, 17.4 GB). Wenn das Volume beim nächtlichen Cron-Start (00:00 Uhr) nicht gemountet ist — z.B. nach Systemreset, Verbindungsunterbruch, Energiesparmodus des externen Laufwerks — findet Ollama kein Modell und die Pipeline schlägt stumm fehl oder gibt leere Analysen zurück. Aktuell funktioniert der Lauf (Volume ist gemountet, Nachweis: erfolgreicher Testlauf heute 09:46). Behebung: `KeepAlive`-Key oder `AssociatedBundleIdentifiers` in plist; alternativ kritische Modelle in Standard-Pfad `~/.ollama/models` spiegeln. Aufwand: S.

---

### H8: Versions-Constraints ohne Pin — Deployment-Instabilität [Deployment]

**Datei:** `/Users/Boti/WillhabenAnalyse/requirements.txt`

Alle 8 Packages verwenden `>=`-Minimalversionen ohne obere Grenze (z.B. `playwright>=1.58.0`, `pydantic>=2.0.0`). Auf einer neuen Maschine würde `pip install -r requirements.txt` die jeweils neuesten Versionen installieren — potenziell inkompatible Breaking Changes. Playwright 2.x oder Pydantic 3.x könnten die Pipeline brechen. Behebung: `pip freeze > requirements.lock` erstellen und für Produktions-Deployments verwenden; aktuell installierte Versionen als Referenz: `playwright==1.58.0`, `pydantic==2.13.2`, `pandas==3.0.2`. Aufwand: XS.

---

## MEDIUM / LOW / INFO (Tabelle)

| # | Titel | Bereich | Severity | Aufwand |
|---|-------|---------|----------|---------|
| M1 | OVP-Parsing-Outlier: 3 Einträge mit Marge < -90% (ID 931008494, 1250771011, 1260078523) | Anomalien | MEDIUM | XS |
| M2 | 2 Non-Ticket False Negatives in Review Queue (ID 1219472817 "Nebelfluid", ID 1218710263 Kategorie-URL) | Anomalien | MEDIUM | S |
| M3 | `unbekannt`-Verkäufertyp (17 Einträge) fällt aus Aggregationsgruppen heraus | Dashboard | MEDIUM | XS |
| M4 | Non-ISO-Datum ID 859029027: `"2026-04-20 & 2026-04-22"` bricht `pd.to_datetime()` | Dashboard | MEDIUM | XS |
| M5 | 4 abgelaufene 2025-Events (IDs 1496940564, 1553269426, 1544521953, 2076375213) mit Confidence=hoch nicht archiviert | Dashboard | MEDIUM | S |
| M6 | `pipeline.log` ohne Rotation — wächst unbegrenzt (4.3 MB nach 4 Tagen, proj. >400 MB/Jahr) | Deployment | MEDIUM | S |
| M7 | 4 von 10 OVP-URLs dysfunktional: szene-wien.com (DNS), gasometer.at (offline), stadthalle.com (Redirect), ticketmaster.at (Folgeschaden) | Deployment / Regression | MEDIUM | S |
| M8 | Python 3.14.4 ist Pre-Release/Beta — keine ABI-Stabilität garantiert für Playwright/pydantic-core | Deployment | MEDIUM | M |
| M9 | OVP-Checker: Massenhafte Playwright `Navigation interrupted by another navigation`-Fehler (>1900 WARNING-Zeilen in log) — Race Condition | Regression | MEDIUM | M |
| M10 | FC3 Concurrent-Spawn-Guard: Tabs-übergreifende Koordination fehlt — paralleler Start über EngineTab + StatusTab möglich | Regression | MEDIUM | S |
| L1 | `Ausverkauft beim Anbieter` 89.6% leer (433/483) — Engpassindikator kaum befüllt | Dashboard | LOW | M |
| L2 | `Verkäufer-ID` 100% leer (483/483) — Spalte wird vom Scraper nicht befüllt | Dashboard | LOW | S |
| L3 | 4 Unnamed-Spalten (24–27) als Excel-Artefakte — Rauschen bei `pd.read_excel()` ohne `usecols` | Dashboard | LOW | XS |
| L4 | `data/parse_cache/` (442 Einträge, v1-Parser, Stand 2026-04-15) — veraltet, ungenutzt, belegt Speicher | Deployment | LOW | XS |
| L5 | `config.json`: `schedule.scrape_interval_minutes: 360` + `schedule.enabled: false` — irreführende Fehlkonfiguration | Deployment | LOW | XS |
| L6 | Plist, Google-Drive-Pfad hard-coded auf Benutzer "Boti" + `mrieder84@gmail.com` — nicht portierbar | Deployment | LOW | INFO |
| L7 | FC2 StatusWriter: `try/except ... raise` statt `try/finally` — `fail()` nicht aufgerufen bei internem `return` (aktuell kein solcher Pfad) | Regression | LOW | XS |
| L8 | FC1 JSON-Parse-Fehler (Structured Output): nicht im Testlauf ausgelöst — nur strukturell adressiert | Regression | LOW | — |
| I1 | Negative Marge bei 82/483 Einträgen (17%) — erwartet, kein Bug | Anomalien | INFO | — |
| I2 | `gemma3:27b` aktuell (2026-04-17), 6 Fallback-Modelle verfügbar — gute Modell-Redundanz | Deployment | INFO | — |
| I3 | `pytest` installiert aber nicht in `requirements.txt` — unsichtbare Dev-Dependency | Deployment | INFO | XS |
| I4 | Letzter Produktionslauf 2026-04-18 09:46: 226 gescrapt, 50 geparst, 43 neu in Excel, 0 Fehler, GDrive-Upload OK | Deployment | INFO | — |

---

## Regression-Check: 5 ursprüngliche Fehlerfälle

| Fehlerfall | Status | Evidenz |
|---|---|---|
| FC1: JSON-Parse-Fehler (Ollama Structured Output) | ⚠️ NICHT VERIFIZIERBAR | `pipeline.py:87-90` fängt Exception — aber kein Fehlerfall im 50er-Testlauf ausgelöst. `errors: []` in final stats. Strukturell adressiert via `format=`-Parameter. |
| FC2: StatusWriter fail() bei Abbruch | ✅ BEHOBEN | `pipeline.py:71-104` — `try/except ... raise` stellt `writer.fail()` bei unkontrollierter Exception sicher. Commit `8a0e17b`. Status `.willhaben_status.json` = `"done"`. |
| FC3: Concurrent-Spawn-Guard | ✅ BEHOBEN (mit Einschränkung) | `engine.py:132-134`, `status.py:149-151` — Guard implementiert. Commit `ec02dae`. ⚠️ Tabs-übergreifende Koordination fehlt (H7 / M10). |
| FC4: ValueError GUI bei leerem Input | ✅ BEHOBEN | `engine.py:162-167` — `try/except ValueError` mit Fehlerdialog. Commit `ec02dae`. Beide Input-Pfade (max_listings + test_batch) gesichert. |
| FC5: after_cancel bei Fenster-Destroy | ✅ BEHOBEN | `status.py:166-170` — `destroy()` cancelt `_after_id` korrekt. Commit `ec02dae`. GUI-spezifisch; kein TclError im 50er-Log. |

**Gesamtbewertung:** 4 von 5 Fehlerfällen durch Code-Review und Commits nachweislich behoben. FC1 strukturell adressiert, aber ohne Live-Fehlerbeweis.

---

## Deployment-Status

| Komponente | Status | Anmerkung |
|---|---|---|
| launchd | ✅ | Installiert, geladen, Exit-Code 0, täglich 00:00 Uhr |
| venv / Python | ⚠️ | Python **3.14.4** (Pre-Release/Beta) — funktional, aber erhöhtes Stabilitätsrisiko |
| Ollama + gemma3:27b | ⚠️ | Erreichbar, Modell vorhanden (17.4 GB, Q4_K_M) — aber auf externem Volume `/Volumes/MacMiniMich/KI` (SPOF) |
| Dependencies | ⚠️ | Alle 8 Packages installiert und satisfiziert — aber keine Lock-Datei, nur `>=`-Constraints |
| Letzter Produktionslauf | ✅ | 2026-04-18 09:46, 226 gescrapt, 50 Events, 43 neu in Excel, 0 Fehler, GDrive OK |
| Letzter Cron-Lauf (launchd) | ✅ | 2026-04-18 00:00:01, 0 Anzeigen (Early-Stop korrekt — kein neues Material) |
| OVP-Quellen | ⚠️ | 4/10 URLs dysfunktional (szene-wien, gasometer, stadthalle, ticketmaster via gasometer) |
| Log-Rotation | ❌ | `pipeline.log` 4.3 MB, kein Rotation-Mechanismus |
| Dashboard | ❌ | Sheet-Name-Bug (C2) + Spalten-Mismatch (C3) → Dashboard seit Tag 1 leer |

---

## Performance-Metriken (aus test_frisch_50_v2.log)

| Metrik | Wert |
|---|---|
| Gescrapte Anzeigen (Übersichtsseiten) | 226 |
| Geparste Events | 50 |
| OVP-gecheckte Events | 31 |
| Neu in Excel eingefügt | 43 |
| Excel aktualisiert | 7 |
| Fehler (errors) | 0 |
| Gesamt-Laufzeit (09:46 Start, log-Ende) | ca. 70–80 Minuten |
| Parse-Dauer pro Anzeige (Unnamed:27 / `parse_dauer_ms`) | Ø **82.957 ms** (~83 Sekunden) |
| Parse-Dauer Min/Max (Stichprobe parse_cache_v2) | 78.000 ms – 88.000 ms |
| OVP-Check-Erfolgsrate (Navigation-Interruptions ausgeschlossen) | 31/50 = 62% |
| OVP-WARNING-Zeilen im Log (Navigation interrupted) | >1.900 |
| Fehlerrate (Parse-Fehler je Anzeige) | 0% (0/50) |

**Hinweis zur Parse-Dauer:** Die Werte 78.000–88.000 ms entsprechen 78–88 Sekunden pro Anzeige mit `gemma3:27b` (Q4_K_M, 17.4 GB). Bei 100 Anzeigen: ca. 2,2–2,5 Stunden. Bei 350 Anzeigen: ca. 7,6–8,6 Stunden — ein vollständiger Nachtlauf mit 350 Listings würde den 24-Stunden-Takt überschreiten. Das `max_listings`-Limit (config: 250) ist daher nicht nur funktional sondern auch performance-kritisch.

---

## GO-Gate Phase B → Phase C

### CRITICAL Blockers für Produktions-Deployment

| Finding | Beschreibung | Phase C blockiert? |
|---|---|---|
| C1 | Fehlender 350-Anzeigen-Testlauf | NEIN (kein Dokumentationsproblem) |
| C2 | Dashboard liest falschen Sheet-Namen — immer leer | NEIN (Dokumentation kann trotzdem verfasst werden) |
| C3 | Spalten-Namen-Mismatch Aggregator vs. Excel | NEIN |
| C4 | Angebotspreis = 0 € in Produktionsdaten | NEIN |

Alle 4 CRITICAL Findings blockieren den **Produktions-Einsatz**, aber **nicht Phase C (Dokumentations-Audit)**. Phase C ist unabhängig von der Code-Korrektheit — sie dokumentiert den Ist-Zustand und identifiziert Dokumentationslücken.

### Für den Audit (Phase C — Dokumentation)

Phase C ist **nicht blockiert**. Die Befunde aus Phase B (insbesondere C1–C4, H1–H8) liefern konkrete Dokumentationsaufgaben für Phase C: fehlende Architektur-Doku für den Dashboard-Aggregator, fehlende Testlauf-Checkliste, fehlende OVP-Quellen-Wartungsanleitung und fehlende Performance-Schätzungen für höhere max_listings-Werte.

### Empfehlung

**GO für Phase C** (Dokumentations-Audit ist unabhängig von Code-Bugs) mit dem Vermerk, dass C1–C4 sowie H7 (externes Volume SPOF) und H8 (fehlende requirements.lock) vor dem Produktions-Einsatz behoben werden müssen. Empfohlene Reihenfolge der Code-Fixes nach Phase C:

1. **C2 + C3** (XS + S): Dashboard-Bug beheben — höchste Sichtbarkeit, kleinster Aufwand
2. **C4** (XS): Nullpreis-Validierung
3. **H8** (XS): `requirements.lock` erstellen
4. **C1** (M): Echter 100-Anzeigen-Testlauf durchführen
5. **H7** (S): Ollama-Volume-SPOF entschärfen
6. **H1–H6**: Datenqualität und Performance nach Zeitplan

---

*Audit erstellt: 2026-04-18 — WillhabenAnalyse v2.1 — Basis: 4 Phase-B Findings-Dateien (Regression, Anomalien, Dashboard, Deployment)*
