# WillhabenAnalyse v2.1 — Audit Design
**Datum:** 2026-04-18  
**Scope:** Produktions-Reife-Bewertung vor erster unbeaufsichtigter Produktion  
**Guardrails:** Kein Code-Change. Kein git push. Nur Read + Report.

---

## Drei Phasen mit GO-Gates

### Phase A — Code-Audit (jetzt)
5 parallele Modul-Agents + 1 Konsolidierungs-Agent → `audit/PHASE_A_CODE_AUDIT.md`

| Agent | Scope |
|-------|-------|
| A1 | `parser/v2/` (extractor, pipeline, postprocessing, preprocessing, prompt, schema, status_writer) |
| A2 | `app/tabs/` (dashboard, engine, status, zeitplan) |
| A3 | `app/backend/` (dashboard_aggregator, launchd_manager, status_monitor, subprocess_runner) |
| A4 | `scraper/willhaben_scraper.py` + `main.py` |
| A5 | `tests/` + CLI-Dimensionen |

Jeder Agent prüft alle **7 Dimensionen** und produziert `audit/findings/phase_a_<layer>.md`:

1. Logik-Fehler (Bugs, Edge-Cases, falsche Annahmen)
2. Dead Code (ungenutzte Importe, tote Branches)
3. Security (Injection, Hardcoded Secrets, Pfad-Traversal)
4. Performance (blocking I/O, Memory, unnecessary loops)
5. Konsistenz (Naming, Style, Pattern-Konsistenz)
6. Testabdeckung (fehlende Tests, schwache Assertions)
7. Maintainability (Komplexität, Duplikation, Kopplung)

Severity-Schema: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `INFO`

**GO-Gate A:** Alle 5 Findings-Dateien vorhanden → Konsolidierung → `PHASE_A_CODE_AUDIT.md`

### Phase B — Integration-Audit (nach GO)
Datenquellen: `logs/test_frisch_50_v2.log` (primär), `data/willhaben_markt.xlsx`, `logs/launchd_stdout.log`
Early-Stop-Bug als CRITICAL Finding dokumentieren.
Output: `audit/PHASE_B_INTEGRATION_AUDIT.md`

### Phase C — Dokumentation (nach GO)
ARCHITECTURE.md, 9 ADRs, API.md, TROUBLESHOOTING.md, ONBOARDING.md, CHANGELOG.md
Output: `docs/` + `docs/adr/`

### Final
`audit/FINAL_AUDIT_REPORT.md` mit Produktions-Reife-Empfehlung.
