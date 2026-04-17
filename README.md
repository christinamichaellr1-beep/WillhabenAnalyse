# WillhabenAnalyse

Automatisches Scraping, Parsing und OVP-Tracking von Konzert-Tickets auf willhaben.at.

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Ollama muss lokal laufen und `gemma3:27b` muss verfügbar sein:

```bash
ollama pull gemma3:27b
```

---

## Pipeline starten

```bash
# Einmaliger Run (Parser v2, Standard)
python main.py --once

# Nur Parsing testen (5 Anzeigen, kein Excel-Write)
python main.py --test-batch 5

# Dry-Run (komplette Pipeline ohne Schreib-Ops)
python main.py --once --dry-run

# Daemon mit Scheduling
python main.py --daemon

# GUI
python main.py --gui
```

---

## Parser v2.0 (seit 2026-04-17)

### Was ist neu

| Feature | v1 | v2 |
|---------|----|----|
| Modell | `gemma4:latest` (8B) | `gemma3:27b` (27B) |
| API | `/api/generate` | `/api/chat` + Structured Output |
| JSON-Parse-Rate | ~85% | **100%** |
| Pre-Filter | keiner | Category-Pages + Non-Tickets |
| Retry-Logik | nein | tenacity (3 Versuche) |
| Fallback-Chain | nein | gemma4:26b → gemma4:latest |
| Latenz Ø | ~25s | ~90s |

### Eval-Ergebnisse (25 Gold-Standard-Einträge)

| Metrik | v2 |
|--------|----|
| JSON-Parse-Rate | 100% |
| Event-Count-Accuracy | 92% (23/25) |
| event_name | 100% |
| originalpreis_pro_karte | 96.7% |
| event_datum | 93.3% |
| anzahl_karten | 90.0% |
| kategorie | 86.7% |
| preis_ist_pro_karte | 80.0% |
| angebotspreis_gesamt | 80.0% |

### Neue CLI-Parameter

| Flag | Beschreibung |
|------|--------------|
| `--parser-version v2` | Parser v2 (Standard seit Phase 5) |
| `--parser-version v1` | Rollback auf Parser v1 |
| `--model gemma3:27b` | Modell-Override (nur v2) |
| `--test-batch N` | N raw_cache-Einträge parsen, kein Excel-Write |
| `--dry-run` | Komplette Pipeline ohne Excel- und Drive-Write |

---

## Rollback auf v1

Falls v2 unerwartetes Verhalten zeigt:

```bash
python main.py --once --parser-version v1
```

v1 (`parser/gemma_parser.py`) und sein Cache (`data/parse_cache/`) bleiben dauerhaft erhalten.

---

## Eval-Suite ausführen

```bash
# v2 mit gemma3:27b evaluieren
.venv/bin/python eval/run_eval.py --parser v2 --model gemma3:27b \
  --output eval/results/v2_gemma3_27b.json

# v1 Baseline
.venv/bin/python eval/run_eval.py --parser v1

# Ergebnis anzeigen
cat eval/results/v2_gemma3_27b.json | python3 -m json.tool | head -40
```

Gold-Standard: 25 hand-verifizierte Anzeigen in `eval/gold_standard.json`
(händler_einfach ×5, privat_einfach ×10, händler_multi ×5, edge_case ×3, non_ticket ×2)

---

## Daten-Verzeichnisse

| Pfad | Inhalt |
|------|--------|
| `data/raw_cache/` | Rohdaten vom Scraper (JSON per ID) |
| `data/parse_cache_v2/` | Parse-Ergebnisse v2 (Cache) |
| `data/parse_cache/` | Parse-Ergebnisse v1 (nicht löschen) |
| `data/willhaben_analyse.xlsx` | Haupt-Ausgabedatei |
