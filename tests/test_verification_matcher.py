"""Tests for verification.matcher — Fuzzy matching of EventCandidate results."""
from __future__ import annotations
import datetime

import pytest

from verification.matcher import (
    _name_similarity,
    _date_score,
    _city_score,
    _weighted_total,
    match,
    MatchResult,
)
from verification.clients.base import EventCandidate


# ---------------------------------------------------------------------------
# _name_similarity
# ---------------------------------------------------------------------------

def test_name_similarity_exact():
    assert _name_similarity("Linkin Park", "Linkin Park") == 1.0


def test_name_similarity_partial():
    score = _name_similarity("Taylor Swift Eras Tour", "Taylor Swift")
    assert score > 0.0, "Expected some token overlap between 'Taylor Swift Eras Tour' and 'Taylor Swift'"


def test_name_similarity_no_overlap():
    assert _name_similarity("Rammstein", "Coldplay") == 0.0


# ---------------------------------------------------------------------------
# _date_score
# ---------------------------------------------------------------------------

def test_date_score_exact():
    d = datetime.date(2025, 6, 15)
    assert _date_score(d, d) == 1.0


def test_date_score_within_7_days():
    d1 = datetime.date(2025, 6, 15)
    d2 = datetime.date(2025, 6, 18)  # 3 days apart
    assert _date_score(d1, d2) == 0.5


def test_date_score_mismatch():
    d1 = datetime.date(2025, 6, 15)
    d2 = datetime.date(2025, 7, 15)  # 30 days apart
    assert _date_score(d1, d2) == 0.0


def test_date_score_none_query():
    assert _date_score(None, datetime.date(2025, 6, 15)) == 0.0


def test_date_score_none_candidate():
    assert _date_score(datetime.date(2025, 6, 15), None) == 0.0


# ---------------------------------------------------------------------------
# _city_score
# ---------------------------------------------------------------------------

def test_city_score_exact():
    assert _city_score("Wien", "Wien") == 1.0


def test_city_score_partial():
    assert _city_score("Wien", "Wien Mitte") == 0.5


def test_city_score_mismatch():
    assert _city_score("Wien", "Graz") == 0.0


def test_city_score_none():
    assert _city_score(None, "Wien") == 0.0
    assert _city_score("Wien", None) == 0.0


# ---------------------------------------------------------------------------
# match()
# ---------------------------------------------------------------------------

def _make_candidate(name: str, datum: datetime.date | None = None, stadt: str | None = None) -> EventCandidate:
    return EventCandidate(
        event_name=name,
        event_datum=datum,
        stadt=stadt,
        source="test",
        confidence_score=0.8,
    )


def test_match_returns_none_if_no_candidates():
    result = match("Linkin Park", datetime.date(2025, 6, 15), "Wien", [])
    assert result is None


def test_match_returns_none_below_min_name_score():
    candidates = [
        _make_candidate("Coldplay World Tour", datetime.date(2025, 6, 15), "Wien"),
        _make_candidate("Ed Sheeran Mathematics", datetime.date(2025, 6, 15), "Wien"),
    ]
    result = match("Rammstein Europa Tour", datetime.date(2025, 6, 15), "Wien", candidates)
    assert result is None


def test_match_returns_best_candidate():
    date = datetime.date(2025, 6, 15)
    # Candidate 1: good name match, exact date, exact city → high score
    good = _make_candidate("Linkin Park World Tour", date, "Wien")
    # Candidate 2: poor name match → low score (may be filtered by min_name_score)
    bad = _make_candidate("Coldplay Concert", datetime.date(2025, 1, 1), "Graz")

    result = match("Linkin Park", date, "Wien", [good, bad])
    assert result is not None
    assert result.candidate is good


def test_match_result_has_correct_fields():
    date = datetime.date(2025, 8, 20)
    cand = _make_candidate("Rammstein Europa Tour", date, "Wien")
    result = match("Rammstein", date, "Wien", [cand])
    assert result is not None
    assert isinstance(result, MatchResult)
    assert 0.0 <= result.name_score <= 1.0
    assert result.date_score == 1.0
    assert result.city_score == 1.0
    assert result.total_score == _weighted_total(result.name_score, result.date_score, result.city_score)


def test_match_respects_custom_min_name_score():
    cand = _make_candidate("Taylor Swift Eras Tour")
    # With a very high threshold, partial matches should be excluded
    result = match("Taylor", None, None, [cand], min_name_score=0.9)
    assert result is None


def test_match_selects_higher_total_score():
    date = datetime.date(2025, 9, 10)
    # Better candidate: exact name match, exact date, exact city
    better = _make_candidate("Die Toten Hosen", date, "Wien")
    # Worse candidate: exact name match, date mismatch, city mismatch
    worse = _make_candidate("Die Toten Hosen", datetime.date(2024, 1, 1), "Berlin")

    result = match("Die Toten Hosen", date, "Wien", [worse, better])
    assert result is not None
    assert result.candidate is better
    assert result.total_score > _weighted_total(1.0, 0.0, 0.0)
