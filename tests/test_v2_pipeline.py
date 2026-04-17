"""Tests for parser/v2/pipeline.py (Ollama via Mock)."""
import json
from unittest.mock import patch, MagicMock


NAV_TEXT = (
    "Zum Inhalt\nZu den Suchergebnissen\nNachrichten\nEinloggen|Registrieren\n"
    "Neue Anzeige aufgeben\nMARKTPLATZ\n"
)

REAL_AD = {
    "id": "99999",
    "link": "https://willhaben.at/test",
    "titel": "Rammstein Wien 15.06.2025 - 2x Tickets",
    "preis_roh": "180 €",
    "text_komplett": (
        NAV_TEXT +
        "Konzerte / Musikfestivals\n\nRammstein Wien 15.06.2025\n"
        "Verkaufe 2 Tickets für Rammstein Wien am 15.06.2025. "
        "Originalpreis je 75 €. Privatverkauf."
    ),
    "verkäufertyp": "Privat",
    "verkäufername": "Test",
    "verkäufer_id": "111",
    "mitglied_seit": "06/2020",
}

CATEGORY_PAGE_AD = {
    "id": "cat123",
    "link": "https://willhaben.at/category",
    "titel": "4.126 Anzeigen in Konzerte / Musikfestivals",
    "preis_roh": "",
    "text_komplett": NAV_TEXT,
    "verkäufertyp": "unbekannt",
    "verkäufername": "",
    "verkäufer_id": "",
    "mitglied_seit": "",
}

MOCK_RESPONSE = json.dumps({
    "events": [{
        "event_name": "Rammstein",
        "event_datum": "2025-06-15",
        "confidence": "hoch",
        "kategorie": "Unbekannt",
        "anzahl_karten": 2,
        "angebotspreis_gesamt": 180.0,
        "originalpreis_pro_karte": 75.0,
        "preis_ist_pro_karte": False,
        "confidence_grund": None,
    }]
})


def _mock_post(content: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
        "total_duration": 5_000_000_000,
    }
    return resp


def test_parse_ad_returns_list():
    from parser.v2.pipeline import parse_ad
    with patch("parser.v2.extractor.requests.post") as mp:
        mp.return_value = _mock_post(MOCK_RESPONSE)
        result = parse_ad(REAL_AD, use_cache=False)
    assert isinstance(result, list)
    assert len(result) >= 1


def test_parse_ad_result_has_event_name():
    from parser.v2.pipeline import parse_ad
    with patch("parser.v2.extractor.requests.post") as mp:
        mp.return_value = _mock_post(MOCK_RESPONSE)
        result = parse_ad(REAL_AD, use_cache=False)
    assert result[0]["event_name"] == "Rammstein"


def test_parse_ad_result_has_v2_metadata():
    from parser.v2.pipeline import parse_ad
    with patch("parser.v2.extractor.requests.post") as mp:
        mp.return_value = _mock_post(MOCK_RESPONSE)
        result = parse_ad(REAL_AD, use_cache=False)
    assert result[0]["pipeline_version"] == "v2.0"
    assert result[0]["willhaben_id"] == "99999"
    assert "modell" in result[0]
    assert "parse_dauer_ms" in result[0]


def test_parse_ad_category_page_skipped_without_ollama_call():
    from parser.v2.pipeline import parse_ad
    with patch("parser.v2.extractor.requests.post") as mp:
        result = parse_ad(CATEGORY_PAGE_AD, use_cache=False)
    mp.assert_not_called()
    assert result[0]["confidence"] == "niedrig"


def test_parse_ads_processes_multiple_ads():
    from parser.v2.pipeline import parse_ads
    with patch("parser.v2.extractor.requests.post") as mp:
        mp.return_value = _mock_post(MOCK_RESPONSE)
        results = parse_ads([REAL_AD, REAL_AD], use_cache=False)
    assert len(results) == 2


def test_parse_ads_uses_cache_on_second_call(tmp_path):
    from parser.v2 import pipeline
    # Temporäres Cache-Verzeichnis
    original_cache = pipeline.PARSE_CACHE_DIR
    pipeline.PARSE_CACHE_DIR = tmp_path
    try:
        with patch("parser.v2.extractor.requests.post") as mp:
            mp.return_value = _mock_post(MOCK_RESPONSE)
            # Erster Aufruf: Ollama wird aufgerufen
            parse_ads_fn = pipeline.parse_ads
            parse_ads_fn([REAL_AD], use_cache=True)
            assert mp.call_count == 1
            # Zweiter Aufruf: Cache-Hit, kein Ollama-Aufruf
            parse_ads_fn([REAL_AD], use_cache=True)
            assert mp.call_count == 1  # kein zweiter Call
    finally:
        pipeline.PARSE_CACHE_DIR = original_cache
