# ADR-003: Dreistufige Fallback-Chain

**Status:** Accepted
**Datum:** 2026-04-15

**Kontext:** Der primäre Parser nutzt gemma3:27b — 26 GB RAM. Bei RAM-Engpass oder nach Reboot kann das Modell nicht geladen werden. Ein Pipeline-Abbruch ist im unbeaufsichtigten Nachtlauf nicht akzeptabel.

**Entscheidung:** Dreistufige Fallback-Chain in `extractor.py`:
1. **Primary:** gemma3:27b via `/api/chat` + Structured Output
2. **Fallback:** gemma4:26b via `/api/generate` (Text-Mode)
3. **Emergency:** gemma4:latest via `/api/generate` (kleinstes Modell)

Bei Totalausfall: leerer String, `confidence="niedrig"`.

**Begründung:** Resilienz vor Konsistenz. Ein Ergebnis niedrigerer Qualität ist besser als kein Ergebnis. `fallback_used`-Flag und `modell`-Feld machen die genutzte Stufe transparent.

**Alternativen erwogen:**
- *Fehler werfen bei Primary-Ausfall:* Kein unbeaufsichtigter Betrieb möglich.
- *Retry mit gleichem Modell:* Adressiert Transient-Fehler (bereits durch tenacity abgedeckt), nicht strukturelle RAM-Probleme.

**Konsequenzen:**
- (+) Pipeline läuft durch bei Modell-Unavailability
- (+) Fallback-Status im Cache und Excel sichtbar
- (-) Qualität variiert je nach Stufe
- (-) `fallback_used`-Semantik aktuell fehlerhaft (HIGH-Finding): Flag=True bei jeder Exception, nicht nur bei echtem Fallback

**Verwandte ADRs:** ADR-001, ADR-002
