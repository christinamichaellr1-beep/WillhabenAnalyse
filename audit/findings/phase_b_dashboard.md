# Phase B — Dashboard-Verifikation
**Geprüft:** 2026-04-18  
**Excel:** data/willhaben_markt.xlsx (483 Zeilen Hauptübersicht, 290 einzigartige Events)  
**Aggregator:** app/backend/dashboard_aggregator.py  
**Raw-Cache:** data/parse_cache_v2/ (50 JSON-Dateien)

---

## Sheet-Übersicht

| Sheet | Zeilen | Beschreibung |
|---|---|---|
| Hauptübersicht | 483 | Hauptdatensatz aller gescrapten Anzeigen |
| Review Queue | 32 | Niedrig-Confidence-Einträge, alle Confidence=niedrig |
| Archiv | 191 | Vergangene/abgelaufene Events |
| Watchlist-Config | 1 | Konfiguration (Linkin Park Beispiel) |

**Kein Sheet namens "Angebote" vorhanden** — relevant für Finding F-1 (kritisch).

---

## A) Aggregations-Korrektheit

Die `aggregate()`-Funktion wurde mit den Excel-Daten manuell verifiziert (Spalten-Umbenennung auf die erwarteten internen Namen). Alle 5 geprüften Events lieferten exakt übereinstimmende Werte.

### Spot-Checks

| Event | Gruppe | Kennzahl | Manuell berechnet | Aggregator-Ausgabe | Ergebnis |
|---|---|---|---|---|---|
| Linkin Park | 2026-06-09 / Sitzplatz | Händler: n=4, avg=249.00, min=249, max=249 | 249.00 | 249.00 | **KORREKT** |
| Linkin Park | 2026-06-09 / Sitzplatz | Privat: n=2, avg=97.50, min=95, max=100 | 97.50 | 97.50 | **KORREKT** |
| Linkin Park | 2026-06-09 / Sitzplatz | OVP (Median) | 105.00 | 105.00 | **KORREKT** |
| Böhse Onkelz | 2026-06-20 / Front-of-Stage | Händler: n=5, avg=229.00 | 229.00 | 229.00 | **KORREKT** |
| Böhse Onkelz | 2026-06-20 / Stehplatz | Privat: n=1, avg=67.50 | 67.50 | 67.50 | **KORREKT** |
| Foo Fighters | 2026-07-03 / Sitzplatz | Privat: n=2, avg=140.00 | 140.00 | 140.00 | **KORREKT** |
| Foo Fighters | 2026-07-03 / Stehplatz | Händler: n=2, avg=159.00, OVP=97.00 | 159.00 / 97.00 | 159.00 / 97.00 | **KORREKT** |
| Seiler und Speer | 2026-07-26 / Front-of-Stage | Händler: n=3, avg=134.25 (44.75+179+179)/3 | 134.25 | 134.25 | **KORREKT** |
| Lacazette | 2026-04-15 / Unbekannt | Privat: n=5, avg=57.00 (45+55+60+55+70)/5 | 57.00 | 57.00 | **KORREKT** |
| Lacazette | 2026-04-15 / Stehplatz | Händler: n=3, avg=39.00; OVP=47.40 | 39.00 / 47.40 | 39.00 / 47.40 | **KORREKT** |

**Fazit:** Die Aggregations-Logik (Min/Max/Avg/Count, OVP-Median, Gruppen-Keys) rechnet vollständig korrekt — **sofern sie überhaupt Daten bekommt** (siehe Finding F-1).

**Nebeneffekt entdeckt:** Events mit `NaN`-Datum werden korrekt als separate Gruppe behandelt (dropna=False in groupby). Die Funktion `load_excel()` liest Sheet "Angebote" — dieses existiert nicht in der Datei.

---

## B) OVP-Korrektheit

Verglichen wurden alle 50 Einträge aus `data/parse_cache_v2/` mit der Excel-Hauptübersicht (Join auf Anzeigen-ID).

| Anzeigen-ID | Event | OVP Excel | OVP Cache | Ergebnis |
|---|---|---|---|---|
| 1242483640 | (Konzert) | 36.90 | 36.90 | **KORREKT** |
| 1307036442 | (Konzert) | 22.00 | 22.00 | **KORREKT** |
| 1427016553 | Kurzurlaub Steiermark | 429.00 | 429.00 | **KORREKT** |
| 1260078523 | (Konzert) | 18.99 | 18.99 | **KORREKT** |
| 1165795297 | (Konzert) | 11.60 | 11.60 | **KORREKT** |
| 1873191466 | (Konzert) | 12.00 | 12.00 | **KORREKT** |
| 1444614985 | (Konzert) | 10.00 | 10.00 | **KORREKT** |
| 949072645 | (Konzert) | 27.50 | 27.50 | **KORREKT** |
| 1615549054 | (Konzert) | 24.90 | 24.90 | **KORREKT** |
| 939443805 | (Konzert) | 14.00 | 14.00 | **KORREKT** |

**Alle 10 geprüften OVP-Werte stimmen exakt überein (0 Abweichungen).**  
Der OVP-Wert in der Excel ist ein **fixer Wert direkt aus dem JSON-Cache**, kein Durchschnitt. Die `aggregate()`-Funktion berechnet erst bei der Aggregation den Median über die Gruppe.

---

## C) Händler/Privat-Klassifikation

### Stichprobe (alle 50 Cache-Excel-Matches geprüft)

| Anzeigen-ID | Excel Typ | Cache Typ | Ergebnis |
|---|---|---|---|
| 1242483640 | Privat | Privat | OK |
| 1307036442 | Privat | Privat | OK |
| 1471700062 | Privat | Privat | OK |
| 1742349434 | Privat | Privat | OK |
| 1379231218 | Privat | Privat | OK |
| ... (alle 50) | — | — | 0 Mismatches |

**Fehlerrate Excel↔Cache: 0/50 (0%)**. Die Klassifikation wird 1:1 aus dem `verkäufertyp`-Feld des JSON übernommen.

### Problemklassen in der Hauptübersicht

| Verkäufertyp | Anzahl | Aggregator-Behandlung |
|---|---|---|
| Privat | 322 | Korrekt → Privat-Gruppe |
| Händler | 144 | Korrekt → Händler-Gruppe |
| **unbekannt** | **17** | **PROBLEM: fällt in keine Gruppe** |

**Kritisch:** Der Aggregator normalisiert nur `None`/`NaN` → "Privat". Der Wert `"unbekannt"` wird weder als "Privat" noch als "Händler" behandelt — diese 17 Einträge verschwinden aus beiden Gruppen (Privat_Anzahl und Haendler_Anzahl zählen sie nicht). Das betrifft u.a. reale Events: KORN, ONEREPUBLIC, GROSSSTADTGEFLÜSTER, BÖHSE ONKELZ (Großschreibung-Variante), BEATSTEAKS, BERQ.

**Zusätzlich:** 50 Händler-Einträge (34.7% aller Händler) haben keinen Preis (`Angebotspreis pro Karte` und `Angebotspreis gesamt` beide leer). Diese werden in der Aggregation korrekt ausgelassen (dropna in `_stats()`), sind aber trotzdem als Händler gezählt wenn `preis_pro_karte`=NaN — tatsächlich werden sie via `prices = sub[_PREIS_COL].dropna()` herausgefiltert, also Händler_Anzahl für diese Einträge = 0.

---

## D) Datum-Format

| Eigenschaft | Wert |
|---|---|
| dtype in pandas | `str` (object) |
| Vorherrschendes Format | ISO-8601: `YYYY-MM-DD` (z.B. `2026-07-03`) |
| Sortierbarkeit | Ja — ISO-8601 ist direkt lexikographisch sortierbar |
| Non-ISO Eintrag | 1 Eintrag: `"2026-04-20 & 2026-04-22"` (ID 859029027, Musikverein Konzert) |
| Vergangene Daten (2025) | 4 Einträge mit Confidence=hoch: Die Toten Hosen (2×, 2025-09-12), Böhse Onkelz (2025-06-20), LEVEL ONE (2025-11-07) |
| NaN-Datum | 88/483 = 18.2% |

**Anomalie:** Der Doppel-Datum-Eintrag `"2026-04-20 & 2026-04-22"` bricht Datums-Parsing in jedem Downstream-System.  
**Anomalie:** 4 Events mit Datum in 2025 sind offensichtlich abgelaufene Events mit hoher Confidence — sollten ins Archiv.

---

## E) Spalten-Vollständigkeit

### Hauptübersicht (483 Zeilen)

| Spalte | Null-Anzahl | Null-Rate | Bewertung |
|---|---|---|---|
| Scan-Datum | 0 | 0.0% | OK |
| Willhaben-Link | 0 | 0.0% | OK |
| Anzeigen-ID | 0 | 0.0% | OK |
| **Verkäufer-ID** | **483** | **100.0%** | LEER — komplett fehlend |
| Verkäufername | 161 | 33.3% | Akzeptabel (Händler haben oft keinen Namen) |
| Verkäufertyp | 0 | 0.0% | OK |
| Mitglied seit | 161 | 33.3% | Akzeptabel (korreliert mit Händlern) |
| Event-Name | 8 | 1.7% | Niedrig — OK |
| Event-Datum | 88 | 18.2% | Mittel — Parsing-Problem |
| Venue | 180 | 37.3% | Mittel |
| Stadt | 27 | 5.6% | Niedrig — OK |
| Kategorie | 0 | 0.0% | OK |
| Anzahl Karten | 88 | 18.2% | Mittel |
| Angebotspreis gesamt | 62 | 12.8% | Niedrig — OK |
| Preis ist pro Karte | 44 | 9.1% | Niedrig — OK |
| Angebotspreis pro Karte | 87 | 18.0% | Mittel |
| **Originalpreis pro Karte** | **175** | **36.2%** | Hoch — OVP fehlt bei 36% |
| OVP-Quelle | 176 | 36.4% | Hoch — korreliert mit OVP |
| **Marge €** | **228** | **47.2%** | Hoch — fast 50% ohne Marge |
| **Marge %** | **228** | **47.2%** | Hoch — fast 50% ohne Marge |
| **Ausverkauft beim Anbieter** | **433** | **89.6%** | Sehr hoch — faktisch leer |
| Watchlist | 0 | 0.0% | OK |
| Confidence | 0 | 0.0% | OK |
| Review nötig | 0 | 0.0% | OK |
| Unnamed: 24–27 | 433–471 | 89–97% | Leere Hilfsspalten — Artefakte |

### v2-spezifische Spalten (parse_cache_v2, 50 Records)

| Spalte | Null-Rate | Werte |
|---|---|---|
| `modell` | 0% | `gemma3:27b` (alle 50) |
| `pipeline_version` | 0% | `v2.0` (alle 50) |
| `parse_dauer_ms` | 0% | Ø 82.957 ms |

Alle v2-spezifischen Felder sind vollständig befüllt.

---

## F) Review-Queue-Qualität

**Sheet vorhanden:** Ja — "Review Queue" mit 32 Einträgen.

| Kennzahl | Wert |
|---|---|
| Alle Einträge Confidence=niedrig | Ja (32/32) |
| Event-Name fehlt | 7/32 (21.9%) |
| Event-Datum fehlt | 31/32 (96.9%) |
| Angebotspreis fehlt | 17/32 (53.1%) |
| Ollama-Parse-Fehler | 13/32 (40.6%) |
| Fehlklassifikationen (kein Ticket) | 5/32 — Nebelfluid, Kurzurlaub, Chalet, Gutschein, Saison-Listing |
| Händler-Einträge | 9/32 |
| unbekannt-Typ | 7/32 |

**Qualität:** Die Queue ist ein valides Sicherheitsnetz. 40.6% sind reine Ollama-Timeouts/Fehler (keine Inhaltsprobleme), 15.6% sind echte Fehlklassifikationen die manuell bereinigt werden müssten. Der Großteil der Einträge (31/32) hat kein Event-Datum — dies ist strukturell erwartet für Niedrig-Confidence-Fälle.

---

## Findings

### F-1 — KRITISCH: Sheet-Name-Mismatch — Aggregator liefert immer leeres Ergebnis

**Severity:** KRITISCH  
**Details:** `dashboard_aggregator.load_excel()` liest Sheet `"Angebote"`. Dieses Sheet existiert nicht in `data/willhaben_markt.xlsx`. Die tatsächlichen Daten liegen in `"Hauptübersicht"`. Der `except`-Block fängt den Fehler still ab und gibt `pd.DataFrame()` zurück. Das Dashboard-Aggregat ist damit dauerhaft leer — alle Aggregationsberechnungen laufen auf einem leeren DataFrame.  
**Fix:** Sheet-Name in `load_excel()` auf `"Hauptübersicht"` ändern, oder Excel-Sheet umbenennen.

---

### F-2 — HOCH: Marge-Berechnung in 34 Zeilen (13.3%) falsch

**Severity:** HOCH  
**Details:** 34 von 255 Zeilen mit Marge-Werten (13.3%) zeigen inkonsistente Marge€/Marge%-Werte relativ zur `Originalpreis pro Karte`-Spalte derselben Zeile. Die Marge wurde mit einem anderen OVP berechnet als dem gespeicherten. Für 19 dieser Fälle ist der implizierte OVP-Wert nicht in der Datei nachweisbar (externer OVP-Lookup?). Betroffen sind u.a. Foo Fighters, Böhse Onkelz, Tokio Hotel, Linkin Park, Die Toten Hosen, Herbert Grönemeyer, Nick Cave.  
**Formel in Excel:** Marge% = (Angebotspreis − OVP_verwendet) / OVP_verwendet × 100  
**Problem:** OVP_verwendet ≠ gespeicherter `Originalpreis pro Karte` in 13.3% der Fälle.  
**Auswirkung:** `aggregate()` berechnet seine eigene Marge% basierend auf dem `Originalpreis pro Karte`-Median — diese Werte weichen von den Excel-Margen ab.

---

### F-3 — MITTEL: `unbekannt`-Verkäufertyp fällt aus Aggregation heraus

**Severity:** MITTEL  
**Details:** 17 Einträge (3.5%) tragen `Verkäufertyp = "unbekannt"`. Der Aggregator filtert nur `None`/`NaN` → "Privat", nicht aber den String "unbekannt". Diese Einträge werden in keiner Gruppe gezählt (weder Privat_Anzahl noch Haendler_Anzahl), sind aber vollständige Einträge mit Preisdaten (z.B. KORN 119€, ONEREPUBLIC 99€, BERQ 85€).  
**Fix:** In `aggregate()` Normalisierungslogik erweitern: `df[_ANBIETER_TYP_COL].replace("unbekannt", "Privat")` oder separate Behandlung.

---

### F-4 — MITTEL: 1 Non-ISO-Datum bricht Datums-Parsing

**Severity:** MITTEL  
**Details:** Anzeigen-ID 859029027 (Musikverein Konzert) enthält `Event-Datum = "2026-04-20 & 2026-04-22"`. Jedes System das dieses Feld als Datum parsed (z.B. `pd.to_datetime()`) wirft einen Fehler oder NaT. Im Aggregator wird es aktuell als String-Gruppe behandelt — was zu einer eigenen Aggregations-Gruppe mit diesem Fantasie-Datum führt.  
**Fix:** Scraper-seitig auf erstes Datum normalisieren; oder Validierungsschritt vor Aggregation.

---

### F-5 — MITTEL: 4 abgelaufene Events (2025) mit Confidence=hoch in Hauptübersicht

**Severity:** MITTEL  
**Details:** Die Toten Hosen (IDs 1496940564, 1553269426, 2025-09-12), Böhse Onkelz (ID 1544521953, 2025-06-20) und LEVEL ONE (ID 2076375213, 2025-11-07) haben Datumsangaben in 2025 und Confidence=hoch. Sie wurden nicht automatisch ins Archiv verschoben obwohl ihr Event-Datum > 6 Monate in der Vergangenheit liegt.

---

### F-6 — NIEDRIG: `Ausverkauft beim Anbieter` zu 89.6% leer

**Severity:** NIEDRIG  
**Details:** 433 von 483 Einträgen (89.6%) haben kein `Ausverkauft beim Anbieter`-Wert. Dieses Feld ist für die Marktanalyse relevant (Engpassindikator), wird aber kaum befüllt. Kein Aggregationsfeld hängt aktuell davon ab.

---

### F-7 — NIEDRIG: `Verkäufer-ID` komplett leer (100%)

**Severity:** NIEDRIG  
**Details:** Die Spalte `Verkäufer-ID` ist in allen 483 Zeilen leer. Sie scheint nicht vom Scraper befüllt zu werden. Kein aktueller Aggregationslogik-Pfad nutzt sie.

---

### F-8 — NIEDRIG: Unnamed-Spalten (24–27) als Artefakte

**Severity:** NIEDRIG  
**Details:** 4 unnamed Spalten (89–97% leer) sind Überreste von Excel-Formatierung. Sie erzeugen Rauschen beim `pd.read_excel()`-Aufruf ohne `usecols`.

---

## Zusammenfassung

| # | Severity | Finding |
|---|---|---|
| F-1 | KRITISCH | Sheet-Name "Angebote" fehlt — Aggregator gibt immer leeres DataFrame |
| F-2 | HOCH | 34 Zeilen (13.3%) mit inkonsistenter Marge-Berechnung |
| F-3 | MITTEL | 17 `unbekannt`-Einträge fallen aus Aggregationsgruppen heraus |
| F-4 | MITTEL | 1 Non-ISO-Datum bricht Datums-Parsing |
| F-5 | MITTEL | 4 abgelaufene 2025-Events nicht archiviert |
| F-6 | NIEDRIG | `Ausverkauft beim Anbieter` 89.6% leer |
| F-7 | NIEDRIG | `Verkäufer-ID` 100% leer |
| F-8 | NIEDRIG | 4 leere Unnamed-Spalten als Excel-Artefakte |

**Positive Befunde:**
- Aggregationslogik (Min/Max/Avg/OVP-Median) rechnet **mathematisch korrekt** (10/10 Spot-Checks bestanden)
- OVP-Werte **100% konsistent** zwischen Excel und parse_cache_v2 (10/10)
- Händler/Privat-Klassifikation **0 Fehler** in 50 geprüften Einträgen
- v2-spezifische Felder (`modell`, `pipeline_version`, `parse_dauer_ms`) **vollständig befüllt**
- ISO-8601-Datumsformat **nahezu einheitlich** (1 Ausreißer)
