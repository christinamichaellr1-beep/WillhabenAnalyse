"""Tests for parser/v2/prompt.py"""


def test_build_prompt_contains_context():
    from parser.v2.prompt import build_prompt
    ctx = "Titel: Rammstein\nPreis: 180 €\n\nBeschreibung:\n2 Tickets Wien"
    result = build_prompt(ctx)
    assert "Rammstein" in result
    assert "180 €" in result


def test_build_prompt_returns_string():
    from parser.v2.prompt import build_prompt
    assert isinstance(build_prompt("test"), str)


def test_prompt_template_has_few_shot_examples():
    from parser.v2.prompt import PROMPT_TEMPLATE
    # Muss mindestens 3 Few-Shot-Beispiele enthalten
    assert PROMPT_TEMPLATE.count("BEISPIEL") >= 3


def test_prompt_template_has_field_definitions():
    from parser.v2.prompt import PROMPT_TEMPLATE
    for field in ["event_name", "event_datum", "originalpreis_pro_karte", "confidence"]:
        assert field in PROMPT_TEMPLATE


def test_build_prompt_no_format_instruction():
    """v2 nutzt format-Parameter — kein 'Antworte mit JSON' im Prompt nötig."""
    from parser.v2.prompt import build_prompt
    result = build_prompt("test")
    # Kein doppelter JSON-Hinweis — Grammar-Enforcement übernimmt das
    assert result.count("JSON") <= 3
