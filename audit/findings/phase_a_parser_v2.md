# Phase A — parser/v2/ Audit
**Geprüft:** 2026-04-18
**Findings gesamt:** 24 (CRITICAL: 1, HIGH: 5, MEDIUM: 8, LOW: 6, INFO: 4)

---

## [CRITICAL] Prompt-Injection via unkontrollierten Anzeigentext (prompt.py:131, preprocessing.py:110–123)
**Dimension:** Security
**Impact:** `build_context()` bettet den rohen Anzeigentext direkt in den Prompt ein, ohne dass Sonderzeichen, Steuerwörter oder das Literal `{context}` im Text selbst escaped werden. Ein Inserat, dessen Beschreibung den String `{context}` oder LLM-Steuermarkierungen (z. B. `════════`, `SCHRITT`, Rollenwechsel-Tokens) enthält, kann den Prompt-Aufbau korrumpieren. Außerdem: `build_prompt()` nutzt `str.replace("{context}", context)` — wenn `context` selbst den String `{context}` enthält, wird er rekursiv ersetzt und erzeugt einen malformed Prompt mit doppeltem Inhalt oder defekter Struktur.
**Fix-Vorschlag:** Entweder Template-Strings mit `str.format_map` plus vorherigem Escape (`context = context.replace("{", "{{").replace("}", "}}")`) oder — sauberer — Jinja2 mit Autoescape. Die Übergabe des Kontexts sollte unabhängig vom Template-Literal sein.
**Aufwand:** S

---

## [HIGH] `parse_ads()` ignoriert Cache-Schreib-Fehler still; Cache-Korruption wird beim Lesen verschwiegen (pipeline.py:120–123, 126–132)
**Dimension:** Logik-Fehler
**Impact:** `_load_cache()` fängt alle Exceptions mit einem leeren `pass` und gibt `None` zurück. Ist eine Cache-Datei korrupt (z. B. partiell geschriebene JSON durch Absturz), wird sie stillschweigend ignoriert — die Anzeige wird neu geparst, aber die korrupte Datei bleibt auf Disk. Beim nächsten Lauf wird sie erneut ignoriert, jedoch nicht repariert. Im Betrieb wächst damit ein stiller Fehler-Bestand. `_save_cache()` loggt den Fehler, löscht die korrupte Datei aber nicht, d. h. der kaputte Stand bleibt persistent.
**Fix-Vorschlag:** In `_load_cache()` die korrupte Datei nach fehlgeschlagenem Parse löschen (`path.unlink(missing_ok=True)`) und einen WARNING-Log schreiben. In `_save_cache()` ebenfalls bei Fehler die unvollständige Datei entfernen.
**Aufwand:** XS

---

## [HIGH] Race Condition beim atomaren Schreiben in `StatusWriter._write()` (status_writer.py:75–84)
**Dimension:** Logik-Fehler / Performance
**Impact:** `tmp.replace(self._file)` ist auf demselben Dateisystem atomar (POSIX-Rename). Werden jedoch mehrere Prozesse/Threads gleichzeitig einen `StatusWriter` für dieselbe `STATUS_FILE` betreiben (z. B. zwei parallele `parse_ads()`-Aufrufe aus separaten Prozessen), überschreiben sich die `.tmp`-Dateien und der letzte Rename gewinnt. Der Name der `.tmp`-Datei ist statisch (`.json.tmp`), nicht prozess-eindeutig. Bei Parallelausführung (Multiprocessing, mehrere Skript-Instanzen) gehen Status-Updates verloren oder erzeugen ein gemischtes Bild.
**Fix-Vorschlag:** Temporär-Dateinamen mit PID oder UUID einzigartig machen: `tmp = self._file.with_name(self._file.stem + f"_{os.getpid()}.tmp")`.
**Aufwand:** XS

---

## [HIGH] `_parse_text()`: Greedy-Regex `\{.*?\}` mit `re.DOTALL` matched zu wenig (postprocessing.py:104–116)
**Dimension:** Logik-Fehler
**Impact:** Das Regex `(\[.*?\])` und `(\{.*?\})` sind non-greedy (`?`) mit `re.DOTALL`. Bei einem JSON-Array oder -Objekt mit verschachtelten Strukturen findet `.*?` nur bis zur ersten schließenden Klammer — also z. B. `[{"a": 1}` ohne das schließende `]` beim Array wenn ein `]` in einem String-Wert vorkommt, oder es wird zu früh abgebrochen. In der Praxis extrahiert das Regex für valides JSON-Array-Multiline korrekt, bei Werten die `]` enthalten (z. B. `"beschreibung": "Reihe [5]"`) bricht es vorzeitig ab und liefert invalides JSON, das die nachfolgende Exception-Behandlung auslöst. Resultat: unnötiger Fallback zum EMPTY_EVENT.
**Fix-Vorschlag:** Statt Regex einen balancierenden JSON-Extraktor verwenden — suche die Position des ersten `[` oder `{` und nutze `json.JSONDecoder().raw_decode()` ab dieser Position. Das ist robust gegenüber verschachteltem JSON.
**Aufwand:** S

---

## [HIGH] Kein Timeout-Handling zwischen Retries in `extractor.py`: 3× 240 s möglich (extractor.py:36–78)
**Dimension:** Performance
**Impact:** Jede der drei Retry-Versuche bei `_call_chat` / `_call_generate` hat einen Timeout von 240 Sekunden. `stop_after_attempt(3)` bedeutet im schlimmsten Fall 3 × 240 s = 12 Minuten pro Modell. Da drei Modelle in der Fallback-Chain stehen, ist der absolute Worst-Case 3 Modelle × 3 Versuche × 240 s = **36 Minuten Blockzeit** für eine einzige Anzeige. `parse_ads()` ist synchron — die gesamte Pipeline blockiert. Für Batches von 100+ Anzeigen ist das ein Produktions-Blocker in schlecht erreichbaren Netzwerksituationen.
**Fix-Vorschlag:** Aggressiveres Timeout (z. B. 60–90 s), oder einen globalen Deadline-Parameter für die gesamte Fallback-Chain einführen. Alternativ: `parse_ads()` async oder mit Thread-Pool betreiben.
**Aufwand:** S

---

## [HIGH] `fallback_used`-Flag inkonsistent: `model_override` setzt es immer auf `False` (extractor.py:96–105)
**Dimension:** Logik-Fehler
**Impact:** Bei Erfolg mit `model_override` gibt `extract()` `fallback_used=False` zurück — auch dann, wenn ein nicht-primäres Modell überschrieben wurde. `pipeline.py:48` leitet daraus ab, ob `used_format_schema=True` ist: `used_format = (model_used == extractor.PRIMARY_MODEL and not fallback_used)`. Das ist korrekt. Bei Fehler mit `model_override` gibt `extract()` jedoch `("", model_override, 0, True)` zurück — `fallback_used=True`. Da `model_override == PRIMARY_MODEL` im Fehlerfall trotzdem möglich wäre, würde `used_format` fälschlicherweise `False` (da `fallback_used=True`), und `postprocessing.parse_raw()` würde den langsameren Regex-Fallback nutzen statt den strukturierten Parser — obwohl Primary benutzt wurde. Dieser Fall tritt auf wenn Primary explizit überschrieben wird und dann scheitert.
**Fix-Vorschlag:** `fallback_used` semantisch klären: es sollte signalisieren, ob ein Nicht-Primary-Modell verwendet wurde, nicht ob ein Fehler auftrat. Bei `model_override`-Fehler entweder Exception weiterwerfen oder ein separates `error`-Flag zurückgeben.
**Aufwand:** S

---

## [MEDIUM] `PARSE_CACHE_DIR.mkdir()` auf Modul-Ebene: Side-Effect beim Import (pipeline.py:17)
**Dimension:** Maintainability / Testabdeckung
**Impact:** `PARSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)` wird beim Import von `pipeline` ausgeführt. In Unit-Tests, die das Modul importieren, wird dadurch ein Verzeichnis auf dem Dateisystem angelegt — auch wenn kein Caching gewünscht ist. Das erschwert isolierte Tests und kann in CI-Umgebungen zu unerwarteten Artefakten führen.
**Fix-Vorschlag:** Das `mkdir()` in eine Funktion verschieben, die lazy beim ersten Cache-Schreiben aufgerufen wird (`_save_cache()` oder `_cache_path()`).
**Aufwand:** XS

---

## [MEDIUM] `use_cache`-Parameter in `parse_ad()` ist deklariert aber vollständig ignoriert (pipeline.py:22–53)
**Dimension:** Dead Code / Logik-Fehler
**Impact:** Die Signatur von `parse_ad()` nimmt `use_cache: bool = True` entgegen, aber die Funktion liest und schreibt niemals den Cache. Aufrufer (inklusive `parse_ads()` selbst via `parse_ad(ad, model=model, use_cache=False)`) übergeben `use_cache=False` in der Erwartung, dass kein Cache benutzt wird — was zufällig stimmt, aber nur weil der Parameter ohnehin ignoriert wird. Dies ist semantisch irreführend und kann zukünftige Entwickler zu falschen Annahmen verleiten.
**Fix-Vorschlag:** Den Parameter aus `parse_ad()` entfernen, oder Cache-Logik korrekt in `parse_ad()` implementieren.
**Aufwand:** XS

---

## [MEDIUM] `_validate_one()`: Felder aus LLM-Antwort außerhalb des bekannten Schemas werden stillschweigend verworfen (postprocessing.py:136–137)
**Dimension:** Logik-Fehler
**Impact:** `result.update({k: v for k, v in obj.items() if k in EMPTY_EVENT})` filtert alle Keys, die nicht in `EMPTY_EVENT` sind. Das ist sicherheitstechnisch defensiv, aber gleichzeitig: wenn das LLM ein gültiges Feld liefert das nicht in `EMPTY_EVENT` definiert ist (z. B. weil `EMPTY_EVENT` veraltet oder unvollständig ist gegenüber `EventResult`), wird es ohne Warnung verworfen. Es gibt keine Drift-Detection zwischen `EMPTY_EVENT` und `EventResult`/`schema.py`.
**Fix-Vorschlag:** `EMPTY_EVENT` direkt aus `EventResult.model_fields` ableiten statt manuell zu pflegen. So gibt es nie eine Divergenz zwischen Schema und Validation-Defaults.
**Aufwand:** S

---

## [MEDIUM] `datetime.datetime.now().isoformat()` ohne Timezone in `attach_metadata()` (postprocessing.py:198)
**Dimension:** Logik-Fehler / Konsistenz
**Impact:** `parsed_at` wird mit naivem Datetime (ohne Timezone) gesetzt. `StatusWriter` hingegen verwendet `datetime.now(timezone.utc).isoformat()` (mit UTC). Die gespeicherten Events haben inkonsistente `parsed_at`-Stempel — mal naive (lokale Zeit), mal UTC-aware. Das führt bei Zeitvergleichen, Sortierungen und Datenbank-Ingestion zu stillen Fehlern.
**Fix-Vorschlag:** `datetime.datetime.now(datetime.timezone.utc).isoformat()` verwenden.
**Aufwand:** XS

---

## [MEDIUM] `strip_nav_prefix()` hat O(n²)-ähnliches Verhalten bei langen Texten (preprocessing.py:88–107)
**Dimension:** Performance
**Impact:** `any(kw in line_lower for kw in NAV_KEYWORDS)` iteriert für jede Zeile über alle 12 NAV_KEYWORDS. Bei einem langen Text mit vielen Zeilen ist das `O(Zeilen × Keywords)`. Bei `max_chars=6000` und typischen Zeilenlängen von ~80 Zeichen sind das ca. 75 Zeilen × 12 Keywords = 900 Operationen — akzeptabel. Wächst jedoch `NAV_KEYWORDS` oder werden sehr lange Rohtexte übergeben (kein Pre-Truncating vor `strip_nav_prefix`), skaliert das schlecht. Beachte: `build_context()` truncated erst **nach** `strip_nav_prefix()` — der volle `text_komplett` wird als Input übergeben, nicht auf `max_chars` begrenzt.
**Fix-Vorschlag:** Entweder ein kompiliertes Regex aus den NAV_KEYWORDS (einmaliger Compile-Aufwand, dann O(n)), oder den Text vor `strip_nav_prefix` auf ein sinnvolles Maximum (z. B. 10.000 Zeichen) begrenzen.
**Aufwand:** S

---

## [MEDIUM] Prompt-Template enthält invalides JSON in Few-Shot-Beispielen (prompt.py:69, 79, 92–94, 101, 109)
**Dimension:** Logik-Fehler
**Impact:** Die Beispiele im Prompt verwenden `{event_name: "..."}` (unquoted Keys), was kein valides JSON ist. Das primäre Modell (`gemma3:27b`) wird durch Grammar-Enforcement (`format`-Parameter) trotzdem korrektes JSON produzieren. Für die Fallback-Modelle (`gemma4:26b`, `gemma4:latest`) im Text-Modus könnte das Lernen aus invaliden JSON-Beispielen die LLM-Ausgabequalität verschlechtern — die Modelle könnten ebenfalls unquoted Keys ausgeben, die dann `json.loads()` scheitern lassen.
**Fix-Vorschlag:** Alle Few-Shot-Beispiele auf valides JSON umstellen (quoted Keys, korrekte Trennzeichen).
**Aufwand:** S

---

## [MEDIUM] `_call_chat` und `_call_generate` sind identisch strukturiert — Code-Duplizierung (extractor.py:36–78)
**Dimension:** Maintainability
**Impact:** Beide Funktionen haben identischen Retry-Decorator, identische HTTP-Behandlung und identische Response-Verarbeitung. Der einzige Unterschied ist URL, JSON-Payload-Schlüssel (`messages` vs. `prompt`) und Response-Schlüssel (`message.content` vs. `response`). Änderungen am Retry-Verhalten, Timeout oder Error-Handling müssen an zwei Stellen vorgenommen werden.
**Fix-Vorschlag:** Eine generische `_call_ollama(url, payload, response_key)` Funktion extrahieren, die von beiden Spezialfunktionen aufgerufen wird.
**Aufwand:** S

---

## [LOW] Import `from typing import Any` in `pipeline.py` ungenutzt (pipeline.py:7)
**Dimension:** Dead Code
**Impact:** `Any` wird in `pipeline.py` importiert aber nirgendwo in der Datei verwendet. Erzeugt Rauschen und kann Linter-Warnungen auslösen.
**Fix-Vorschlag:** Import entfernen.
**Aufwand:** XS

---

## [LOW] Import `import time` in `extractor.py` ungenutzt (extractor.py:7)
**Dimension:** Dead Code
**Impact:** `time` wird importiert, aber nicht verwendet. Vermutlich ein Überbleibsel aus einer früheren Version mit manuellem Sleep zwischen Retries.
**Fix-Vorschlag:** Import entfernen.
**Aufwand:** XS

---

## [LOW] `EMPTY_EVENT` ist ein mutabler Dict auf Modul-Ebene; `dict(EMPTY_EVENT)` als Schutz ist korrekt aber fragil (postprocessing.py:15–27)
**Dimension:** Maintainability
**Impact:** `EMPTY_EVENT` ist kein konstantes Objekt — es ist ein normales `dict`, das theoretisch mutiert werden könnte. An drei Stellen wird korrekt `dict(EMPTY_EVENT)` (Shallow Copy) verwendet. Käme ein Entwickler auf die Idee, direkt `EMPTY_EVENT["field"] = value` zu schreiben (z. B. in einem Test oder einer schnellen Fix-Iteration), würden alle zukünftigen Kopien den mutierten Default erhalten — ein schwer zu findender Bug.
**Fix-Vorschlag:** `EMPTY_EVENT` als `types.MappingProxyType({...})` definieren, um Mutation zur Laufzeit unmöglich zu machen.
**Aufwand:** XS

---

## [LOW] `_RETRY_EXCEPTIONS` ist als Tupel nach dem Import definiert, aber der Decorator referenziert es davor (extractor.py:12–15 vs. 36)
**Dimension:** Konsistenz / Logik-Fehler
**Impact:** In der aktuellen Datei ist die Reihenfolge: `_RETRY_EXCEPTIONS` definiert (Z.12), dann `from .schema import ...` (Z.17), dann Decorator mit `retry_if_exception_type(_RETRY_EXCEPTIONS)` (Z.36). Das ist korrekt und funktioniert. Aber der `from .schema import` steht mitten zwischen Konstanten-Definitionen und dem Standard-Import-Block — das verletzt PEP 8 (lokale Imports ans Ende, oder besser: alle Imports am Anfang). Linter-Tools (isort, flake8) würden hier warnen.
**Fix-Vorschlag:** Alle Imports an den Anfang der Datei verschieben, `_RETRY_EXCEPTIONS` nach den Imports definieren.
**Aufwand:** XS

---

## [LOW] Inkonsistente Feldnamen: `titel` vs. `title`, `verkäufertyp` (mit Umlaut) in Dicts (preprocessing.py:51, 65, pipeline.py:80, postprocessing.py:193)
**Dimension:** Konsistenz
**Impact:** `preprocessing.py` liest `ad.get("titel", ...)` (Deutsch), aber `pipeline.py:80` liest `ad.get("title", ad.get("beschreibung", ""))` (Englisch/Gemischt). Gleichzeitig speichert `attach_metadata()` Felder wie `verkäufertyp`, `verkäufername` mit deutschen Umlauten, während andere Felder (`willhaben_id`, `willhaben_link`) ASCII sind. Keine klare Namenskonvention für das interne Daten-Dict.
**Fix-Vorschlag:** Eine zentrale Schema-Dokumentation (oder Dataclass/TypedDict) für das `ad`-Dict einführen, die alle erwarteten Keys normiert.
**Aufwand:** M

---

## [LOW] `_CONTENT_PATTERNS` in `preprocessing.py` kompiliert `\beur\b` case-insensitiv, aber `€` ist kein Word-Boundary-Fall (preprocessing.py:16–19)
**Dimension:** Logik-Fehler (minor)
**Impact:** Das Pattern `\beur\b` soll "EUR" als Währungshinweis erkennen. `\b` im Python-Regex-Modul erkennt Word-Boundaries nur für ASCII-Wortzeichen (`\w = [a-zA-Z0-9_]`). Das Pattern funktioniert korrekt. Hingegen würde "EUR" in "EURL" (hypothetisch) nicht matchen, was gewollt ist. Kein echter Bug, aber das Pattern ist undokumentiert und könnte bei Refactoring falsch verstanden werden.
**Fix-Vorschlag:** Kommentar ergänzen, warum `\beur\b` statt z. B. `(?<!\w)eur(?!\w)` verwendet wird.
**Aufwand:** XS

---

## [INFO] Kein einziges Test-File in parser/v2/ vorhanden (alle Dateien)
**Dimension:** Testabdeckung
**Impact:** Es gibt keine Unit-Tests für die sieben Module. Kritische Logik wie `_parse_text()`, `_validate_one()`, `strip_nav_prefix()`, `is_non_ticket_ad()` und die Fallback-Chain in `extract()` ist vollständig ungetestet. Fehler in Randfällen (leere Eingaben, malformed JSON, Unicode-Sonderzeichen) können erst im Produktionsbetrieb entdeckt werden.
**Fix-Vorschlag:** Mindestens `test_postprocessing.py` und `test_preprocessing.py` mit parametrisierten Tests für die Parse- und Validierungs-Logik anlegen. Für `extractor.py` Mocking der `requests.post`-Calls.
**Aufwand:** L

---

## [INFO] `StatusWriter._write()` verschluckt alle Exceptions; kein Logging (status_writer.py:83–84)
**Dimension:** Maintainability
**Impact:** `except Exception: pass` ist als bewusstes "Best-effort"-Design kommentiert. Das ist für Status-Writes akzeptabel. Jedoch: ohne jegliches Logging ist es im Betrieb unmöglich zu diagnostizieren, ob Status-Writes systematisch fehlschlagen (z. B. volle Disk, Permission-Problem). Der Fehler tritt lautlos auf.
**Fix-Vorschlag:** Zumindest einmalig ein WARNING-Log schreiben wenn der erste Write fehlschlägt, danach stilles Ignorieren (mit einem `_write_failed`-Flag).
**Aufwand:** XS

---

## [INFO] `build_context()` truncated mid-multibyte-character möglich (preprocessing.py:121)
**Dimension:** Logik-Fehler (edge case)
**Impact:** `stripped[:max_chars]` schneidet auf Zeichen-Ebene ab (Python str = Unicode), nicht auf Byte-Ebene — das ist korrekt für Ollama, das UTF-8 erwartet. Kein echter Bug. Jedoch kann mitten in einem Satz abgeschnitten werden, was den LLM-Kontext semantisch beschädigt.
**Fix-Vorschlag:** Statt hartem Byte-Cut auf die nächste Leerzeile oder Satzgrenze truncaten: `stripped[:max_chars].rsplit("\n", 1)[0]`.
**Aufwand:** XS

---

## [INFO] Keine Version-Pinning-Dokumentation für Ollama-Modelle (extractor.py:21–23)
**Dimension:** Maintainability
**Impact:** `PRIMARY_MODEL = "gemma3:27b"` etc. sind Magic Strings ohne Dokumentation, welche konkrete Ollama-Version/Digest erwartet wird. Wird das lokale Ollama-Modell aktualisiert, kann sich das Ausgabeverhalten ohne Code-Änderung ändern.
**Fix-Vorschlag:** In einem Kommentar oder separaten `config.py` dokumentieren, welcher Ollama-Digest / welche Modellversion getestet und freigegeben wurde.
**Aufwand:** XS

---

## [INFO] `from typing import Any` in `postprocessing.py` nur für `EMPTY_EVENT`-Annotation (postprocessing.py:9)
**Dimension:** Dead Code (minor)
**Impact:** `Any` wird nur in der `EMPTY_EVENT: dict[str, Any]`-Annotation verwendet. Ab Python 3.9+ ist `dict[str, Any]` via `from __future__ import annotations` oder direkt nutzbar; `Any` ist aus `typing` korrekt importiert. Kein Bug, aber der Import könnte durch `object` oder gar keine explizite Annotation ersetzt werden wenn der Typ ohnehin heterogen ist.
**Fix-Vorschlag:** Belassen oder auf `dict` ohne explizites Value-Type reduzieren. Kein Handlungsbedarf.
**Aufwand:** XS

---

*Audit durchgeführt am 2026-04-18. Alle Findings basieren auf statischer Code-Analyse ohne Ausführung.*
