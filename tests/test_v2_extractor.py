"""Tests for parser/v2/extractor.py (HTTP-Calls werden gemockt)."""
import json
from unittest.mock import patch, MagicMock


def _mock_chat_response(content: str, done_reason: str = "stop") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": done_reason,
        "total_duration": 5_000_000_000,
    }
    return resp


def _mock_generate_response(response_text: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "response": response_text,
        "done": True,
        "total_duration": 5_000_000_000,
    }
    return resp


VALID_JSON = json.dumps({"events": [{"event_name": "Coldplay", "confidence": "hoch"}]})


def test_extract_uses_primary_model_by_default():
    from parser.v2 import extractor
    with patch("parser.v2.extractor.requests.post") as mock_post:
        mock_post.return_value = _mock_chat_response(VALID_JSON)
        raw, model_used, ms, fallback = extractor.extract("test prompt")
    assert model_used == extractor.PRIMARY_MODEL
    assert fallback is False
    assert "Coldplay" in raw


def test_extract_sends_format_schema_to_primary():
    from parser.v2 import extractor
    with patch("parser.v2.extractor.requests.post") as mock_post:
        mock_post.return_value = _mock_chat_response(VALID_JSON)
        extractor.extract("test prompt")
    call_kwargs = mock_post.call_args
    body = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
    assert "format" in body


def test_extract_falls_back_to_gemma4_on_primary_failure():
    from parser.v2 import extractor
    TEXT_RESP = '[{"event_name": "Foo", "confidence": "mittel"}]'
    with patch("parser.v2.extractor.requests.post") as mock_post:
        mock_post.side_effect = [
            Exception("connection refused"),  # primary fails
            _mock_generate_response(TEXT_RESP),  # fallback succeeds
        ]
        raw, model_used, ms, fallback = extractor.extract("test prompt")
    assert model_used == extractor.FALLBACK_MODEL
    assert fallback is True


def test_extract_falls_back_to_emergency_on_double_failure():
    from parser.v2 import extractor
    TEXT_RESP = '[{"event_name": "Bar", "confidence": "niedrig"}]'
    with patch("parser.v2.extractor.requests.post") as mock_post:
        mock_post.side_effect = [
            Exception("primary fail"),
            Exception("fallback fail"),
            _mock_generate_response(TEXT_RESP),  # emergency succeeds
        ]
        raw, model_used, ms, fallback = extractor.extract("test prompt")
    assert model_used == extractor.EMERGENCY_MODEL
    assert fallback is True


def test_extract_model_override_skips_fallback_chain():
    from parser.v2 import extractor
    with patch("parser.v2.extractor.requests.post") as mock_post:
        mock_post.return_value = _mock_generate_response('[{"event_name":"X"}]')
        raw, model_used, ms, fallback = extractor.extract(
            "test", model_override="gemma4:26b"
        )
    assert model_used == "gemma4:26b"


def test_extract_returns_empty_string_on_all_failures():
    from parser.v2 import extractor
    with patch("parser.v2.extractor.requests.post") as mock_post:
        mock_post.side_effect = Exception("all fail")
        raw, model_used, ms, fallback = extractor.extract("test")
    assert raw == ""
    assert fallback is True


def test_extract_returns_duration_ms():
    from parser.v2 import extractor
    with patch("parser.v2.extractor.requests.post") as mock_post:
        mock_post.return_value = _mock_chat_response(VALID_JSON)
        raw, model_used, ms, fallback = extractor.extract("test")
    assert isinstance(ms, int)
    assert ms > 0
