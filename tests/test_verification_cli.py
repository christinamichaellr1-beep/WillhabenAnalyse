"""Tests for verification/verify_excel.py (Phase 6 CLI)."""
from __future__ import annotations
import datetime
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

from export.excel_writer import MAIN_FIELDS, MAIN_HEADERS, SHEET_HAUPT, _write_header
from verification.orchestrator import VerifStatus, VerificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xlsx(path: Path, rows: list[dict]) -> None:
    """Create a minimal Hauptuebersicht xlsx with the given data rows."""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_HAUPT
    _write_header(ws, MAIN_HEADERS)
    for row in rows:
        ws.append([row.get(f, "") for f in MAIN_FIELDS])
    wb.save(path)


def _make_result(status: VerifStatus) -> VerificationResult:
    return VerificationResult(
        status=status,
        best_match=None,
        sources_checked=[],
        sources_confirmed=[],
        verif_datum=datetime.date.today().isoformat(),
    )


# ---------------------------------------------------------------------------
# Test 1: missing Excel returns {}
# ---------------------------------------------------------------------------

def test_run_returns_empty_if_excel_missing(tmp_path):
    """run() must return {} when the Excel file does not exist."""
    from verification.verify_excel import run

    missing = tmp_path / "does_not_exist.xlsx"
    db = tmp_path / "cache.db"

    result = run(excel_path=missing, db_path=db, dry_run=True)

    assert result == {}


# ---------------------------------------------------------------------------
# Test 2: dry_run does not write to Excel
# ---------------------------------------------------------------------------

def test_run_dry_run_does_not_write_excel(tmp_path):
    """With dry_run=True, write_verif_result must not be called."""
    from verification.verify_excel import run

    xlsx = tmp_path / "test.xlsx"
    db = tmp_path / "cache.db"

    _make_xlsx(xlsx, [
        {
            "willhaben_id": "42",
            "event_name": "Coldplay Wien",
            "event_datum": "2026-07-15",
            "stadt": "Wien",
        }
    ])

    mock_result = _make_result(VerifStatus.LIKELY)

    with (
        patch("verification.verify_excel.Orchestrator") as MockOrch,
        patch("verification.verify_excel.write_verif_result") as mock_write,
    ):
        MockOrch.return_value.verify.return_value = mock_result

        stats = run(excel_path=xlsx, db_path=db, dry_run=True, force=True)

    mock_write.assert_not_called()
    assert stats["total"] == 1


# ---------------------------------------------------------------------------
# Test 3: cached result bypasses orchestrator.verify
# ---------------------------------------------------------------------------

def test_run_uses_cache(tmp_path):
    """If a valid cache entry exists, orchestrator.verify must not be called."""
    from verification.verify_excel import run
    from verification.cache import VerificationCache

    xlsx = tmp_path / "test.xlsx"
    db = tmp_path / "cache.db"

    event_name = "Linkin Park Wien"
    event_datum = datetime.date(2026, 6, 9)

    _make_xlsx(xlsx, [
        {
            "willhaben_id": "99",
            "event_name": event_name,
            "event_datum": event_datum.isoformat(),
            "stadt": "Wien",
        }
    ])

    # Pre-populate the cache
    cache = VerificationCache(db_path=db, ttl_days=7)
    cached_result = _make_result(VerifStatus.VERIFIED)
    cache.put(event_name, event_datum, cached_result)

    with (
        patch("verification.verify_excel.Orchestrator") as MockOrch,
        patch("verification.verify_excel.write_verif_result"),
        patch("verification.verify_excel.rebuild_nicht_verifiziert_sheet", return_value=0),
    ):
        stats = run(
            excel_path=xlsx,
            db_path=db,
            dry_run=False,
            force=False,
        )

    # verify() must never have been called because the cache hit
    MockOrch.return_value.verify.assert_not_called()
    assert stats["cached"] == 1


# ---------------------------------------------------------------------------
# Test 4: stats counted correctly (1 cached + 1 newly verified)
# ---------------------------------------------------------------------------

def test_run_stats_counted_correctly(tmp_path):
    """Two rows: one cached (nicht_verifiziert), one live-verified (wahrscheinlich)."""
    from verification.verify_excel import run
    from verification.cache import VerificationCache

    xlsx = tmp_path / "test.xlsx"
    db = tmp_path / "cache.db"

    cached_name = "Rammstein Graz"
    cached_datum = datetime.date(2026, 8, 1)
    live_name = "Ed Sheeran Wien"
    live_datum = datetime.date(2026, 9, 20)

    _make_xlsx(xlsx, [
        {
            "willhaben_id": "1",
            "event_name": cached_name,
            "event_datum": cached_datum.isoformat(),
            "stadt": "Graz",
        },
        {
            "willhaben_id": "2",
            "event_name": live_name,
            "event_datum": live_datum.isoformat(),
            "stadt": "Wien",
        },
    ])

    # Pre-populate cache for the first row only
    cache = VerificationCache(db_path=db, ttl_days=7)
    cache.put(cached_name, cached_datum, _make_result(VerifStatus.UNVERIFIED))

    live_result = _make_result(VerifStatus.LIKELY)

    with (
        patch("verification.verify_excel.Orchestrator") as MockOrch,
        patch("verification.verify_excel.write_verif_result"),
        patch("verification.verify_excel.rebuild_nicht_verifiziert_sheet", return_value=1),
    ):
        MockOrch.return_value.verify.return_value = live_result

        stats = run(
            excel_path=xlsx,
            db_path=db,
            dry_run=False,
            force=False,
        )

    assert stats["total"] == 2
    assert stats["cached"] == 1
    # cached row was nicht_verifiziert, live row was wahrscheinlich
    assert stats["nicht_verifiziert"] == 1
    assert stats["wahrscheinlich"] == 1
    # orchestrator called exactly once (for the non-cached row)
    MockOrch.return_value.verify.assert_called_once()
