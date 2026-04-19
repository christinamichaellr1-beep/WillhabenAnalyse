"""
konflikt_detector.py

Detects data quality conflicts/anomalies in scraped event dicts BEFORE they
are written to Excel. Pure function — no side effects, no file I/O.
"""
from __future__ import annotations

import datetime

# Names that are considered invalid / placeholder values (lower-cased for comparison)
_UNGUELTIGE_NAMEN: frozenset[str] = frozenset({
    "unbekannt",
    "none",
    "",
    "n/a",
    "k.a.",
    "k. a.",
    "unbekanntes event",
})


def detect_konflikte(event: dict) -> list[str]:
    """
    Detects data quality conflicts in an event dict.
    Returns list of conflict description strings (empty if no conflicts).

    Checks:
    1. PREIS_LOGIK: angebotspreis_gesamt > 0 but anzahl_karten is None or 0
    2. DATUM_VERGANGENHEIT: event_datum is in the past (< today)
    3. OVP_INKONSISTENZ: originalpreis_pro_karte > 0 but ovp_quelle is None/empty
    4. PREIS_ZU_HOCH: angebotspreis_gesamt > 5000 (suspicious outlier)
    5. NAME_FEHLT: event_name is None or empty or in ungültige Namen set
    6. CONFIDENCE_NIEDRIG_KEIN_GRUND: confidence == "niedrig" but confidence_grund is None/empty
    """
    konflikte: list[str] = []

    # 1. PREIS_LOGIK
    gesamt = event.get("angebotspreis_gesamt")
    anzahl = event.get("anzahl_karten")
    if gesamt is not None and gesamt > 0 and (anzahl is None or anzahl == 0):
        konflikte.append(f"PREIS_LOGIK: gesamt={gesamt} aber anzahl_karten={anzahl}")

    # 2. DATUM_VERGANGENHEIT
    event_datum = event.get("event_datum")
    if event_datum is not None:
        try:
            datum = datetime.date.fromisoformat(str(event_datum))
            if datum < datetime.date.today():
                konflikte.append(f"DATUM_VERGANGENHEIT: {event_datum}")
        except (ValueError, TypeError):
            pass  # unparseable date — skip this check

    # 3. OVP_INKONSISTENZ
    ovp = event.get("originalpreis_pro_karte")
    ovp_quelle = event.get("ovp_quelle")
    if ovp is not None and ovp > 0 and (ovp_quelle is None or str(ovp_quelle).strip() == ""):
        konflikte.append(f"OVP_INKONSISTENZ: ovp={ovp} aber quelle leer")

    # 4. PREIS_ZU_HOCH
    if gesamt is not None and gesamt > 5000:
        konflikte.append(f"PREIS_ZU_HOCH: {gesamt}")

    # 5. NAME_FEHLT
    event_name = event.get("event_name")
    name_str = "" if event_name is None else str(event_name).strip().lower()
    if name_str in _UNGUELTIGE_NAMEN:
        konflikte.append("NAME_FEHLT")

    # 6. CONFIDENCE_NIEDRIG_KEIN_GRUND
    confidence = event.get("confidence")
    confidence_grund = event.get("confidence_grund")
    if confidence == "niedrig" and (
        confidence_grund is None or str(confidence_grund).strip() == ""
    ):
        konflikte.append("CONFIDENCE_NIEDRIG_KEIN_GRUND")

    return konflikte
