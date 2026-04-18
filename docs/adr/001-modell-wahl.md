# ADR-001: Modell-Wechsel von gemma4:8B zu gemma3:27B

**Status:** Accepted
**Datum:** 2026-04-17

## Kontext

Parser v1 nutzte `gemma4:latest` (8B-Parameter-Modell) via `/api/generate` und erreichte eine JSON-Parse-Rate von ~85 %. Die restlichen 15 % der Anzeigen lieferten kein valides JSON und wurden ohne Ergebnis abgebrochen oder erforderten manuelle Nacharbeit. Ziel für v2.0 war eine JSON-Parse-Rate von 100 %, um den Review-Aufwand zu eliminieren und die Excel-Ausgabe vollständig automatisiert zu befüllen.

Die Eval-Suite (25 hand-verifizierte Gold-Standard-Einträge in `eval/gold_standard.json`) diente als objektiver Vergleichsmaßstab. Neben der Parse-Rate wurden auch inhaltliche Metriken bewertet: `event_name`, `event_datum`, `originalpreis_pro_karte`, `anzahl_karten`, `kategorie`, `preis_ist_pro_karte`, `angebotspreis_gesamt`.

## Entscheidung

`gemma3:27b` wird als primäres Parsing-Modell eingesetzt. Die Ollama Structured Output API (`/api/chat` mit `format`-Parameter und dem aus `ParseResponse.model_json_schema()` abgeleiteten JSON-Schema) erzwingt valides JSON auf Modell-Ebene. Das Modell wird lokal via Ollama betrieben (`http://localhost:11434`).

## Begründung

`gemma3:27b` erzielte in internen Tests in Kombination mit Structured Output eine JSON-Parse-Rate von 100 % und gleichzeitig verbesserte inhaltliche Genauigkeit (92 % Event-Count-Accuracy, 100 % event_name, 96,7 % originalpreis_pro_karte). Das deutlich größere Parameterfenster (27B vs. 8B) erlaubt besseres Verstehen von unstrukturierten Freitextanzeigen, mehrdeutigen Preisangaben und mehreren Events pro Anzeige. Da das Modell lokal läuft, entstehen keine API-Kosten und keine Datenschutzbedenken bezüglich der Weitergabe von Ticket-Anzeigendaten an externe Dienste.

Die höhere Latenz (~90 s/Anzeige statt ~25 s) ist durch den Parse-Cache (ADR-009) und die Nutzung eines Nighttime-Schedules (ADR-005) vertretbar.

## Alternativen erwogen

| Alternative | Verworfen, weil |
|-------------|-----------------|
| **Fine-tuning auf 8B** | Erfordert annotiertes Trainingsset, wartungsintensiv bei Modell-Updates; Parse-Rate-Garantie unklar |
| **GPT-4 / externe API** | API-Kosten pro Lauf, Datenschutzbedenken, Abhängigkeit von externer Verfügbarkeit, kein Offline-Betrieb |
| **Prompt-Engineering auf gemma4:8B** | Intensiv getestet; konnte strukturelle JSON-Fehler (fehlende Klammern, Kommentare im Output) nicht zuverlässig eliminieren |
| **Llama 3.3 70B** | RAM-Bedarf (~48 GB) übersteigt typische Entwicklungsmaschinen; gemma3:27b passt in ~24 GB |

## Konsequenzen

**Positiv:**
- JSON-Parse-Rate 100 % — keine kaputten Parses mehr in der Pipeline
- Inhaltliche Genauigkeit deutlich verbessert
- Kein API-Schlüssel, keine Datenweitergabe, Offline-fähig
- Fallback-Chain (ADR-003) schützt vor Ausfall

**Negativ:**
- Latenz ~3,6× höher als v1 (~90 s vs. ~25 s pro Anzeige ohne Cache-Hit)
- RAM-Bedarf ~24 GB — auf Maschinen mit weniger RAM muss auf Fallback-Modelle ausgewichen werden
- `ollama pull gemma3:27b` (~17 GB Download) erforderlich beim ersten Setup

## Verwandte ADRs

- [ADR-002](002-structured-output.md) — Ollama Structured Output als Mechanismus für 100 % Parse-Rate
- [ADR-003](003-fallback-chain.md) — Fallback-Chain bei Nichtverfügbarkeit von gemma3:27b
- [ADR-009](009-parse-cache.md) — Cache zur Kompensation der höheren Latenz
