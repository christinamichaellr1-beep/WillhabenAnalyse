"""Tests for verification/orchestrator.py — Phase 3."""
from __future__ import annotations
import datetime
from unittest.mock import MagicMock

import pytest

from verification.clients.base import EventCandidate
from verification.orchestrator import Orchestrator, VerifStatus, VerificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(source_name: str, available: bool = True, candidates=None, raises=False):
    """Build a mock client."""
    client = MagicMock()
    client.SOURCE_NAME = source_name
    client.is_available.return_value = available
    if raises:
        client.search.side_effect = Exception(f"{source_name} exploded")
    else:
        client.search.return_value = candidates if candidates is not None else []
    return client


def _high_score_candidate(source: str = "musicbrainz") -> EventCandidate:
    """Returns a candidate that produces a near-perfect match against 'Linkin Park' / 2026-06-09 / Wien."""
    return EventCandidate(
        event_name="Linkin Park",
        event_datum=datetime.date(2026, 6, 9),
        venue="Ernst-Happel-Stadion",
        stadt="Wien",
        source=source,
        confidence_score=0.9,
    )


# ---------------------------------------------------------------------------
# Test 1: SKIPPED when event_name is None
# ---------------------------------------------------------------------------

def test_verify_skipped_empty_name():
    orc = Orchestrator(
        musicbrainz=_make_client("musicbrainz"),
        wikidata=_make_client("wikidata"),
        songkick=_make_client("songkick", available=False),
        bandsintown=_make_client("bandsintown", available=False),
    )
    result = orc.verify(None)
    assert result.status == VerifStatus.SKIPPED
    assert result.sources_checked == []


# ---------------------------------------------------------------------------
# Test 2: SKIPPED when event_name is blank
# ---------------------------------------------------------------------------

def test_verify_skipped_blank_name():
    orc = Orchestrator(
        musicbrainz=_make_client("musicbrainz"),
        wikidata=_make_client("wikidata"),
        songkick=_make_client("songkick", available=False),
        bandsintown=_make_client("bandsintown", available=False),
    )
    result = orc.verify("   ")
    assert result.status == VerifStatus.SKIPPED


# ---------------------------------------------------------------------------
# Test 3: VERIFIED when 2 sources confirm with high score
# ---------------------------------------------------------------------------

def test_verify_verified_two_sources():
    cand = _high_score_candidate("musicbrainz")

    mock_mb = _make_client("musicbrainz", candidates=[cand])
    mock_wd = _make_client("wikidata", candidates=[
        EventCandidate(
            event_name="Linkin Park",
            event_datum=datetime.date(2026, 6, 9),
            venue="Ernst-Happel-Stadion",
            stadt="Wien",
            source="wikidata",
            confidence_score=0.85,
        )
    ])
    mock_sk = _make_client("songkick", available=False)
    mock_bit = _make_client("bandsintown", available=False)

    orc = Orchestrator(musicbrainz=mock_mb, wikidata=mock_wd, songkick=mock_sk, bandsintown=mock_bit)
    result = orc.verify("Linkin Park", datetime.date(2026, 6, 9), "Wien")

    assert result.status == VerifStatus.VERIFIED
    assert "musicbrainz" in result.sources_confirmed
    assert "wikidata" in result.sources_confirmed
    assert result.best_match is not None
    assert result.best_match.total_score >= 0.6


# ---------------------------------------------------------------------------
# Test 4: LIKELY when only 1 source confirms
# ---------------------------------------------------------------------------

def test_verify_likely_one_source():
    cand = _high_score_candidate("musicbrainz")
    mock_mb = _make_client("musicbrainz", candidates=[cand])
    mock_wd = _make_client("wikidata", candidates=[])   # returns nothing
    mock_sk = _make_client("songkick", available=False)
    mock_bit = _make_client("bandsintown", available=False)

    orc = Orchestrator(musicbrainz=mock_mb, wikidata=mock_wd, songkick=mock_sk, bandsintown=mock_bit)
    result = orc.verify("Linkin Park", datetime.date(2026, 6, 9), "Wien")

    assert result.status == VerifStatus.LIKELY
    assert "musicbrainz" in result.sources_confirmed
    assert "wikidata" not in result.sources_confirmed


# ---------------------------------------------------------------------------
# Test 5: UNVERIFIED when all clients return empty candidate lists
# ---------------------------------------------------------------------------

def test_verify_unverified_no_match():
    mock_mb = _make_client("musicbrainz", candidates=[])
    mock_wd = _make_client("wikidata", candidates=[])
    mock_sk = _make_client("songkick", available=False)
    mock_bit = _make_client("bandsintown", available=False)

    orc = Orchestrator(musicbrainz=mock_mb, wikidata=mock_wd, songkick=mock_sk, bandsintown=mock_bit)
    result = orc.verify("Unbekannte Band XYZ", datetime.date(2026, 1, 1), "Graz")

    assert result.status == VerifStatus.UNVERIFIED
    assert result.sources_confirmed == []
    assert result.best_match is None


# ---------------------------------------------------------------------------
# Test 6: sources_checked is populated for each available layer that responds
# ---------------------------------------------------------------------------

def test_verify_sources_checked_populated():
    cand = _high_score_candidate("musicbrainz")
    mock_mb = _make_client("musicbrainz", candidates=[cand])
    mock_wd = _make_client("wikidata", candidates=[])
    mock_sk = _make_client("songkick", available=False)   # unavailable → NOT in sources_checked
    mock_bit = _make_client("bandsintown", available=False)

    orc = Orchestrator(musicbrainz=mock_mb, wikidata=mock_wd, songkick=mock_sk, bandsintown=mock_bit)
    result = orc.verify("Linkin Park", datetime.date(2026, 6, 9), "Wien")

    assert "musicbrainz" in result.sources_checked
    assert "wikidata" in result.sources_checked
    assert "songkick" not in result.sources_checked
    assert "bandsintown" not in result.sources_checked


# ---------------------------------------------------------------------------
# Test 7: FAILED when every available layer raises an exception
# ---------------------------------------------------------------------------

def test_verify_failed_all_exceptions():
    mock_mb = _make_client("musicbrainz", raises=True)
    mock_wd = _make_client("wikidata", raises=True)
    mock_sk = _make_client("songkick", available=False)
    mock_bit = _make_client("bandsintown", available=False)

    orc = Orchestrator(musicbrainz=mock_mb, wikidata=mock_wd, songkick=mock_sk, bandsintown=mock_bit)
    result = orc.verify("Linkin Park", datetime.date(2026, 6, 9), "Wien")

    assert result.status == VerifStatus.FAILED
    assert result.sources_checked == []


# ---------------------------------------------------------------------------
# Test 8 (bonus): unavailable layers do not appear in sources_checked
# ---------------------------------------------------------------------------

def test_verify_unavailable_layers_not_in_sources_checked():
    mock_mb = _make_client("musicbrainz", available=False)
    mock_wd = _make_client("wikidata", available=False)
    mock_sk = _make_client("songkick", available=False)
    mock_bit = _make_client("bandsintown", available=False)

    orc = Orchestrator(musicbrainz=mock_mb, wikidata=mock_wd, songkick=mock_sk, bandsintown=mock_bit)
    result = orc.verify("Linkin Park", datetime.date(2026, 6, 9), "Wien")

    # All layers unavailable → treated like all failed (no sources_checked)
    assert result.sources_checked == []
    # Status should be FAILED (all_failed=True, sources_checked empty)
    assert result.status == VerifStatus.FAILED
