# Parser v2.0 — Design-Spezifikation

**Datum:** 2026-04-17  
**Status:** Genehmigt (Phase 2 abgeschlossen)  
**Scope:** Komplette Neuentwicklung des LLM-Parsers mit Structured Output, Fallback-Chain, Eval-Harness und CLI-Erweiterung.

---

## Kontext & Motivation

### Ausgangslage (v1)
- Modell: `gemma4:latest` (12b) via `/api/generate`
- Kein `format`-Parameter → JSON-Extraktion per Regex-Fallback nötig
- `temperature: 0.1` → minimal stochastisch
- `text[:4000]` Truncation → lange Händler-Tabellen abgeschnitten
- Kein Retry bei Timeout
- Kein Pre-Filter → Category-Pages erzeugen Ollama-Timeouts

### Forensik-Findings (Phase 1)
| Metric | Wert |
|--------|------|
| Confidence=hoch | 72.7% (320/440) |
| Confidence=mittel | 20.2% (89/440) |
| Confidence=niedrig | 7.1% (31/440) |
| Ollama-Fehler | 7 Fälle (Category-Pages + Timeouts) |
| OVP fehlend | 36.4% (160/440) |

### Ziele v2.0
1. **Structured Output** mit `format`-Schema → 0% JSON-Parse-Fehler
2. **Stärkeres Modell** (`gemma3:27b`) → bessere Extraktion komplexer Händler-Anzeigen
3. **Fallback-Chain** → Resilienz bei Modell-Nichtverfügbarkeit
4. **Pre-Filter** → Category-Pages ohne Ollama-Aufruf verwerfen
5. **Retry** → transiente Timeouts automatisch überwinden
6. **Eval-Harness** → objektiver v1/v2 Vergleich vor Default-Switch

---

## Modell-Entscheidung

| Rolle | Modell | Endpunkt | Format |
|-------|--------|----------|--------|
| Primary | `gemma3:27b` | `/api/chat` | JSON-Schema via `format` |
| Fallback | `gemma4:26b` | `/api/generate` | Text-Modus (Thinking-Bug!) |
| Emergency | `gemma4:latest` | `/api/generate` | Text-Modus |

**Warum gemma3:27b als Primary:**  
`gemma4:26b` hat einen bekannten Bug: Mit `format`-Parameter und aktiviertem Thinking-Modus verbraucht der interne Thinking-Block alle `num_predict`-Token; `content` bleibt leer. `gemma3:27b` hat diesen Bug nicht und unterstützt Structured Output zuverlässig.

**Format-Schema-Constraint:**  
Ollama's `format`-Parameter erwartet ein JSON-Schema mit `type: object` auf der obersten Ebene. Arrays als Top-Level werden nicht akzeptiert. Lösung: `ParseResponse(events=[...])` als Wrapper-Objekt.

---

## Modul-Architektur

```
parser/
├── __init__.py              # unverändert
├── gemma_parser.py          # v1 — FROZEN, kein Touch
└── v2/
    ├── __init__.py          # re-exportiert parse_ad, parse_ads
    ├── schema.py            # Pydantic-Modelle + OLLAMA_FORMAT_SCHEMA
    ├── prompt.py            # PROMPT_TEMPLATE + build_prompt()
    ├── preprocessing.py     # is_category_page(), strip_nav(), build_context()
    ├── extractor.py         # Ollama-Aufrufe, Fallback-Chain, Retry
    ├── postprocessing.py    # parse_raw(), validate(), attach_metadata()
    └── pipeline.py          # parse_ad(), parse_ads() — Drop-in für v1
```

### Datenfluss

```
ad: dict
  → preprocessing.is_category_page()          → skip_result wenn True
  → preprocessing.build_context()             → context: str
  → prompt.build_prompt(context)              → prompt: str
  → extractor.extract(prompt, model)          → (raw, model_used, ms, fallback)
  → postprocessing.parse_raw(raw, used_fmt)   → events: list[dict]
  → postprocessing.validate(events)           → list[EventResult]
  → postprocessing.attach_metadata(...)       → list[dict]  (Excel-ready)
```

---

## schema.py

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel

class Confidence(str, Enum):
    hoch    = "hoch"
    mittel  = "mittel"
    niedrig = "niedrig"

class Kategorie(str, Enum):
    stehplatz    = "Stehplatz"
    sitzplatz    = "Sitzplatz"
    vip          = "VIP"
    front        = "Front-of-Stage"
    gemischt     = "Gemischt"
    unbekannt    = "Unbekannt"

class EventResult(BaseModel):
    event_name:              Optional[str]   = None
    event_datum:             Optional[str]   = None   # YYYY-MM-DD oder null
    venue:                   Optional[str]   = None
    stadt:                   Optional[str]   = None
    kategorie:               Kategorie       = Kategorie.unbekannt
    anzahl_karten:           Optional[int]   = None
    angebotspreis_gesamt:    Optional[float] = None
    preis_ist_pro_karte:     Optional[bool]  = None
    originalpreis_pro_karte: Optional[float] = None
    confidence:              Confidence      = Confidence.niedrig
    confidence_grund:        Optional[str]   = None

class ParseResponse(BaseModel):
    events: list[EventResult]

# Wird als format-Parameter an Ollama gesendet
OLLAMA_FORMAT_SCHEMA: dict = ParseResponse.model_json_schema()
```

---

## preprocessing.py

```python
NAV_KEYWORDS = frozenset([
    "zum inhalt", "zu den suchergebnissen", "nachrichten", "einloggen",
    "registrieren", "neue anzeige aufgeben", "marktplatz", "immobilien",
    "auto & motor", "rechtlicher hinweis", "noch mehr ähnliche anzeigen",
])

def is_category_page(ad: dict) -> bool:
    """
    True wenn:
    - Titel matcht r'^\d[\d.,]+ Anzeigen in '
    - ODER text_komplett nach Nav-Strip < 200 Zeichen
    - ODER text_komplett enthält keinen Preis und kein Event-Datum
    """

def strip_nav_prefix(text: str) -> str:
    """
    Entfernt führenden Willhaben-Navigationsblock.
    Startpunkt: erste Zeile mit Preismuster (€, EUR) oder Konzert-Keyword.
    """

def build_context(ad: dict, max_chars: int = 6000) -> str:
    """
    Gibt 'Titel: ...\nPreis: ...\n\nBeschreibung:\n{text[:max_chars]}' zurück.
    text wird vor Truncation durch strip_nav_prefix() gefiltert.
    """
```

**Bug-Fix vs. v1:** `max_chars=6000` (war 4000) + Nav-Strip → effektiv ~2200 Zeichen mehr Nutzinhalt für Händler-Tabellen.

---

## extractor.py

```python
PRIMARY_MODEL   = "gemma3:27b"
FALLBACK_MODEL  = "gemma4:26b"
EMERGENCY_MODEL = "gemma4:latest"
CHAT_URL     = "http://localhost:11434/api/chat"
GENERATE_URL = "http://localhost:11434/api/generate"
TIMEOUT      = 240   # Sekunden

RETRY_POLICY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=3, max=30),
    reraise=True,
)

@RETRY_POLICY
def _call_chat(prompt: str, model: str, use_format: bool) -> tuple[str, int]:
    """POST /api/chat. use_format=True: sendet OLLAMA_FORMAT_SCHEMA."""

@RETRY_POLICY
def _call_generate(prompt: str, model: str) -> tuple[str, int]:
    """POST /api/generate — Text-Modus für Fallback-Modelle."""

def extract(
    prompt: str,
    model_override: str | None = None,
) -> tuple[str, str, int, bool]:
    """
    Fallback-Chain:
      1. PRIMARY_MODEL  via /api/chat + format  (gemma3:27b)
      2. FALLBACK_MODEL via /api/generate        (gemma4:26b)
      3. EMERGENCY_MODEL via /api/generate       (gemma4:latest)

    Gibt (raw_response, model_used, duration_ms, fallback_used) zurück.
    model_override: überspringt Fallback-Chain.
    """
```

---

## postprocessing.py

```python
EMPTY_EVENT: dict  # identisch mit v1 (Rückwärtskompatibilität)

def parse_raw(raw: str, used_format_schema: bool) -> list[dict]:
    """
    used_format_schema=True  → json.loads(raw)["events"]  (Grammar-guaranteed)
    used_format_schema=False → Regex-Fallback-Kette (identisch v1 _extract_json_array)
    Gibt immer liste[dict] zurück, min. 1 Element (EMPTY_EVENT als Fallback).
    """

def validate(raw_events: list[dict]) -> list[EventResult]:
    """
    Pydantic-Validierung: ungültige Felder → Default-Werte (kein Crash).
    Identische Typen-Normalisierung wie v1 _validate_event().
    """

def attach_metadata(
    events: list[EventResult],
    ad: dict,
    model_used: str,
    duration_ms: int,
    fallback_used: bool,
) -> list[dict]:
    """
    Konvertiert EventResult → dict.
    Hängt an: willhaben_id, willhaben_link, verkäufer*,
              preis_roh, parsed_at, modell, pipeline_version="v2.0",
              parse_dauer_ms, confidence_grund (jetzt auch in Hauptübersicht).
    """
```

---

## pipeline.py

```python
PARSE_CACHE_DIR = BASE_DIR / "data" / "parse_cache_v2"   # separates Dir!

def parse_ad(
    ad: dict,
    model: str | None = None,
    use_cache: bool = True,
) -> list[dict]:
    """Drop-in-Ersatz für v1 parse_ad(). Gibt v1-kompatibles Schema zurück."""

def parse_ads(
    ads: list[dict],
    use_cache: bool = True,
    model: str | None = None,
) -> list[dict]:
    """Drop-in-Ersatz für v1 parse_ads(). Gleiche Logging-Ausgaben."""
```

**Cache-Verzeichnis:** `parse_cache_v2/` statt `parse_cache/` — verhindert Schema-Konflikt zwischen v1 (ohne `modell`-Feld) und v2.

---

## CLI-Erweiterung (main.py)

### Neue Flags

| Flag | Typ | Default | Beschreibung |
|------|-----|---------|--------------|
| `--model` | choice | None | Modell-Override (überspringt Fallback-Chain) |
| `--parser-version` | choice | `v1` | v1 bleibt Default bis Eval GO |
| `--test-batch N` | int | — | N raw_cache-Einträge parsen, kein Excel-Write |
| `--dry-run` | bool | False | Komplette Pipeline ohne Schreib-Ops |

### run_pipeline() Erweiterung

```python
def run_pipeline(
    log_callback=None,
    parser_version: str = "v1",
    model_override: str | None = None,
    dry_run: bool = False,
) -> dict:
```

---

## Excel-Schema-Erweiterung (excel_writer.py)

```python
MAIN_COLUMNS: list[tuple[str, str]] = [
    # ... bestehende 24 Spalten unverändert ...
    ("confidence_grund",  "Confidence-Grund"),    # NEU — Spalte 25
    ("modell",            "Modell"),              # NEU — Spalte 26
    ("pipeline_version",  "Pipeline-Version"),    # NEU — Spalte 27
    ("parse_dauer_ms",    "Parse-Dauer ms"),      # NEU — Spalte 28
]
```

Bestehende Zeilen (v1-Daten): neue Spalten leer — vollständig backward-kompatibel.

---

## Eval-Harness

### Verzeichnis-Layout

```
eval/
├── gold_standard.json    # 25 hand-verifizierte Einträge
├── run_eval.py           # Eval-Skript
└── results/
    └── YYYY-MM-DD.json   # Eval-Ergebnisse pro Run
```

### Gold-Standard-Kategorien (je 5 Einträge)

| Kategorie | Beschreibung |
|-----------|--------------|
| Privat einfach | OVP klar, 1-2 Karten, confidence=hoch erwartet |
| Privat Datum fehlt | confidence=mittel erwartet |
| Händler 2 Kategorien | genau 2 Event-Objekte erwartet |
| Händler 3+ Kategorien | 3+ Objekte erwartet |
| OVP im Titel / Non-Ticket | OVP-Extraktion oder confidence=niedrig |

### Metriken & Ziele

| Metrik | Ziel v2 | v1 Baseline |
|--------|---------|-------------|
| JSON-Parse-Rate | ≥ 99% | ~98% |
| Event-Count-Accuracy | ≥ 92% | ~88% |
| Field-Acc: event_name | ≥ 95% | ~90% |
| Field-Acc: event_datum | ≥ 90% | ~85% |
| Field-Acc: originalpreis_pro_karte (±1€) | ≥ 85% | ~80% |
| Confidence-Calibration | ≥ 90% | ~87% |
| Ø Latenz pro Anzeige | ≤ 60s | ~25s |

---

## Risiko-Assessment

| # | Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|---|--------|--------------------|--------|------------|
| R1 | gemma3:27b format-Bug analog gemma4:26b | Mittel | Hoch | Smoke-Test direkt nach Download; Fallback-Chain greift automatisch |
| R2 | Ollama format kein top-level Array | Hoch (bekannt) | Mittel | Mitigiert: ParseResponse-Wrapper |
| R3 | parse_cache_v2 leer → erster Lauf langsam | Sicher | Niedrig | Separates Dir, kein Konflikt; ~440 × 30s einmalig |
| R4 | PEP 668 → pip geblockt | Sicher | Hoch | Phase 3: venv erstellen |
| R5 | Händler-Texte > 6000 Zeichen | Niedrig | Mittel | Monitoring via parse_dauer_ms; bei Bedarf max_chars=8000 |

---

## Rollout-Strategie

```
Phase 3: Code schreiben (parser/v2/ alle Module + venv)
   ↓
Phase 4: Unit Tests + Smoke-Test (5 raw_cache-Einträge)
   ↓  (gemma3:27b Download muss fertig sein)
Phase 5: Eval-Harness
   ├── Gold-Standard 25 Einträge manuell kuratieren
   ├── run_eval.py v1 → Baseline
   └── run_eval.py v2 → Decision Gate
   ↓  (alle Metriken erfüllt, 0 Regressionen)
GO: Default-Switch
   ├── main.py: --parser-version default → "v2"
   ├── excel_writer.py: neue Spalten aktiviert
   └── README: venv-Setup + Migration-Notiz
```

### Decision Gate (vor Default-Switch)

| Kriterium | Minimum |
|-----------|---------|
| JSON-Parse-Rate | ≥ 99% |
| Event-Count-Accuracy | ≥ 92% |
| Latenz Ø | ≤ 60s/Anzeige |
| Regressionen v1→v2 (hoch-Einträge) | 0 |

### Parallel-Betrieb (bis Switch)

- `parser/gemma_parser.py` → nie löschen
- `data/parse_cache/` → nie löschen  
- `--parser-version v1` → bleibt dauerhaft funktionsfähig

---

## Dependencies

```
# requirements.txt — Additionen für v2.0
ollama>=0.5.0
pydantic>=2.0.0
tenacity>=8.2.0
```

**Setup:** venv erforderlich (PEP 668 blockiert system-pip auf macOS).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
