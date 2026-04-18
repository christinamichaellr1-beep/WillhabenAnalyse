# ADR-008: Excel als primärer Datenspeicher

**Status:** Accepted
**Datum:** 2026-04-14

**Kontext:** Zielgruppe will Daten direkt analysieren ohne zusätzliche Tools. Marktübersicht, Filterung und Export sollen in einem bekannten Format verfügbar sein.

**Entscheidung:** openpyxl-basierter Upsert in `.xlsx` mit 4 Sheets (Hauptübersicht, Review Queue, Archiv, Watchlist-Config). Primärschlüssel: `willhaben_id`.

**Begründung:** Excel ist für die Zielgruppe unmittelbar nutzbar. Kein DB-Setup nötig. `openpyxl` ist leichtgewichtig und gut dokumentiert.

**Alternativen erwogen:**
- *SQLite:* Robuster für Concurrent-Writes, aber erfordert separates Analyse-Tool.
- *PostgreSQL:* Overkill für Einzel-User-Desktop-App.
- *CSV:* Kein Multi-Sheet, keine Formatierung.

**Konsequenzen:**
- (+) Zielgruppe kann Daten sofort in Excel öffnen und analysieren
- (+) Kein DB-Setup
- (-) Kein Concurrent-Write-Schutz
- (-) Dashboard-Aggregator erwartet Sheet "Angebote", existiert nicht (CRITICAL-Finding)
- (-) Spalten-Namen-Mismatch zwischen Aggregator (snake_case) und Excel (Deutsche Display-Namen) (CRITICAL-Finding)
- (-) Unnamed-Spalten für v2-Metadaten bei Append an bestehende Datei (HIGH-Finding)

**Verwandte ADRs:** ADR-009
