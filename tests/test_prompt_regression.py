"""
Prompt-Hardening Regression Tests — Stage 2.
Kein echtes Ollama nötig: Tests validieren Gold-Standard-Struktur und Prompt-Inhalt.
"""
import json
from pathlib import Path
import pytest

GOLD_PATH = Path(__file__).parent / "gold_standard" / "prompt_hardening_regression.json"


@pytest.fixture(scope="module")
def gold():
    return json.loads(GOLD_PATH.read_text(encoding="utf-8"))


def test_gold_standard_laedt(gold):
    assert "cases" in gold
    assert len(gold["cases"]) == 22


def test_alle_cases_haben_pflichtfelder(gold):
    for case in gold["cases"]:
        assert "id" in case, f"Kein id in {case}"
        assert "input" in case, f"Kein input in {case}"
        assert "expected_events" in case, f"Kein expected_events in {case}"
        assert "is_valid_extraction" in case, f"Kein is_valid_extraction in {case}"
        assert isinstance(case["expected_events"], list) and len(case["expected_events"]) >= 1


@pytest.mark.parametrize("case_idx", range(22))
def test_expected_events_valide_schema(gold, case_idx):
    from parser.v2.postprocessing import validate
    case = gold["cases"][case_idx]
    validated = validate(case["expected_events"])
    assert validated, f"validate() returned empty für {case['id']}"


@pytest.mark.parametrize("case_idx", range(22))
def test_is_valid_extraction_korrekt(gold, case_idx):
    from parser.v2.postprocessing import ist_valide_event_extraktion
    case = gold["cases"][case_idx]
    result = ist_valide_event_extraktion(case["expected_events"][0])
    assert result == case["is_valid_extraction"], (
        f"{case['id']}: expected is_valid={case['is_valid_extraction']}, got {result}"
    )


def test_extraction_prompt_enthaelt_k1_regel():
    from parser.v2.prompt import EXTRACTION_PROMPT
    assert "K1" in EXTRACTION_PROMPT or "EVENT-NAME NICHT" in EXTRACTION_PROMPT


def test_extraction_prompt_enthaelt_k2_regel():
    from parser.v2.prompt import EXTRACTION_PROMPT
    assert "K2" in EXTRACTION_PROMPT or "TRIBUTE" in EXTRACTION_PROMPT.upper()


def test_extraction_prompt_enthaelt_k3_regel():
    from parser.v2.prompt import EXTRACTION_PROMPT
    assert "K3" in EXTRACTION_PROMPT or "KATEGORIE" in EXTRACTION_PROMPT.upper()


def test_build_prompt_funktioniert():
    from parser.v2.prompt import build_prompt
    result = build_prompt("Testanzeige")
    assert "Testanzeige" in result
    assert len(result) > 500
