"""
Heuristik zur Erkennung und Korrektur fehlerhafter Event-Daten.

Das LLM (gemma) extrahiert manchmal Daten, die in der Vergangenheit liegen,
obwohl das Inserat aktiv ist — häufigster Fehler: Jahr um 1 zu niedrig.
"""
import datetime


def korrigiere_datum(event: dict, heute: datetime.date | None = None) -> dict:
    """
    Heuristische Korrektur für das event_datum-Feld.

    Gibt ein neues Dict zurück (kein Mutieren des Inputs).

    Regeln IN DIESER REIHENFOLGE:
    1. KEIN_DATUM: event_datum ist None/leer → unverändert zurückgeben
    2. PARSE_FEHLER: event_datum nicht als ISO-Datum (YYYY-MM-DD) parsbar → unverändert
    3. VERGANGENHEIT_SHIFT: Datum liegt in der Vergangenheit (< heute) UND Jahr in
       [heute.year, heute.year-1]:
       - +1 Jahr versuchen: new_datum = date(parsed.year + 1, parsed.month, parsed.day)
       - Wenn new_datum > heute → Shift anwenden, event_datum setzen, Notiz in confidence_grund
       - Sonst → unverändert
    4. ZUKUNFT_ZU_WEIT: Datum mehr als 5 Jahre in der Zukunft → unverändert (verdächtig,
       aber kein sinnvoller Korrekturversuch)
    5. OK: sonst unverändert
    """
    if heute is None:
        heute = datetime.date.today()

    # Regel 1: KEIN_DATUM
    event_datum = event.get("event_datum")
    if not event_datum or str(event_datum).strip() in ("", "None"):
        return event

    # Regel 2: PARSE_FEHLER
    try:
        parsed = datetime.date.fromisoformat(str(event_datum).strip())
    except (ValueError, TypeError):
        return event

    # Regel 3: VERGANGENHEIT_SHIFT
    if parsed < heute and parsed.year in (heute.year, heute.year - 1):
        try:
            new_datum = datetime.date(parsed.year + 1, parsed.month, parsed.day)
        except ValueError:
            # Ungültiges Datum nach Shift (z.B. 29. Feb in Nicht-Schaltjahr)
            return event

        if new_datum > heute:
            result = dict(event)
            old_str = parsed.isoformat()
            new_str = new_datum.isoformat()
            result["event_datum"] = new_str
            notiz = f"[datum_shift: {old_str} → {new_str}]"
            bestehend = result.get("confidence_grund")
            if bestehend is None:
                result["confidence_grund"] = notiz
            else:
                result["confidence_grund"] = str(bestehend) + " " + notiz
            return result

        return event

    # Regel 4: ZUKUNFT_ZU_WEIT
    fuenf_jahre_spaeter = datetime.date(heute.year + 5, heute.month, heute.day)
    if parsed > fuenf_jahre_spaeter:
        return event

    # Regel 5: OK
    return event
