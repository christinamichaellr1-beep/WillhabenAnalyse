# ADR-009: Dateibasierter JSON Parse-Cache

**Status:** Accepted
**Datum:** 2026-04-15

**Kontext:** Ein Ollama-Call mit gemma3:27b dauert ~83 Sekunden. Bei 250 Anzeigen wären das ~5,5 Stunden. Bereits geparste Anzeigen dürfen nicht erneut geparst werden.

**Entscheidung:** `data/parse_cache_v2/<willhaben_id>.json` speichert das Parse-Ergebnis. Cache-Hit in `pipeline.py` überspringt Preprocessing + Ollama-Call vollständig. Kein automatisches TTL.

**Begründung:** Einfachste mögliche Lösung. Eine Datei pro Anzeigen-ID ist leicht zu debuggen (direkt lesbar), leicht zu invalidieren (Datei löschen) und braucht keine Datenbank.

**Alternativen erwogen:**
- *SQLite-Cache:* Robuster für große Datenmengen, aber Overkill für ~500 Einträge.
- *In-Memory-Cache:* Überlebt keinen Prozess-Neustart.
- *Kein Cache:* Bei 250 Anzeigen = 5,5h Laufzeit täglich — nicht akzeptabel.

**Konsequenzen:**
- (+) Drastische Laufzeit-Reduktion bei Folge-Runs
- (+) Einzelne Einträge einfach invalidierbar
- (+) Direkt lesbar für Debugging
- (-) `_load_cache()` hat stilles Exception-Handling — korrupte Cache-Dateien werden ignoriert statt gemeldet (HIGH-Finding)
- (-) Kein TTL: veraltete Preise bleiben im Cache bis manuell gelöscht
- (-) `use_cache`-Parameter in `parse_ad()` ist Dead Code (MEDIUM-Finding)

**Verwandte ADRs:** ADR-006, ADR-008
