"""Tests for Phase 4: Dashboard OVP final integration."""
import math
import pandas as pd
import pytest
from app.backend.dashboard_aggregator import aggregate


def _make_df(rows):
    return pd.DataFrame(rows)


def test_ovp_final_prefers_manual():
    """Wenn manueller OVP vorhanden, wird dieser für Margen genutzt."""
    rows = [
        {
            "event_name": "Test", "event_datum": "2026-10-01", "kategorie": "GA",
            "anbieter_typ": "Händler", "preis_pro_karte": 150.0,
            "angebotspreis_gesamt": 150.0, "anzahl_karten": 1,
            "originalpreis_pro_karte": 100.0,
            "ovp_manuell": 80.0,  # Manual OVP wins
            "verkäufername": "X", "vertrieb_klasse": "gewerblich",
            "confidence": "hoch",
        }
    ]
    result = aggregate(_make_df(rows))
    assert len(result) == 1
    # OVP should be 80.0 (manual), not 100.0 (extracted)
    assert result.iloc[0]["OVP"] == 80.0


def test_ovp_status_manuell():
    """OVP_Status ist 'manuell gepflegt ✓' wenn manueller OVP vorhanden."""
    rows = [
        {
            "event_name": "Test", "event_datum": "2026-10-01", "kategorie": "GA",
            "anbieter_typ": "Privat", "preis_pro_karte": 90.0,
            "angebotspreis_gesamt": 90.0, "anzahl_karten": 1,
            "originalpreis_pro_karte": None,
            "ovp_manuell": 80.0,
            "confidence": "hoch",
        }
    ]
    result = aggregate(_make_df(rows))
    assert result.iloc[0]["OVP_Status"] == "manuell gepflegt ✓"


def test_ovp_status_nur_extrahiert():
    """OVP_Status ist 'nur extrahiert ⚠' wenn nur LLM-OVP vorhanden."""
    rows = [
        {
            "event_name": "Test", "event_datum": "2026-10-01", "kategorie": "GA",
            "anbieter_typ": "Privat", "preis_pro_karte": 90.0,
            "angebotspreis_gesamt": 90.0, "anzahl_karten": 1,
            "originalpreis_pro_karte": 70.0,
            "ovp_manuell": None,
            "confidence": "hoch",
        }
    ]
    result = aggregate(_make_df(rows))
    assert result.iloc[0]["OVP_Status"] == "nur extrahiert ⚠"


def test_ovp_status_fehlt():
    """OVP_Status ist 'fehlt ❌' wenn kein OVP vorhanden."""
    rows = [
        {
            "event_name": "Test", "event_datum": "2026-10-01", "kategorie": "GA",
            "anbieter_typ": "Privat", "preis_pro_karte": 90.0,
            "angebotspreis_gesamt": 90.0, "anzahl_karten": 1,
            "originalpreis_pro_karte": None,
            "ovp_manuell": None,
            "confidence": "hoch",
        }
    ]
    result = aggregate(_make_df(rows))
    assert result.iloc[0]["OVP_Status"] == "fehlt ❌"
    assert math.isnan(result.iloc[0]["OVP"])
