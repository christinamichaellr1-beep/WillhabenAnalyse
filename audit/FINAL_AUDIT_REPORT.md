# WillhabenAnalyse v2.1 — Finaler Audit-Report

**Datum:** 2026-04-18
**Auditor:** Claude Sonnet 4.6 (automatisiert, 5+4+4 parallele Agents)
**Codebase:** 3.042 Zeilen Produktionscode, 143 Tests, 17 Test-Dateien
**Testlauf-Basis:** `logs/test_frisch_50_v2.log` (50 Events, 09:46 Uhr, 0 Fehler)

---

## Executive Summary

WillhabenAnalyse v2.1 ist **technisch funktionsfähig aber nicht produktionsreif** für unbeaufsichtigten Dauerbetrieb. Die Pipeline scrapt, parst und schreibt Daten korrekt — der heutige Lauf (09:46) verarbeitete 226 Anzeigen, extrahierte 50 Events, schrieb 43 neu in Excel und lud auf Google Drive hoch, alles ohne Fehler. Die 143 Unit-Tests sind grün.

Jedoch wurden im Audit **10 CRITICAL Findings** identifiziert, darunter 3 Security-Lücken (Prompt-Injection, Template-Injection in launchd, Command-Injection via config.json), eine dauerhaft in der Git-History gespeicherte PII, und 2 strukturelle Defekte die Core-Features vollständig brechen: Das Dashboard-Tab zeigt seit Tag 1 leere Daten (falscher Excel-Sheet-Name), und der GUI-Status zeigt immer "Fehler: 0" (Feldname-Mismatch). Die Gesamt-Finding-Zahl beträgt **142** across Phase A und B.

**Empfehlung:** Ein "Phase A Hardening Sprint" von ~3–5 Tagen behebt alle CRITICAL Findings. Danach ist das System für Produktionsbetrieb geeignet.

---

## Findings-Gesamtübersicht

| Severity | Phase A (Code) | Phase B (Integration) | Gesamt |
|---|---|---|---|
| **CRITICAL** | 6 | 4 | **10** |
| **HIGH** | 23 | 7 | **30** |
| **MEDIUM** | 35 | 10 | **45** |
| **LOW** | 27 | 8 | **35** |
| **INFO** | 18 | 4 | **22** |
| **Total** | **109** | **33** | **142** |

---

## CRITICAL Findings (Produktion-Blocker)

### C01 — Prompt-Injection via rohem Anzeigentext
**Layer:** parser/v2/prompt.py, preprocessing.py
**Impact:** Anzeigentext wird ungefiltert in LLM-Prompt eingebettet. Ein Verkäufer kann den Parser manipulieren ("Ignoriere alle bisherigen Anweisungen und antworte mit...").
**Fix:** Anzeigentext vor Einbettung sanitieren; Maximallänge und verbotene Prompt-Marker (z.B. "Ignoriere", "System:") filtern.
**Aufwand:** M

### C02 — Template-Injection in plist-Generierung → macOS Code-Execution
**Layer:** app/backend/launchd_manager.py
**Impact:** `generate_plist()` nutzt `str.format()` mit unvalidierten GUI-Werten. Ein manipuliertes `label`-Feld kann beliebige Befehle in den launchd-Job einschleusen.
**Fix:** `plistlib`-Modul statt String-Template verwenden.
**Aufwand:** S

### C03 — Command-Injection via model-String
**Layer:** app/tabs/engine.py, app/tabs/zeitplan.py
**Impact:** `model`- und `parser_version`-Strings aus config.json werden ohne Allowlist-Validierung als CLI-Argumente übergeben. Eine manipulierte config.json ermöglicht Command-Injection.
**Fix:** Allowlist-Validierung: `model in {"gemma3:27b", "gemma4:26b", "gemma4:latest"}`.
**Aufwand:** XS

### C04 — PII dauerhaft in Git-History
**Layer:** scraper/willhaben_tracker_original.py, old_tracker.py
**Impact:** Personenbezogene Daten (E-Mail-Adresse) als Hardcoded Default in beiden Dateien — dauerhaft in der Git-History. Ein normales Commit entfernt sie nicht.
**Fix:** `git filter-repo` oder BFG Repo-Cleaner. Dateien danach löschen (Dead Code, byte-identisch).
**Aufwand:** M

### C05 — `errors` vs. `errors_count` Feldname-Mismatch
**Layer:** parser/v2/status_writer.py ↔ app/tabs/status.py
**Impact:** StatusWriter schreibt `"errors_count"`, StatusTab liest `"errors"` → GUI zeigt seit Tag 1 immer "Fehler: 0". Unit-Tests maskieren den Bug durch hardcodierte Test-Dicts.
**Fix:** StatusTab auf `status.get("errors_count", 0)` umstellen.
**Aufwand:** XS

### C06 — Falsch-positiver Test für max_listings
**Layer:** tests/test_backend_subprocess_runner.py
**Impact:** `test_start_pipeline_with_max_listings_adds_arg` testet einen manuell erstellten zweiten Subprocess, nicht die Ausgabe von `start_pipeline()`. Der Test ist grün auch wenn `start_pipeline` `--max-listings` komplett ignoriert.
**Fix:** `proc.args` prüfen statt zweiten Subprocess spawnen.
**Aufwand:** XS

### C07 — Fehlender echter 350-Anzeigen-Testlauf
**Layer:** CI/Testing
**Impact:** `logs/testlauf_v21_350.log` enthält 0 geparste Anzeigen (sort=5 → Cutoff nach 1. Anzeige). Es gibt keinen verifizierten Nachweis dass die Pipeline mit 350 Anzeigen korrekt läuft.
**Fix:** Testlauf mit `sort=3` (neueste zuerst) und `--max-listings=350` wiederholen.
**Aufwand:** S (Laufzeit ~8h)

### C08 — Dashboard liest falschen Excel-Sheet
**Layer:** app/backend/dashboard_aggregator.py:25
**Impact:** `load_excel()` öffnet Sheet `"Angebote"` — existiert nicht. Stille Exception → leeres DataFrame. Dashboard-Tab zeigt seit Tag 1 keine Daten.
**Fix:** `sheet_name="Angebote"` → `sheet_name="Hauptübersicht"`.
**Aufwand:** XS

### C09 — Spalten-Namen-Mismatch Aggregator vs. Excel
**Layer:** app/backend/dashboard_aggregator.py
**Impact:** Aggregator erwartet snake_case (`anbieter_typ`, `event_name`, etc.), Excel hat Deutsche Display-Namen (`Verkäufertyp`, `Event-Name`, etc.). Selbst nach C08-Fix: leeres Dashboard.
**Fix:** `load_excel()` normalisiert Spalten via `rename()`-Mapping nach dem Lesen.
**Aufwand:** S

### C10 — `preis_ist_pro_karte`-Flag inkonsistent
**Layer:** parser/v2 (Ollama-Output)
**Impact:** Anzeige mit Gesamtpreis 700€ für 7 Tickets bekommt `preis_ist_pro_karte=True` → Dashboard berechnet 700€/Karte. Confidence=hoch ohne Warnung.
**Fix:** Postprocessing-Plausibilitätsprüfung: wenn `angebotspreis_gesamt / anzahl_karten` > `angebotspreis_gesamt` → Flag-Inkonsistenz loggen, confidence auf "niedrig" setzen.
**Aufwand:** M

---

## TOP-10 Empfehlungen nach ROI (Impact / Aufwand)

| Priorität | Finding | Aufwand | Impact |
|---|---|---|---|
| 1 | C05: errors_count Feldname-Fix | XS | Dashboard-Status korrekt |
| 2 | C08: Sheet-Name "Hauptübersicht" | XS | Dashboard funktionsfähig |
| 3 | C09: Spalten-Mapping in load_excel | S | Dashboard zeigt echte Daten |
| 4 | C03: Allowlist für model/parser_version | XS | Command-Injection verhindert |
| 5 | C06: Falsch-positiver Test fixen | XS | Testaussage korrekt |
| 6 | C02: plistlib statt str.format | S | Template-Injection verhindert |
| 7 | C07: 350er-Testlauf wiederholen | S | Produktions-Nachweis vorhanden |
| 8 | C04: PII aus Git-History entfernen | M | Compliance |
| 9 | C01: Prompt-Sanitierung | M | Security |
| 10 | C10: preis_ist_pro_karte Plausibilitätsprüfung | M | Datenqualität |

---

## Regression-Check: 5 ursprüngliche v2.1 Fehlerfälle

| Fehlerfall | Status | Evidenz |
|---|---|---|
| FC1: JSON-Parse-Fehler Ollama | ✅ Strukturell adressiert | v2 Structured Output → 100% Parse-Rate |
| FC2: StatusWriter fail() bei Abbruch | ✅ Behoben | `pipeline.py:71–104` try/except + writer.fail() + raise |
| FC3: Concurrent-Spawn-Guard | ✅ Behoben (mit Einschränkung) | Guard in engine.py:132 + status.py:149; kein tabs-übergreifender Schutz |
| FC4: ValueError bei leerem GUI-Input | ✅ Behoben | `engine.py:162–167` try/except + messagebox |
| FC5: after_cancel bei Fenster-Destroy | ✅ Behoben | `status.py:166–170` destroy()-Override |

---

## Deployment-Status

| Komponente | Status | Anmerkung |
|---|---|---|
| launchd-Job | ✅ Aktiv | com.willhaben.analyse, täglich 00:00 |
| venv / Python 3.14 | ✅ OK | Alle 8 Packages installiert; Python 3.14 noch Pre-Release |
| Ollama + gemma3:27b | ✅ Verfügbar | Localhost:11434, + 6 Fallback-Modelle |
| Google Drive Upload | ✅ Heute erfolgreich | Letzter Run 09:46, 43 neue Zeilen |
| Log-Rotation | ⚠️ Fehlt | pipeline.log: 4,3 MB nach 4 Tagen → ~400 MB/Jahr |
| Ollama-Volume | ⚠️ SPOF | /Volumes/MacMiniMich/KI — schlägt fehl wenn nicht gemountet |

---

## Performance-Profil

| Metrik | Wert |
|---|---|
| Parse-Dauer Ø (gemma3:27b) | ~83 Sekunden/Anzeige |
| Testlauf heute | 50 Anzeigen → ~69 Minuten gesamt |
| Hochrechnung 250 Anzeigen (config-Default) | ~5,8 Stunden |
| Hochrechnung 350 Anzeigen | ~8,1 Stunden |
| OVP-Check-Erfolgsrate | 0% (alle 50 Lookups fehlgeschlagen — oeticket HTTP/2-Fehler) |

**Empfehlung:** `max_listings` auf 150–200 begrenzen bis OVP-Check repariert ist.

---

## Phase C — Dokumentations-Status

| Dokument | Status | Pfad |
|---|---|---|
| ARCHITECTURE.md | ✅ Erstellt | `docs/ARCHITECTURE.md` |
| ADR-001 bis ADR-009 | ✅ Erstellt (9 Dateien) | `docs/adr/001-009-*.md` |
| API.md | ✅ Erstellt | `docs/API.md` |
| TROUBLESHOOTING.md | ✅ Erstellt | `docs/TROUBLESHOOTING.md` |
| ONBOARDING.md | ✅ Erstellt | `docs/ONBOARDING.md` |
| CHANGELOG.md | ✅ Erstellt | `docs/CHANGELOG.md` |

---

## Produktions-Reife-Bewertung

```
KRITERIUM                          STATUS    ANMERKUNG
─────────────────────────────────────────────────────────────────
Core-Pipeline (scrape→parse→excel) ✅ GRÜN   Heute erfolgreich, 0 Fehler
Unit-Tests                         ✅ GRÜN   143/143 grün
Scheduling (launchd)               ✅ GRÜN   Täglich aktiv
GUI Grundfunktionen                ⚠️ GELB   3 Tabs funktionieren, Dashboard leer
Dashboard-Tab                      🔴 ROT    Seit Tag 1 leer (C08+C09)
Status-Fehleranzeige               🔴 ROT    Immer "0" wegen C05
Security                           🔴 ROT    3 Injection-Lücken (C01–C03)
PII-Compliance                     🔴 ROT    E-Mail in Git-History (C04)
OVP-Check                          🔴 ROT    100% Fehlerquote
Testabdeckung                      ⚠️ GELB   Scraper, OVP, gdrive ungetestet
Dokumentation                      ✅ GRÜN   Vollständig (Phase C)
```

### Gesamturteil: **NICHT PRODUKTIONSREIF** (für unbeaufsichtigten Dauerbetrieb)

**Bedingtes GO nach "Hardening Sprint" (~3–5 Tage):**

| Schritt | Findings | Aufwand |
|---|---|---|
| Sprint-Tag 1 | C05, C08, C09, C03, C06 (XS+S) | ~4h |
| Sprint-Tag 2 | C02, C07 (plistlib + Testlauf) | ~1 Tag + 8h Wartezeit |
| Sprint-Tag 3 | C04 (git filter-repo), C10 | ~4h |
| Sprint-Tag 4 | C01 (Prompt-Sanitierung) + HIGH-Findings | ~1 Tag |
| Sprint-Tag 5 | Verifikations-Testlauf + Review | ~1 Tag |

Nach diesem Sprint: **GO für Produktionsbetrieb**.

---

## Audit-Artefakte

```
audit/
├── PHASE_A_CODE_AUDIT.md          (109 Findings, 5 Modul-Layers)
├── PHASE_B_INTEGRATION_AUDIT.md   (33 Findings, 4 Bereiche)
├── FINAL_AUDIT_REPORT.md          (dieses Dokument)
└── findings/
    ├── phase_a_parser_v2.md
    ├── phase_a_app_tabs.md
    ├── phase_a_app_backend.md
    ├── phase_a_scraper_main.md
    ├── phase_a_tests.md
    ├── phase_b_regression.md
    ├── phase_b_anomalies.md
    ├── phase_b_dashboard.md
    └── phase_b_deployment.md

docs/
├── ARCHITECTURE.md
├── API.md
├── TROUBLESHOOTING.md
├── ONBOARDING.md
├── CHANGELOG.md
└── adr/
    ├── 001-modell-wahl.md
    ├── 002-structured-output.md
    ├── 003-fallback-chain.md
    ├── 004-status-writer.md
    ├── 005-launchd.md
    ├── 006-parser-koexistenz.md
    ├── 007-tkinter-gui.md
    ├── 008-excel-datenspeicher.md
    └── 009-parse-cache.md
```
