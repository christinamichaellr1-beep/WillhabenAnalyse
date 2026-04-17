"""Tests for parser/v2/postprocessing.py"""
import json


VALID_EVENTS_JSON = json.dumps({
    "events": [
        {
            "event_name": "Coldplay",
            "event_datum": "2026-08-25",
            "venue": "Ernst Happel Stadion",
            "stadt": "Wien",
            "kategorie": "Stehplatz",
            "anzahl_karten": 2,
            "angebotspreis_gesamt": 190.0,
            "preis_ist_pro_karte": False,
            "originalpreis_pro_karte": 95.0,
            "confidence": "hoch",
            "confidence_grund": None,
        }
    ]
})

MULTI_EVENT_JSON = json.dumps({
    "events": [
        {"event_name": "Foo Fighters", "kategorie": "Sitzplatz",
         "originalpreis_pro_karte": 97.0, "confidence": "hoch"},
        {"event_name": "Foo Fighters", "kategorie": "Stehplatz",
         "originalpreis_pro_karte": 116.5, "confidence": "hoch"},
    ]
})

TEXT_MODE_JSON = '[{"event_name": "Rammstein", "confidence": "mittel"}]'


# --- parse_raw ---

def test_parse_raw_structured_output_parses_events_key():
    from parser.v2.postprocessing import parse_raw
    events = parse_raw(VALID_EVENTS_JSON, used_format_schema=True)
    assert len(events) == 1
    assert events[0]["event_name"] == "Coldplay"


def test_parse_raw_structured_output_multi_event():
    from parser.v2.postprocessing import parse_raw
    events = parse_raw(MULTI_EVENT_JSON, used_format_schema=True)
    assert len(events) == 2


def test_parse_raw_text_mode_parses_array():
    from parser.v2.postprocessing import parse_raw
    events = parse_raw(TEXT_MODE_JSON, used_format_schema=False)
    assert len(events) == 1
    assert events[0]["event_name"] == "Rammstein"


def test_parse_raw_text_mode_json_in_markdown():
    from parser.v2.postprocessing import parse_raw
    md_json = "```json\n" + TEXT_MODE_JSON + "\n```"
    events = parse_raw(md_json, used_format_schema=False)
    assert len(events) == 1


def test_parse_raw_invalid_json_returns_empty_event():
    from parser.v2.postprocessing import parse_raw, EMPTY_EVENT
    events = parse_raw("not json at all", used_format_schema=True)
    assert len(events) == 1
    assert events[0]["confidence"] == "niedrig"


def test_parse_raw_empty_string_returns_empty_event():
    from parser.v2.postprocessing import parse_raw
    events = parse_raw("", used_format_schema=True)
    assert len(events) == 1
    assert events[0]["confidence"] == "niedrig"


# --- validate ---

def test_validate_returns_list_of_dicts():
    from parser.v2.postprocessing import validate
    raw = [{"event_name": "Test", "confidence": "hoch", "kategorie": "Stehplatz"}]
    result = validate(raw)
    assert isinstance(result, list)
    assert result[0]["event_name"] == "Test"
    assert result[0]["confidence"] == "hoch"


def test_validate_fills_missing_fields_with_defaults():
    from parser.v2.postprocessing import validate
    result = validate([{}])
    assert result[0]["confidence"] == "niedrig"
    assert result[0]["kategorie"] == "Unbekannt"


def test_validate_normalizes_invalid_confidence():
    from parser.v2.postprocessing import validate
    result = validate([{"confidence": "sehr_hoch"}])
    assert result[0]["confidence"] == "niedrig"


def test_validate_coerces_float_fields():
    from parser.v2.postprocessing import validate
    result = validate([{"originalpreis_pro_karte": "95.5", "angebotspreis_gesamt": "190"}])
    assert result[0]["originalpreis_pro_karte"] == 95.5
    assert result[0]["angebotspreis_gesamt"] == 190.0


def test_validate_accepts_none_floats():
    from parser.v2.postprocessing import validate
    result = validate([{"originalpreis_pro_karte": None}])
    assert result[0]["originalpreis_pro_karte"] is None


# --- attach_metadata ---

def test_attach_metadata_adds_willhaben_fields():
    from parser.v2.postprocessing import attach_metadata
    events = [{"event_name": "Test", "confidence": "hoch",
               "kategorie": "Unbekannt", "confidence_grund": None}]
    ad = {
        "id": "123456",
        "link": "https://willhaben.at/test",
        "titel": "Test Ticket",
        "preis_roh": "50 €",
        "verkäufertyp": "Privat",
        "verkäufername": "Max",
        "verkäufer_id": "999",
        "mitglied_seit": "06/2020",
    }
    result = attach_metadata(events, ad, "gemma3:27b", 1500, False)
    assert result[0]["willhaben_id"] == "123456"
    assert result[0]["willhaben_link"] == "https://willhaben.at/test"
    assert result[0]["modell"] == "gemma3:27b"
    assert result[0]["pipeline_version"] == "v2.0"
    assert result[0]["parse_dauer_ms"] == 1500


def test_attach_metadata_preserves_event_fields():
    from parser.v2.postprocessing import attach_metadata
    events = [{"event_name": "Coldplay", "confidence": "hoch",
               "kategorie": "Stehplatz", "confidence_grund": None}]
    result = attach_metadata(events, {"id": "1"}, "gemma3:27b", 100, False)
    assert result[0]["event_name"] == "Coldplay"
