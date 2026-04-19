"""
Tests for enrichment/konflikt_detector.py
"""
import pytest
from enrichment.konflikt_detector import detect_konflikte


def test_preis_logik_keine_anzahl():
    """gesamt=150 but anzahl=None → PREIS_LOGIK conflict."""
    event = {
        "angebotspreis_gesamt": 150.0,
        "anzahl_karten": None,
    }
    result = detect_konflikte(event)
    assert len(result) >= 1
    assert "PREIS_LOGIK" in result[0]


def test_datum_vergangenheit():
    """event_datum in the past → DATUM_VERGANGENHEIT conflict."""
    event = {
        "event_datum": "2020-01-01",
    }
    result = detect_konflikte(event)
    assert any("DATUM_VERGANGENHEIT" in k for k in result)
    assert "DATUM_VERGANGENHEIT" in result[0]


def test_ovp_inkonsistenz():
    """originalpreis_pro_karte=89.9 but ovp_quelle=None → OVP_INKONSISTENZ."""
    event = {
        "originalpreis_pro_karte": 89.9,
        "ovp_quelle": None,
    }
    result = detect_konflikte(event)
    assert any("OVP_INKONSISTENZ" in k for k in result)
    assert "OVP_INKONSISTENZ" in result[0]


def test_preis_zu_hoch():
    """angebotspreis_gesamt=9999 → PREIS_ZU_HOCH conflict."""
    event = {
        "angebotspreis_gesamt": 9999,
        "anzahl_karten": 2,  # valid anzahl so PREIS_LOGIK doesn't fire first
    }
    result = detect_konflikte(event)
    assert any("PREIS_ZU_HOCH" in k for k in result)
    # PREIS_ZU_HOCH should be in the result (position may vary)
    preis_zu_hoch = [k for k in result if "PREIS_ZU_HOCH" in k]
    assert len(preis_zu_hoch) == 1


def test_name_fehlt():
    """event_name=None → NAME_FEHLT conflict."""
    event = {
        "event_name": None,
    }
    result = detect_konflikte(event)
    assert any("NAME_FEHLT" in k for k in result)
    assert "NAME_FEHLT" in result[0]


def test_confidence_niedrig_kein_grund():
    """confidence='niedrig' but confidence_grund=None → CONFIDENCE_NIEDRIG_KEIN_GRUND."""
    event = {
        "confidence": "niedrig",
        "confidence_grund": None,
    }
    result = detect_konflikte(event)
    assert any("CONFIDENCE_NIEDRIG_KEIN_GRUND" in k for k in result)


def test_kein_konflikt_valider_event():
    """Valid event with all fields correct → empty conflict list."""
    event = {
        "event_name": "Linkin Park",
        "event_datum": "2027-06-09",  # future date
        "angebotspreis_gesamt": 250.0,
        "anzahl_karten": 2,
        "originalpreis_pro_karte": None,  # no OVP
        "ovp_quelle": None,
        "confidence": "hoch",
        "confidence_grund": None,
    }
    result = detect_konflikte(event)
    assert result == []
