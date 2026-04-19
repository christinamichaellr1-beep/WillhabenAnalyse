"""Tests for verification/cache.py — SQLite-backed VerificationCache."""
from __future__ import annotations
import datetime
import tempfile
from pathlib import Path

import pytest

from verification.orchestrator import VerifStatus, VerificationResult
from verification.cache import VerificationCache


def _make_result(status: str = "nicht_verifiziert") -> VerificationResult:
    return VerificationResult(
        status=VerifStatus(status),
        sources_checked=["mb"],
        verif_datum="2026-04-19",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cache(tmp: str, ttl_days: int = 7) -> VerificationCache:
    """Create a VerificationCache backed by a temp directory."""
    return VerificationCache(db_path=Path(tmp) / "cache.db", ttl_days=ttl_days)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_returns_none_if_empty():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        assert cache.get("Taylor Swift") is None


def test_put_and_get_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        result = _make_result("verifiziert")
        cache.put("Taylor Swift", datetime.date(2026, 6, 1), result)
        got = cache.get("Taylor Swift", datetime.date(2026, 6, 1))
        assert got is not None
        assert got.status == VerifStatus.VERIFIED
        assert got.sources_checked == ["mb"]


def test_get_returns_none_after_expiry():
    with tempfile.TemporaryDirectory() as tmp:
        # ttl_days=0 means anything cached before today is expired.
        # We manually insert with yesterday's date to guarantee expiry.
        cache = _cache(tmp, ttl_days=0)
        result = _make_result()
        cache.put("Expired Event", None, result)
        # With ttl_days=0 the cutoff is today; cached_at == today so it is
        # NOT strictly less than cutoff → still valid.  Force a past date.
        import sqlite3
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        with sqlite3.connect(cache.db_path) as conn:
            conn.execute(
                "UPDATE verif_cache SET cached_at=? WHERE event_name_key=?",
                (yesterday, "expired event"),
            )
        assert cache.get("Expired Event") is None


def test_put_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        cache.put("Rammstein", None, _make_result("nicht_verifiziert"))
        cache.put("Rammstein", None, _make_result("verifiziert"))
        got = cache.get("Rammstein")
        assert got is not None
        assert got.status == VerifStatus.VERIFIED


def test_invalidate_removes_entry():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        cache.put("Metallica", datetime.date(2026, 7, 4), _make_result())
        cache.invalidate("Metallica", datetime.date(2026, 7, 4))
        assert cache.get("Metallica", datetime.date(2026, 7, 4)) is None


def test_purge_expired_returns_count():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp, ttl_days=7)
        cache.put("Event A", None, _make_result())
        cache.put("Event B", datetime.date(2026, 5, 1), _make_result())
        # Back-date both entries so they are expired
        import sqlite3
        old_date = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        with sqlite3.connect(cache.db_path) as conn:
            conn.execute("UPDATE verif_cache SET cached_at=?", (old_date,))
        count = cache.purge_expired()
        assert count == 2


def test_key_normalization():
    with tempfile.TemporaryDirectory() as tmp:
        cache = _cache(tmp)
        cache.put("Taylor Swift", None, _make_result("wahrscheinlich"))
        # Trailing space and different case should hit the same cache entry
        got = cache.get("Taylor Swift ", None)
        assert got is not None
        assert got.status == VerifStatus.LIKELY
