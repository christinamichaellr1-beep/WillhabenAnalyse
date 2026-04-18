# Phase B — Deployment-Verifikation
**Geprüft:** 2026-04-18

---

## A) launchd-Status

| Attribut | Wert |
|---|---|
| Plist-Datei | `~/Library/LaunchAgents/com.willhabenanalyse.pipeline.plist` |
| Installiert | Ja (Datei vorhanden, `-rw-r--r--`, 1347 Bytes, Stand 2026-04-18 07:12) |
| Geladen | Ja (`launchctl list` zeigt `com.willhabenanalyse.pipeline`) |
| Exit-Code laut launchctl | `0` (kein Fehler-Exit beim letzten Run) |
| Disabled-Flag in plist | `<false/>` — Job ist aktiv |
| Trigger | `StartCalendarInterval` → täglich **00:00 Uhr** |
| Letzter gesehener Lauf | 2026-04-18 00:00:01 (launchd_stdout.log) |
| Ergebnis letzter Lauf | 0 Anzeigen gescrapt, Pipeline abgebrochen (korrekt — kein neues Material nach cutoff) |
| stderr-Log | leer (0 Bytes) — keine Fehler |

**Bewertung:** launchd ist korrekt installiert, geladen und läuft täglich um Mitternacht. Der nächtliche Lauf vom 2026-04-18 fand 0 Anzeigen jünger als cutoff — verhält sich erwartungsgemäß mit dem Early-Stop.

---

## B) venv-Integrität

| Attribut | Wert |
|---|---|
| Python-Version | **3.14.4** (Apple Silicon, Homebrew) |
| venv-Pfad | `/Users/Boti/WillhabenAnalyse/.venv/bin/python3` |
| pip-Version | 26.0.1 |
| Status | Alle requirements.txt-Abhängigkeiten installiert und satisfiziert |
| Dry-run-Ergebnis | `Requirement already satisfied` für alle 8 Packages — keine Nachinstallation nötig |

**Auffälligkeit:** Python **3.14** ist eine Pre-Release/Beta-Version (Stand April 2026 noch nicht stabil released). Playwright und pydantic-core kompilieren gegen diese Version — bisher funktional, aber erhöhtes Risiko bei Python-Updates.

---

## C) Dependencies-Audit

| Package | Anforderung (requirements.txt) | Installiert | Status | Anmerkung |
|---|---|---|---|---|
| `playwright` | `>=1.58.0` | `1.58.0` | OK | Exakt Minimum-Version |
| `openpyxl` | `>=3.1.0` | `3.1.5` | OK | Dashboard-Export funktionsfähig |
| `requests` | `>=2.31.0` | `2.33.1` | OK | |
| `schedule` | `>=1.2.0` | `1.2.2` | OK | |
| `ollama` | `>=0.5.0` | `0.6.1` | OK | |
| `pydantic` | `>=2.0.0` | `2.13.2` | OK | |
| `tenacity` | `>=8.2.0` | `9.1.4` | OK | Retry-Logik verfügbar |
| `pandas` | `>=2.0.0` | `3.0.2` | OK | Dashboard-Analyse verfügbar |
| `httpx` | nicht in requirements.txt | `0.28.1` | OK (Transitivabhängigkeit via `ollama`) | Async-HTTP verfügbar |
| `aiohttp` | nicht in requirements.txt | nicht installiert | INFO | Nicht benötigt — httpx übernimmt diese Rolle |
| `numpy` | nicht in requirements.txt | `2.4.4` | OK (Transitivabhängigkeit via pandas) | |
| `pytest` | nicht in requirements.txt | `9.0.3` | OK (Dev-Dependency, nicht prod-kritisch) | Fehlt in requirements.txt |

**Versions-Pinning-Analyse:**
- Alle Packages sind mit `>=`-Grenzen definiert — **keine exakten Pins**.
- Sicherheitsrisiko: Bei `pip install -r requirements.txt` auf einer neuen Maschine könnten neuere, inkompatible Versionen installiert werden.
- `pytest` ist installiert, aber nicht in `requirements.txt` deklariert — unsichtbare Dev-Dependency.
- **Empfehlung:** `pip freeze > requirements.lock` erstellen und für Produktions-Deployments nutzen.

---

## D) Ollama-Verfügbarkeit

| Attribut | Wert |
|---|---|
| Ollama erreichbar | **Ja** — API antwortet auf `http://localhost:11434` |
| Primäres Modell `gemma3:27b` | **Vorhanden** (17.4 GB, Q4_K_M, zuletzt geändert 2026-04-17) |

**Alle verfügbaren Modelle:**

| Modell | Größe | Quantisierung | Zuletzt aktualisiert |
|---|---|---|---|
| `gemma3:27b` | 17.4 GB | Q4_K_M | 2026-04-17 (**Primärmodell**) |
| `gemma4:26b` | 18.0 GB | Q4_K_M | 2026-04-12 |
| `gemma4:latest` | 9.6 GB | Q4_K_M | 2026-04-12 |
| `deepseek-r1:32b` | 19.9 GB | Q4_K_M | 2026-02-15 |
| `qwen2.5-coder:14b` | 9.0 GB | Q4_K_M | 2026-02-15 |
| `mistral-small:22b` | 12.6 GB | Q4_0 | 2026-02-15 |
| `llama3.1:8b` | 4.9 GB | Q4_K_M | 2026-02-15 |

**Auffälligkeit:** `OLLAMA_MODELS` ist in der plist auf `/Volumes/MacMiniMich/KI` gesetzt — ein externes Volume. Wenn dieses Volume nicht gemountet ist, werden Modelle nicht gefunden. Ollama läuft aktuell korrekt, was bedeutet das Volume ist gemountet — aber dies ist ein Single-Point-of-Failure bei Neustart oder Trennung des Volumes.

---

## E) Daten-Verzeichnisse

### `/Users/Boti/WillhabenAnalyse/data/` (3.8 MB gesamt)

| Eintrag | Größe / Anzahl | Letztes Änderungsdatum | Notiz |
|---|---|---|---|
| `ovp_cache.json` | 108 KB | 2026-04-18 09:46 | OVP-Preiscache, aktuell |
| `parse_cache/` | 442 Einträge | 2026-04-15 15:38 | Alter v1-Cache |
| `parse_cache_v2/` | 52 Einträge | 2026-04-18 09:42 | Aktueller v2-Cache |
| `raw_cache/` | 228 Einträge | 2026-04-18 08:33 | HTML-Rohdaten-Cache, aktuell |
| `willhaben_markt.xlsx` | 113 KB | 2026-04-18 09:46 | Ausgabedatei, aktuell |

### `/Users/Boti/WillhabenAnalyse/logs/` (7.9 MB gesamt)

| Datei | Größe | Letztes Datum | Notiz |
|---|---|---|---|
| `pipeline.log` | 4.3 MB | 2026-04-18 09:46 | Haupt-Logdatei, kein Rotation |
| `launchd_stdout.log` | 13 KB | 2026-04-18 00:00 | Cron-Output |
| `launchd_stderr.log` | 0 Bytes | 2026-04-15 00:00 | Kein Fehler-Output |
| `reparse_v2.log` | 526 KB | 2026-04-15 15:51 | Einmalig-Logs |
| `run.log` | 2.2 MB | 2026-04-14 13:28 | Alter Log |
| `test_frisch_50_v2.log` | 273 KB | 2026-04-18 09:46 | Testlauf-Log heute |

**Auffälligkeit:** `pipeline.log` wächst unbegrenzt (4.3 MB, kein Log-Rotation). `parse_cache/` (442 Einträge, v1) ist veraltet und belegt unnötig Speicher.

---

## F) Konfiguration

**Datei:** `/Users/Boti/WillhabenAnalyse/config.json`

| Feld | Wert | Bewertung |
|---|---|---|
| `schedule.scrape_interval_minutes` | 360 | Plausibel (6h), aber ignoriert — launchd läuft nur 1x/Tag |
| `schedule.enabled` | `false` | Konsistent — kein internes Scheduling, launchd übernimmt |
| `ovp_search_urls` | 10 URLs | Plausibel |
| `watchlist[0]` | "Linkin Park Wien 09.06.2026", OVP 89.9€ | Plausibel, OVP-Link leer |
| `max_age_days` | 2 | Plausibel |
| `first_run_max_age_days` | 3 | Plausibel |
| `export_path` | `data/willhaben_markt.xlsx` | **Relativer Pfad** — funktioniert nur wenn WorkingDirectory korrekt gesetzt ist |
| `log_level` | `INFO` | OK |
| `max_listings` | 250 | Konsistent mit Early-Stop-Logik |

**Hardcoded-Pfade-Analyse:**

| Pfad | Wo | Portierbarkeit |
|---|---|---|
| `/Users/Boti/WillhabenAnalyse/` | plist (WorkingDirectory, ProgramArguments, Log-Pfade) | **Nicht portierbar** — absoluter Pfad auf Benutzername "Boti" |
| `/Users/Boti/WillhabenAnalyse/.venv/bin/python3` | plist | **Nicht portierbar** |
| `/Volumes/MacMiniMich/KI` | plist (OLLAMA_MODELS) | **Kritisch** — externes Volume, Single-Point-of-Failure |
| `/Users/Boti/Library/CloudStorage/GoogleDrive-mrieder84@gmail.com/` | im Code (aus pipeline.log sichtbar) | **Nicht portierbar** — hardcoded Google-Account |
| `data/willhaben_markt.xlsx` | config.json | Relativ — OK wenn WorkingDirectory stimmt |

Die plist setzt `WorkingDirectory` korrekt, daher funktionieren relative Pfade. Für einen anderen Benutzer oder eine andere Maschine wäre ein komplettes Redeployment nötig.

---

## G) Letzte Produktionsausführung

### Letzter vollständiger Produktionslauf: 2026-04-18 09:46 (manuell/Testlauf)

```
scraped:        226
parsed_events:   50
ovp_checked:     31
excel_inserted:  43
excel_updated:    7
errors:          []
gdrive_upload:  true
```

### Letzter launchd-Cron-Lauf: 2026-04-18 00:00:01

```
scraped:          0
parsed_events:    0
Grund:            Erste Anzeige älter als cutoff (2026-03-04 < 2026-04-17)
                  → Early-Stop nach 1 Detail-Request
errors:           []
```

### Vorheriger erfolgreicher Cron-Lauf: 2026-04-16 00:00

```
scraped:          1
parsed_events:    1
ovp_checked:      0
excel_inserted:   0
excel_updated:    1
errors:           []
gdrive_upload:    true
```

**Wiederkehrende Warnungen im pipeline.log:**
- `szene-wien.com` → `ERR_NAME_NOT_RESOLVED` (Domain nicht erreichbar)
- `stadthalle.com` → Redirect-Interrupt (Navigation wird umgeleitet)
- `gasometer.at` → `chrome-error://chromewebdata/` (Domain nicht erreichbar)
- `ticketmaster.at` → Interrupt durch gasometer-Redirect

Diese OVP-Fehler werden als WARNING geloggt und führen nicht zum Abbruch — die Pipeline ist korrekt resilient dagegen.

---

## Findings

| ID | Severity | Bereich | Beschreibung | Empfehlung |
|---|---|---|---|---|
| F-B01 | **HIGH** | launchd / Ollama | `OLLAMA_MODELS=/Volumes/MacMiniMich/KI` zeigt auf externes Volume. Wenn das Volume beim nächtlichen Cron-Start nicht gemountet ist, findet Ollama kein Modell — Pipeline schlägt stumm fehl. | `KeepAlive`-Key in plist + Monitoring ob Volume gemountet ist; alternativ Modelle in Standard-Pfad (`~/.ollama/models`) spiegeln |
| F-B02 | **HIGH** | Konfiguration | Alle Versions-Constraints sind `>=`-Minimalversionen ohne obere Grenze. Auf einer frischen Maschine könnte `pip install -r requirements.txt` inkompatible Versionen installieren. | `pip freeze > requirements.lock` erstellen und bei Deployment verwenden |
| F-B03 | **MEDIUM** | Logs | `pipeline.log` hat keine Rotation und wächst unbegrenzt (aktuell 4.3 MB nach ~4 Tagen Betrieb). Projiziert auf 12 Monate: >400 MB. | `logrotate` oder Python `RotatingFileHandler` konfigurieren |
| F-B04 | **MEDIUM** | OVP-Suche | 4 von 10 OVP-URLs schlagen regelmäßig fehl: `szene-wien.com` (DNS-Fehler), `gasometer.at` (offline), `stadthalle.com` (Redirect), `ticketmaster.at` (Folgeschaden von gasometer). 40% der OVP-Quellen sind dysfunktional. | Tote URLs aus `config.json` entfernen; funktionierende Alternativen recherchieren |
| F-B05 | **MEDIUM** | Python-Version | Python **3.14.4** ist eine Pre-Release/Development-Version (kein stabiles Release). Playwright und pydantic-core kompilieren darauf, aber ABI-Stabilität nicht garantiert. | Auf Python 3.12 (LTS) oder 3.13 (stabil) wechseln |
| F-B06 | **LOW** | Daten | `data/parse_cache/` enthält 442 Einträge aus dem v1-Parser (letztes Datum: 2026-04-15). Der v2-Parser verwendet `parse_cache_v2/`. Der v1-Cache ist veraltet und ungenutzt. | `parse_cache/` archivieren oder löschen (~100+ Dateien, Speicher freigeben) |
| F-B07 | **LOW** | Konfiguration | `config.json` enthält `schedule.scrape_interval_minutes: 360` und `schedule.enabled: false`. Das Schedule-Feld hat keine Wirkung — launchd übernimmt das Timing. Die Konfiguration ist irreführend. | Feld entfernen oder in einen Kommentar/README dokumentieren |
| F-B08 | **LOW** | Portierbarkeit | Plist, Google-Drive-Sync-Pfad und andere Pfade sind hart auf Benutzer "Boti" und Account `mrieder84@gmail.com` kodiert. Funktioniert nur auf dieser Maschine. | Akzeptierbar für Single-User-Setup; bei Teamnutzung parametrisieren |
| F-B09 | **INFO** | Ollama | Primärmodell `gemma3:27b` aktuell (2026-04-17 aktualisiert). Zusätzlich 6 Fallback-Modelle vorhanden (`gemma4:26b`, `deepseek-r1:32b`, etc.). Gute Modell-Redundanz. | Fallback-Logik im Code explizit machen |
| F-B10 | **INFO** | Betrieb | Letzter vollständiger Produktionslauf heute 09:46 mit 226 Anzeigen, 50 geparsten Events, 43 neu in Excel, 0 Fehler, Google Drive Upload erfolgreich. System ist produktionsbereit. | — |
| F-B11 | **INFO** | Dependencies | `pytest` installiert aber nicht in `requirements.txt` — unsichtbare Dev-Dependency. `httpx` und `aiohttp`-Äquivalenz durch `httpx 0.28.1` (via ollama) gegeben. | `pytest` in separates `requirements-dev.txt` auslagern |

---

*Audit durchgeführt: 2026-04-18 — WillhabenAnalyse v2.1 Deployment auf macOS (Apple Silicon)*
