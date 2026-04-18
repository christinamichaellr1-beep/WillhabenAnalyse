# Phase B — Anomalie-Detektion
**Geprüft:** 2026-04-18  
**Datengrundlage:** 50 Einträge in parse_cache_v2/ (alle vollständig gelesen), 226 Einträge in raw_cache/ (30 stichprobenartig), Log test_frisch_50_v2.log (vollständig gelesen), .willhaben_status.json

---

## Zusammenfassung

| Anomalie-Typ | Anzahl | Severity |
|---|---|---|
| preis_ist_pro_karte falsch gesetzt → 700€/Karte-Fehler | 1 | CRITICAL |
| Kategorie "Unbekannt" | 45 / 50 (90%) | HIGH |
| Non-Ticket im parse_cache (Programmheft, nicht erkannt) | 1 | HIGH |
| Datum: vergangene Events im parse_cache | 22 / 50 (44%) | HIGH |
| confidence=hoch ohne Schutz bei Preis-Inkonsistenz | systemisch | HIGH |
| Datum: Parser-Fehler (falsches Jahr extrahiert) | 2 | HIGH |
| Non-Ticket im parse_cache (teilweise erkannt) | 2 | MEDIUM |
| Preis None obwohl preis_roh vorhanden | 1 | MEDIUM |
| OVP-Check komplett ausgefallen (alle 50) | 50 / 50 | MEDIUM |
| Datum None | 3 | MEDIUM |
| Preis < 5€/Karte (inkl. 0€-Verschenk) | 3 | LOW |
| Event-Name = None | 0 | INFO |
| Event-Name < 3 Zeichen | 0 | INFO |
| Event-Name enthält Preisangabe | 0 | INFO |
| Datum > 2030 | 0 | INFO |

---

## A) Preis-Anomalien

### A1 — angebotspreis_gesamt = None, preis_roh vorhanden

| willhaben_id | event_name | preis_roh | confidence | confidence_grund |
|---|---|---|---|---|
| 1165795297 | Maria Theresia | € 6 | mittel | Anzahl Karten unklar |

**Befund:** Raw-Preis `€ 6` klar vorhanden (Willhaben-Listing-Preis), aber Parser extrahierte `None`. Ursache: Das Angebot ist ein **Programmheft** (Titel: "Programmheft Musical 'Maria Theresia'"), kein Eintrittskartenticket. Der Parser erkannte keinen sinnvollen Ticketpreis, lieferte aber auch keinen Non-Ticket-Flag — sondern behandelt es als valides Ticket mit unklarer Anzahl. Zusätzlich: `originalpreis_pro_karte=11.6` gesetzt (Phantomwert).  
**Severity: MEDIUM** — Symptom; eigentliche Anomalie ist die fehlende Non-Ticket-Erkennung (→ F).

---

### A2 — Preis < 5€ pro Karte

| willhaben_id | event_name | angebotspreis | preis_ist_pro_karte | anzahl | calc | Bewertung |
|---|---|---|---|---|---|---|
| 1451378514 | Die Schachnovelle | 0.0 | False | 2 | 0.00€ | Korrekt: "zu verschenken", Anzeige bereits reserviert |
| 1260078523 | Der Nino aus Wien & die AusWienBand | 1.0 | True | 1 | 1.00€ | Korrekt: preis_roh=€1, symbolischer Preis |
| 2140103846 | Mozart im Rabenhof | 20.0 | False | 5 | 4.00€ | Korrekt: 5 Karten à 4€ = Kinderkonzert |

**Befund:** Alle drei Fälle sind inhaltlich korrekt geparst. Kein Parsing-Fehler.  
**Severity: LOW**

---

### A3 — Preis > 500€ pro Karte (KRITISCHER PARSING-FEHLER)

| willhaben_id | event_name | preis_roh | angebotspreis_gesamt | preis_ist_pro_karte | anzahl | calc_per_karte |
|---|---|---|---|---|---|---|
| 847435356 | Maria Theresia | € 100 | 700.0 | **True** (falsch) | 7 | **700€/Karte** |

**Befund:** Anzeige verkauft 7 Tickets zu je 100€ (Gesamtpreis: 700€, Originalpreis 119€/Karte). Parser extrahierte `angebotspreis_gesamt=700` (korrekt: Gesamtpreis) aber `preis_ist_pro_karte=True` (FALSCH). Die korrekte Kodierung wäre entweder:
- `angebotspreis_gesamt=700, preis_ist_pro_karte=False` (700€ Gesamt), oder
- `angebotspreis_gesamt=100, preis_ist_pro_karte=True` (100€ pro Stück)

Das falsche Flag führt zur Berechnung 700€/Karte. Confidence=**hoch** ohne jede Warnung — das Modell sieht keine Inkonsistenz.  
**Severity: CRITICAL** — systematischer Fehler; confidence schützt nicht vor Flag-Inkonsistenz.

---

### A4 — Negativmarge (Angebotspreis/Karte > OVP) — Artefakte

| willhaben_id | event_name | OVP | Angebot/Karte berechnet | Ursache |
|---|---|---|---|---|
| 2076375213 | LEVEL ONE – VIENNA'S FIRST TEEN CLUB | 12.0 | 36.0 | Artefakt: angebotspreis_gesamt=36 (richtig: Gesamt) + preis_ist_pro_karte=True (falsch) |
| 847435356 | Maria Theresia | 119.0 | 700.0 | Artefakt: s.o. A3 |

**Befund:** Beide Negativmargen sind **keine echten Aufschläge**. Bei 2076375213 ("3 Tickets zu je 12€, Originalpreis") ist der Angebotspreis identisch mit dem OVP (kein Aufschlag). Parser setzt angebotspreis_gesamt=36 (korrekt: 3×12) aber preis_ist_pro_karte=True (falsch) → 36 > 12 scheinbar negativ.  
**Severity: MEDIUM** — Folge des preis_ist_pro_karte-Fehlers aus A3.

---

## B) Datum-Anomalien

### B1 — Events mit Datum in der Vergangenheit: 22 von 50 (44%)

| willhaben_id | event_name | event_datum | Typ |
|---|---|---|---|
| 875342147 | Rock in Riem | 1994-05-21 | Sammlerstück — korrekt (Anzeige verkauft altes Ticket) |
| 1825523594 | Kunstschatzi | 2024-03-24 | **Parser-Fehler: Anzeige vom 2026-04-18, Event vor 2 Jahren** |
| 2076375213 | LEVEL ONE – VIENNA'S FIRST TEEN CLUB | 2025-11-07 | **Parser-Fehler: Anzeige vom 2026-03-30, Event vor 5 Monaten** |
| 2145392335 | Liv, Love, Laugh, Strömquist | 2026-03-22 | Abgelaufen (26 Tage vergangen) |
| 1011951006 | Die Verlorene Ehre der Katharina Blum | 2026-03-17 | Abgelaufen |
| 1032365306 | Zum ass im Ärmel | 2026-03-28 | Abgelaufen |
| 1585191197 | Staatsoper Veranstaltung mit Welser-Möst | 2026-04-02 | Abgelaufen |
| 1615549054 | Constellation Choir and Orchestra | 2026-04-07 | Abgelaufen |
| 931008494 | Imperial Gala Concert | 2026-04-06 | Abgelaufen |
| 949072645 | Efeu Fest | 2026-04-10 | Abgelaufen |
| 2023012047 | Cloud 7 | 2026-04-11 | 7 Tage alt |
| 1120238997 | Adriatique | 2026-04-03 | Abgelaufen |
| 1165795297 | Maria Theresia | 2026-04-16 | Vorgestern (Programmheft) |
| 1507000726 | Mahler 9 | 2026-04-16 | Vorgestern |
| 1086858617 | Vicky | 2026-04-17 | Gestern |
| 1242483640 | Apollo Brown | 2026-04-17 | Gestern |
| 1260078523 | Der Nino aus Wien & die AusWienBand | 2026-04-17 | Gestern |
| 1295685815 | SHAKE STEW | 2026-04-17 | Gestern (Graz) |
| 1471700062 | Nino aus Wien | 2026-04-17 | Gestern |
| 1964899751 | Vicky Konzert | 2026-04-17 | Gestern |
| 1965037994 | UBC battle culture | 2026-04-17 | Gestern |
| 2140103846 | Mozart im Rabenhof | 2026-04-17 | Gestern |

**Befund:**
- 20 von 22 vergangenen Daten sind **strukturell erklärbar**: Der max_age_days=3-Cutoff filtert nach Anzeigen-Einstelldatum, nicht nach Event-Datum. Eine am 16.04. eingestellte Anzeige kann ein Event vom 02.04. bewerben.
- **2 echte Parser-Fehler** (HIGH):
  - **1825523594** "Kunstschatzi": Anzeige vom 2026-04-18, Text "heute 24.3." → Parser interpretierte "24.3." als 2024-03-24 statt 2026-03-24.
  - **2076375213** "LEVEL ONE": Anzeige vom 2026-03-30, Titel "Heute 30.3." → Event-Datum 2025-11-07 (völlig falsch extrahiert, vermutlich aus früherem Anzeigentext).

**Severity: HIGH** für die 2 Parser-Fehler; MEDIUM/strukturell für die übrigen 20.

### B2 — Datum > 2030
Keine gefunden. Kein Problem.

### B3 — Datum = None

| willhaben_id | event_name | Erklärung |
|---|---|---|
| 1155933700 | OETICKET | Gutschein, kein Event → korrekt None |
| 1427016553 | MEHRERE | Urlaubs-Paket, kein Konzertdatum → inhaltlich korrekt None, aber falscher Eintrag |
| 1444614985 | Nova Rock 2026 | Green-Camping-Ticket — kein konkretes Tagesdatum → akzeptabel |

**Severity: MEDIUM** — 2 dieser 3 Fälle sollten als Non-Tickets herausgefiltert sein.

---

## C) Event-Name-Anomalien

### C1 — Event-Name = None/leer
**Keine gefunden.** Alle 50 Einträge haben einen event_name.

### C2 — Event-Name < 3 Zeichen
**Keine gefunden.**

### C3 — Event-Name enthält Preisangabe
**Keine gefunden.** Parser trennt Preis sauber vom Event-Namen.

### C4 — Inhaltlich problematische Event-Namen

| willhaben_id | event_name | Problem |
|---|---|---|
| 1155933700 | OETICKET | Name ist der Ticketanbieter, kein Event — Non-Ticket im System |
| 1427016553 | MEHRERE | Platzhalter — Non-Ticket (Urlaubs-Paket) im System |

**Severity: LOW** — kein technischer Parsing-Fehler, aber inhaltlich falsche Einträge (→ F).

---

## D) Confidence-Verteilung

| Confidence | Anzahl | Anteil |
|---|---|---|
| hoch | 38 | 76.0% |
| mittel | 11 | 22.0% |
| niedrig | 1 | 2.0% |

**Einziger "niedrig"-Eintrag:**
- **1155933700** "OETICKET" — confidence_grund: "Kein Konzert, sondern Gutschein" — korrekt erkannt und flaggt.

**Bewertung:**

76% hoch-confidence ist bei den gefundenen Fehlern **zu optimistisch**. Mindestens 4 Einträge mit confidence=hoch weisen nachgewiesene Fehler auf:
- **847435356** (hoch) → 700€/Karte-Fehler durch falsches preis_ist_pro_karte-Flag
- **1825523594** (hoch) → event_datum 2 Jahre falsch
- **2076375213** (hoch) → event_datum 5 Monate falsch + preis_ist_pro_karte inkonsistent
- **1444614985** (hoch) → event_datum=None für Festival-Ticket

**Kritisches Problem:** Das Confidence-System prüft keine interne Konsistenz zwischen `angebotspreis_gesamt`, `preis_ist_pro_karte` und `anzahl_karten`. Ein offensichtlich falsches Preis-Flag wird mit "hoch" bewertet.

Alle mittel-confidence Fälle stichprobenartig geprüft: keine False Positives — mittel ist korrekt vergeben (fehlende Daten, ältere Events, Gutscheine).

**Severity: HIGH** — confidence-Skala ist nicht sensitiv genug für Preis-Logik-Fehler.

---

## E) Kategorie-Verteilung

| Kategorie | Anzahl | Anteil |
|---|---|---|
| Unbekannt | 45 | 90.0% |
| Sitzplatz | 2 | 4.0% |
| Stehplatz | 2 | 4.0% |
| Gemischt | 1 | 2.0% |

**90% "Unbekannt" überschreitet die Warnschwelle von 30% mehr als dreifach.**

**Plausibilitätsprüfung der 5 kategorisierten Einträge:**

| willhaben_id | event_name | Kategorie | Bewertung |
|---|---|---|---|
| 1379231218 | Lepa Brena | Sitzplatz | Plausibel (Konzerthalle) |
| 868590090 | Lepa Brena Konzert | Sitzplatz | Plausibel |
| 1451378514 | Die Schachnovelle | Stehplatz | Plausibel (Burgtheater Stehplatz existiert) |
| 888296624 | Jazeek 4ever Tour 2026 | Stehplatz | Plausibel (Tour-Konzert) |
| 1155933700 | OETICKET | Gemischt | Fragwürdig (Gutschein ohne Kategorie) |

Keine unplausiblen Zuordnungen. Die 5 kategorisierten Einträge sind korrekt.

**Befund:** Das Modell klassifiziert nur dann, wenn explizite Keywords im Text vorkommen ("Stehplatz", "Sitzplatz"). Alle anderen 45 Einträge bekommen "Unbekannt". Das Kategorie-Feld ist für 90% der Daten praktisch unbrauchbar.  
**Severity: HIGH** — Feld funktioniert strukturell nicht.

---

## F) Non-Ticket-Filter-Performance

### F1 — Architektur: Kein dedizierter Pre-Parse-Filter

**Wichtige Erkenntnis:** Das System hat **keinen regelbasierten Non-Ticket-Filter vor dem Parsing**. Die Pipeline ist:
1. Scraping (454 Links)
2. Cutoff-Datum-Filter (228 übersprungen — Anzeige-Einstelldatum, nicht Event-Datum)
3. max-listings=50 (nur erste 50 der 226 verbleibenden geparst)
4. LLM-Parsing — Non-Ticket-Erkennung ausschließlich durch Ollama-Urteil

### F2 — Filterrate / False-Negative-Analyse

| Stufe | Anzahl | Anmerkung |
|---|---|---|
| Gesamt gescrapt (Seiten 1–5) | 454 | |
| Nach Cutoff-Datum übersprungen | 228 (50.2%) | Anzeige vor 2026-04-15 eingestellt |
| Verbleibend | 226 | |
| Geparst (max-listings=50) | 50 | Erste 50 in Scraping-Reihenfolge |
| Nicht geparst | 176 | **KEIN Filter** — reine Mengenbegrenzung |

Die 176 "raw-only" Dateien sind **valide Konzertickets** die schlicht außerhalb des 50er-Caps lagen. Stichprobe von 30 Einträgen: ausnahmslos echte Tickets (Kiki Rockwell, Beatsteaks, Joe Bonamassa, Paul van Dyke, Fuzzman, Greeen, etc.). **Keine False Negatives durch Filter.**

### F3 — False Positives (Non-Tickets im parse_cache_v2): 3 von 50 (6%)

| willhaben_id | event_name | Art des Non-Tickets | Erkannt? | confidence |
|---|---|---|---|---|
| 1155933700 | OETICKET | €20-Gutschein für oeticket.com | JA — confidence=niedrig, Grund "Kein Konzert, sondern Gutschein" | niedrig |
| 1427016553 | MEHRERE | 8-Tage-Urlaubs-Paket (Steiermark, 399€) | TEILWEISE — confidence=mittel, Grund "Gutschein für Urlaub" | mittel |
| 1165795297 | Maria Theresia | Programmheft (kein Eintrittskarten-Ticket) | NICHT ERKANNT — confidence=mittel ohne Non-Ticket-Flag | mittel |

**Non-Ticket-Erkennungsrate: 2 von 3 = 67%** (1 vollständig, 1 teilweise, 1 nicht).

**Das Programmheft (1165795297) ist der kritischste Fall:** Der Parser extrahiert event_name, venue, event_datum und originalpreis_pro_karte — behandelt das Programmheft als reguläres Ticket. Einziger Hinweis: angebotspreis_gesamt=None und confidence_grund="Anzahl Karten unklar".

### F4 — False Negatives (echte Tickets irrtümlich gefiltert)
**Keine gefunden.** Der Cutoff-Datum-Filter filtert nach Anzeigen-Datum (korrekt), und der 50er-Cap ist keine inhaltliche Filterung.

**Severity: CRITICAL** — Kein dedizierter Non-Ticket-Regelfilter; LLM-Erkennung mit 33% Fehlerrate bei Non-Tickets.

---

## Kritische Datenlücken

| Lücke | Ursache | Impact |
|---|---|---|
| OVP-Check komplett ausgefallen (alle 50/50) | Alle OVP-Lookups schlugen fehl (ERR_HTTP2_PROTOCOL_ERROR auf oeticket.com, DNS-Fehler auf szene-wien.com, Navigations-Interruptions auf eventim/myticket/wien-ticket/konzerthaus/stadthalle/gasometer/ticketmaster) | OVP-Werte in parse_cache ausschließlich aus LLM-Extraktion — keine externe Validierung. Verlässlichkeit unklar. |
| Keine externe Datum-Validierung | Kein API-Abgleich mit Veranstaltungskalendern | Parsing-Fehler wie "2024-03-24" statt "2026-03-24" werden nicht erkannt |
| Confidence prüft keine interne Preis-Konsistenz | Prompt/Modell berechnet keine Plausibilität zwischen angebotspreis_gesamt + preis_ist_pro_karte + anzahl_karten | 847435356: confidence=hoch bei 700€/Karte-Fehler |
| 176 raw_cache-Einträge nicht bewertet | max-listings=50 Cap | Keine Aussage über Anomalie-Rate jenseits der ersten 50 Anzeigen |
| Kein Pre-Parse-Non-Ticket-Filter | Architektur-Entscheidung | LLM-Only mit ~33% Fehlerrate bei Non-Tickets |
| Kategorie-Extraktion strukturell unzuverlässig | 90% Unbekannt | Kategorie-basierte Downstream-Auswertung nicht möglich |

---

## Anhang: Top-Anomalien nach Priorität

| willhaben_id | Anomalie | Severity |
|---|---|---|
| 847435356 | preis_ist_pro_karte=True + angebotspreis_gesamt=700 → 700€/Karte (Parsing-Logik-Fehler, confidence=hoch) | CRITICAL |
| 1165795297 | Programmheft als Ticket geparst, kein Non-Ticket-Flag trotz confidence=mittel | HIGH |
| 1825523594 | event_datum=2024-03-24 (2 Jahre falsch, confidence=hoch ohne Warnung) | HIGH |
| 2076375213 | event_datum=2025-11-07 (5 Monate falsch), preis_ist_pro_karte inkonsistent, confidence=hoch | HIGH |
| 1427016553 | Urlaubs-Gutschein im parse_cache, nur mittel-confidence (sollte niedrig/raus) | MEDIUM |
| 1155933700 | OETICKET-Gutschein im parse_cache (korrekt erkannt als niedrig, aber trotzdem gespeichert) | MEDIUM |
| alle 50 | OVP-Check vollständig ausgefallen — alle originalpreis-Werte unvalidiert | MEDIUM |
