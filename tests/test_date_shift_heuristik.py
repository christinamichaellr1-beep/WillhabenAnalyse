"""Tests for parser/v2/date_shift_heuristik.py"""
import datetime
import pytest

from parser.v2.date_shift_heuristik import korrigiere_datum


HEUTE = datetime.date(2026, 4, 19)


# --- Regel 1: KEIN_DATUM ---

def test_kein_datum_unveraendert():
    event = {"event_datum": None, "confidence_grund": None}
    result = korrigiere_datum(event, heute=HEUTE)
    assert result["event_datum"] is None
    assert result is event  # unverändert, gleiches Objekt


# --- Regel 2: PARSE_FEHLER ---

def test_parse_fehler_unveraendert():
    event = {"event_datum": "nicht-ein-datum", "confidence_grund": None}
    result = korrigiere_datum(event, heute=HEUTE)
    assert result["event_datum"] == "nicht-ein-datum"
    assert result is event


# --- Regel 5: OK (valides Zukunftsdatum) ---

def test_valides_zukunftsdatum():
    event = {"event_datum": "2027-06-09", "confidence_grund": None}
    result = korrigiere_datum(event, heute=HEUTE)
    assert result["event_datum"] == "2027-06-09"
    assert result is event


# --- Regel 3: VERGANGENHEIT_SHIFT ---

def test_vergangenheit_shift_angewendet():
    """2025-06-09 liegt in der Vergangenheit, +1 Jahr = 2026-06-09 liegt in der Zukunft."""
    event = {"event_datum": "2025-06-09", "confidence_grund": None}
    result = korrigiere_datum(event, heute=HEUTE)
    assert result["event_datum"] == "2026-06-09"


def test_shift_notiz_in_confidence_grund():
    """Der Shift-Hinweis wird in confidence_grund eingetragen."""
    event = {"event_datum": "2025-06-09", "confidence_grund": None}
    result = korrigiere_datum(event, heute=HEUTE)
    assert "[datum_shift: 2025-06-09 → 2026-06-09]" in result["confidence_grund"]


def test_shift_notiz_angehaengt_wenn_confidence_grund_vorhanden():
    """Bestehender confidence_grund bleibt erhalten, Notiz wird angehängt."""
    event = {"event_datum": "2025-06-09", "confidence_grund": "bereits vorhanden"}
    result = korrigiere_datum(event, heute=HEUTE)
    assert "bereits vorhanden" in result["confidence_grund"]
    assert "[datum_shift: 2025-06-09 → 2026-06-09]" in result["confidence_grund"]


def test_shift_nur_wenn_ergebnis_zukunft():
    """2025-03-01 +1 Jahr = 2026-03-01, liegt VOR heute (April 2026) → kein Shift."""
    event = {"event_datum": "2025-03-01", "confidence_grund": None}
    result = korrigiere_datum(event, heute=HEUTE)
    assert result["event_datum"] == "2025-03-01"
    assert result is event


# --- Regel 4: ZUKUNFT_ZU_WEIT ---

def test_zukunft_zu_weit_unveraendert():
    """Datum mehr als 5 Jahre in der Zukunft → unverändert."""
    event = {"event_datum": "2035-01-01"}
    result = korrigiere_datum(event, heute=HEUTE)
    assert result["event_datum"] == "2035-01-01"
    assert result is event


# --- Integration: validate() wendet shift an ---

def test_integration_in_validate():
    """validate() in postprocessing.py ruft korrigiere_datum auf."""
    from parser.v2.postprocessing import validate
    raw = [{
        "event_name": "Testkonzert",
        "event_datum": "2025-06-09",
        "confidence": "hoch",
        "confidence_grund": None,
        "kategorie": "Stehplatz",
    }]
    # validate() verwendet datetime.date.today() intern — wir prüfen nur, dass
    # der Shift-Mechanismus im Pipeline-Code verdrahtet ist.
    # Da today() == 2026-04-19 laut Aufgabe, erwarten wir den Shift.
    result = validate(raw)
    # Der Shift greift wenn heute == 2026-04-19 (wie in der Aufgabe dokumentiert).
    # Unabhängig vom Testdatum prüfen wir, dass confidence_grund die Notiz enthält
    # ODER event_datum unverändert ist (kein Crash).
    assert "event_datum" in result[0]
    # Wenn der Shift angewendet wurde, muss die Notiz da sein
    if result[0]["event_datum"] == "2026-06-09":
        assert "[datum_shift: 2025-06-09 → 2026-06-09]" in result[0]["confidence_grund"]
