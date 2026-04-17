"""Tests for parser/v2/schema.py"""
import pytest


def test_event_result_defaults():
    from parser.v2.schema import EventResult
    e = EventResult()
    assert e.event_name is None
    assert e.confidence.value == "niedrig"
    assert e.kategorie.value == "Unbekannt"


def test_event_result_valid_data():
    from parser.v2.schema import EventResult
    e = EventResult(
        event_name="Coldplay",
        event_datum="2026-08-25",
        venue="Ernst Happel Stadion",
        stadt="Wien",
        kategorie="Stehplatz",
        anzahl_karten=2,
        angebotspreis_gesamt=190.0,
        preis_ist_pro_karte=False,
        originalpreis_pro_karte=95.0,
        confidence="hoch",
    )
    assert e.event_name == "Coldplay"
    assert e.originalpreis_pro_karte == 95.0
    assert e.confidence.value == "hoch"
    assert e.kategorie.value == "Stehplatz"


def test_event_result_invalid_confidence_coerced():
    from parser.v2.schema import EventResult
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EventResult(confidence="sehr_hoch")


def test_event_result_invalid_kategorie_coerced():
    from parser.v2.schema import EventResult
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EventResult(kategorie="Balkon")


def test_parse_response_wraps_events():
    from parser.v2.schema import ParseResponse, EventResult
    resp = ParseResponse(events=[EventResult(event_name="Test")])
    assert len(resp.events) == 1
    assert resp.events[0].event_name == "Test"


def test_ollama_format_schema_is_object_type():
    """Ollama format param requires top-level type=object."""
    from parser.v2.schema import OLLAMA_FORMAT_SCHEMA
    assert isinstance(OLLAMA_FORMAT_SCHEMA, dict)
    assert OLLAMA_FORMAT_SCHEMA.get("type") == "object"


def test_ollama_format_schema_has_events_array():
    from parser.v2.schema import OLLAMA_FORMAT_SCHEMA
    props = OLLAMA_FORMAT_SCHEMA.get("properties", {})
    assert "events" in props
    assert props["events"]["type"] == "array"


def test_event_result_null_floats_accepted():
    from parser.v2.schema import EventResult
    e = EventResult(angebotspreis_gesamt=None, originalpreis_pro_karte=None)
    assert e.angebotspreis_gesamt is None
    assert e.originalpreis_pro_karte is None
