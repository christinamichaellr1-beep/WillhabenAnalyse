# ADR-002: Ollama Structured Output statt Freitext-JSON-Parsing

**Status:** Accepted
**Datum:** 2026-04-17

## Kontext

Parser v1 schickte einen Prompt an `/api/generate` und versuchte anschließend, den Freitext-Response via `json.loads()` zu parsen. Ollama-Modelle gaben dabei häufig JSON aus, das syntaktisch fehlerhaft war: fehlende schließende Klammern, JavaScript-style Kommentare (`// …`) im JSON-Body, `None` statt `null`, doppelte Schlüssel oder abgeschnittene Ausgaben bei langen Anzeigen. Das führte zu einer Parse-Rate von ~85 %.

Für v2.0 sollte die Fehlerquelle strukturell eliminiert werden — nicht durch besseres Post-Processing, sondern durch eine Garantie auf Modell-Ebene.

## Entscheidung

Der primäre Modell-Aufruf erfolgt via `POST /api/chat` mit dem `format`-Parameter. Als Wert wird das JSON-Schema übergeben, das Pydantic aus `ParseResponse.model_json_schema()` ableitet. Ollama erzwingt daraufhin, dass der generierte Token-Stream dem Schema entspricht (Constrained Decoding). Die Antwort wird direkt via `ParseResponse.model_validate_json(content)` deserialisiert.

```python
# parser/v2/schema.py
class ParseResponse(BaseModel):
    events: list[EventResult]

OLLAMA_FORMAT_SCHEMA: dict = ParseResponse.model_json_schema()

# parser/v2/extractor.py — _call_chat()
requests.post(CHAT_URL, json={
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "format": OLLAMA_FORMAT_SCHEMA,
    ...
})
```

## Begründung

Ollamas Constrained Decoding auf Basis eines JSON-Schemas ist die einzige Methode, die JSON-Korrektheit als harte Garantie und nicht als Wahrscheinlichkeit behandelt. Das Schema (`ParseResponse`) ist identisch mit dem Pydantic-Modell, das ohnehin für die Typ-Validierung benötigt wird — es entsteht keine Redundanz. Der Mechanismus ist Teil der stabilen Ollama-API und nicht modellspezifisch.

Der `format`-Parameter funktioniert mit `/api/chat`, nicht mit `/api/generate`. Da das primäre Modell `gemma3:27b` den Chat-Endpunkt unterstützt, ist dies kein Einschränkungsfaktor. Fallback-Modelle (ADR-003) nutzen weiterhin `/api/generate` im Text-Modus, da `gemma4:26b` einen bekannten Thinking-Bug beim `format`-Parameter zeigt.

## Alternativen erwogen

| Alternative | Verworfen, weil |
|-------------|-----------------|
| **Regex-Extraktion** | Unzuverlässig bei geschachteltem JSON, mehrzeiligen Strings und Edge Cases; Wartungsaufwand hoch |
| **json-repair Library** | Behandelt Symptome statt Ursache; nicht alle Fehlerklassen abgedeckt; externe Abhängigkeit |
| **Strikte Prompt-Anweisung** | "Antworte nur mit validem JSON" verbessert Rate, garantiert sie aber nicht; bei 8B-Modellen ineffektiv |
| **Zwei-Schritt-Ansatz (erst Text, dann Format)** | Doppelte Latenz; komplexere Fehlerbehandlung; kein wesentlicher Genauigkeitsgewinn |

## Konsequenzen

**Positiv:**
- JSON-Parse-Rate 100 % — `json.loads()` kann nie mehr scheitern, solange Ollama antwortet
- Pydantic-Validierung direkt anwendbar — Typ-Fehler (z. B. `str` statt `float`) werden explizit gemeldet
- Kein Post-Processing-Code für JSON-Reparatur nötig
- Schema dient gleichzeitig als Dokumentation des Datenmodells

**Negativ:**
- `/api/chat`-Endpunkt erforderlich — Fallback-Modelle ohne Chat-Support können Structured Output nicht nutzen (sie fallen auf Freitext-Modus zurück, ADR-003)
- `gemma4:26b` zeigt Thinking-Bug mit `format`-Parameter → Fallback muss explizit `/api/generate` nutzen
- Constrained Decoding kann theoretisch die Kreativität des Modells einschränken; bei Parsing-Aufgaben ist das kein Nachteil

## Verwandte ADRs

- [ADR-001](001-modell-wahl.md) — gemma3:27b als Modell, das Structured Output zuverlässig unterstützt
- [ADR-003](003-fallback-chain.md) — Fallback-Modelle ohne Structured Output
