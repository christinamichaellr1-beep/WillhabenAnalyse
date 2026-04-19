"""Tests for enrichment/venue_stadt_mapping.py (12 tests)."""
import pytest
from enrichment.venue_stadt_mapping import get_stadt


# --- Per-venue lookups (9 tests) ---

def test_ernst_happel_stadion():
    assert get_stadt("Ernst-Happel-Stadion") == "Wien"


def test_wiener_stadthalle():
    assert get_stadt("Wiener Stadthalle") == "Wien"


def test_gasometer_wien():
    assert get_stadt("Gasometer Wien") == "Wien"


def test_szene_wien():
    assert get_stadt("Szene Wien") == "Wien"


def test_arena_wien():
    assert get_stadt("Arena Wien") == "Wien"


def test_wiener_konzerthaus():
    assert get_stadt("Wiener Konzerthaus") == "Wien"


def test_musikverein_wien():
    assert get_stadt("Musikverein Wien") == "Wien"


def test_open_air_donauinsel():
    assert get_stadt("Open Air Donauinsel") == "Wien"


def test_wiener_volksoper():
    assert get_stadt("Wiener Volksoper") == "Wien"


# --- Edge cases (2 tests) ---

def test_none_returns_none():
    assert get_stadt(None) is None


def test_unknown_venue_returns_none():
    assert get_stadt("Unbekannte Halle") is None


# --- Integration test (1 test) ---

def test_attach_metadata_infers_stadt_from_venue():
    """attach_metadata fills stadt from venue when stadt is empty."""
    from parser.v2.postprocessing import attach_metadata

    events = [{
        "event_name": "Konzert",
        "event_datum": "2026-06-01",
        "venue": "Ernst Happel Stadion",
        "stadt": None,
        "kategorie": "Stehplatz",
        "anzahl_karten": 2,
        "angebotspreis_gesamt": 180.0,
        "preis_ist_pro_karte": False,
        "originalpreis_pro_karte": 90.0,
        "confidence": "hoch",
        "confidence_grund": None,
    }]
    ad = {"id": "99999", "link": "https://willhaben.at/x"}

    result = attach_metadata(events, ad, "gemma3:27b", 500, False)

    assert result[0]["stadt"] == "Wien"
