# ADR-004: Atomarer JSON-Heartbeat via StatusWriter

**Status:** Accepted
**Datum:** 2026-04-17

**Kontext:** Die GUI braucht Live-Fortschrittsinformationen über einen Parse-Subprocess. Direkter Speicher-Zugriff über Prozessgrenzen ist nicht möglich. Stdout-Lines sind zu unstrukturiert.

**Entscheidung:** `parser/v2/status_writer.py` schreibt `.willhaben_status.json` atomar (tmp → rename). Die GUI pollt alle 2s via `status_monitor.read_status()`.

**Begründung:** Datei-basierte IPC: kein zusätzlicher Infrastruktur-Dependency, von jedem Tool lesbar (`cat .willhaben_status.json`), zuverlässig auf macOS.

**Alternativen erwogen:**
- *SQLite:* Overkill für einen einzelnen Status-Datensatz; Write-Lock-Komplexität.
- *multiprocessing.Queue:* Funktioniert nicht über `subprocess.Popen`-Grenzen.
- *Redis:* Externe Abhängigkeit unakzeptabel für Desktop-Tool.

**Konsequenzen:**
- (+) Kein zusätzliches Dependency
- (+) Atomar, korruptionsresistent
- (-) 2s-Polling-Latenz
- (-) `errors_count` vs `errors` Feldname-Mismatch — GUI zeigt immer "Fehler: 0" (CRITICAL-Finding aus Audit)

**Verwandte ADRs:** ADR-006
