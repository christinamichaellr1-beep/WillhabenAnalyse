# ADR-005: launchd statt cron für macOS-Scheduling

**Status:** Accepted
**Datum:** 2026-04-17

**Kontext:** Täglicher automatischer Lauf auf macOS ohne manuellen Start. System startet nach Reboot neu.

**Entscheidung:** launchd-Agent via `~/Library/LaunchAgents/<label>.plist`. GUI bietet Install/Uninstall-Buttons im Zeitplan-Tab. plist via `launchd_manager.generate_plist()` aus Template generiert.

**Begründung:** launchd ist der native macOS-Scheduling-Mechanismus mit Sleep/Wake-Handling und vollem System-Support. cron auf macOS ist deprecated und hat bekannte venv-PATH-Probleme.

**Alternativen erwogen:**
- *cron:* Auf macOS instabil, kein Native venv-Support.
- *Python `schedule`-Daemon:* Läuft nur bei aktivem Prozess, kein Reboot-Recovery.
- *GitHub Actions:* Erfordert Internet-Verbindung, keine lokale Ollama-Nutzung.

**Konsequenzen:**
- (+) Native macOS-Integration, Reboot-resistent
- (+) Logs in `launchd_stdout.log` / `launchd_stderr.log`
- (-) `launchctl load` deprecated ab macOS 13 (HIGH-Finding)
- (-) `OLLAMA_MODELS=/Volumes/...` — SPOF wenn Volume nicht gemountet (HIGH-Finding)
- (-) Template-Injection via `str.format()` in `generate_plist()` (CRITICAL-Finding — `plistlib` verwenden)

**Verwandte ADRs:** ADR-007
