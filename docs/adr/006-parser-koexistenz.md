# ADR-006: Parser v1/v2 Koexistenz

**Status:** Accepted
**Datum:** 2026-04-15

**Kontext:** Parser v2 (gemma3:27b) ist 3,5× langsamer als v1 (90s vs 25s). Bei Einführung war unklar ob alle Edge-Cases korrekt behandelt werden. Hard-Cutover wäre riskant.

**Entscheidung:** Beide Parser aktiv. `--parser-version v1|v2` CLI-Flag und GUI-Dropdown. Separate Cache-Verzeichnisse (`parse_cache/` vs `parse_cache_v2/`).

**Begründung:** Rollback-Fähigkeit wichtiger als Code-Sauberkeit. Aufwand gering (ein `if`-Branch in `main._select_parse_ads()`).

**Alternativen erwogen:**
- *v1 löschen:* Kein Rollback bei Regression.
- *Feature-Flag in config.json:* Weniger transparent als CLI-Flag.
- *Getrennte Branches:* Branch-Wechsel zu langsam im Incident.

**Konsequenzen:**
- (+) Sofortiger Rollback: `python main.py --once --parser-version v1`
- (+) A/B-Vergleich möglich
- (-) `parser/gemma_parser.py` (16 KB) hat null Unit-Tests (HIGH-Finding)
- (-) Erhöhte Maintenance-Last durch zwei parallele Parser

**Verwandte ADRs:** ADR-001, ADR-009
