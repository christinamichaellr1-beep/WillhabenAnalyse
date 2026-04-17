"""Tests for app/backend/status_monitor.py"""
import json
from pathlib import Path

import pytest

from app.backend.status_monitor import (
    avg_duration_ms,
    format_progress,
    is_running,
    read_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_status(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / ".willhaben_status.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _sample_status(**overrides) -> dict:
    base = {
        "run_id": "abc-123",
        "status": "running",
        "total": 350,
        "current": 42,
        "last_10_durations": [100, 200, 300],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests: read_status
# ---------------------------------------------------------------------------

def test_read_status_returns_none_when_missing(tmp_path):
    result = read_status(tmp_path)
    assert result is None


def test_read_status_parses_valid_json(tmp_path):
    data = _sample_status()
    _write_status(tmp_path, data)
    result = read_status(tmp_path)
    assert result is not None
    assert result["run_id"] == "abc-123"
    assert result["total"] == 350


def test_read_status_returns_none_on_invalid_json(tmp_path):
    p = tmp_path / ".willhaben_status.json"
    p.write_text("NOT VALID JSON {{{", encoding="utf-8")
    result = read_status(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Tests: is_running
# ---------------------------------------------------------------------------

def test_is_running_true_when_running():
    status = _sample_status(status="running")
    assert is_running(status) is True


def test_is_running_false_when_done():
    status = _sample_status(status="done")
    assert is_running(status) is False


def test_is_running_false_when_error():
    status = _sample_status(status="error")
    assert is_running(status) is False


# ---------------------------------------------------------------------------
# Tests: format_progress
# ---------------------------------------------------------------------------

def test_format_progress_correct_format():
    status = _sample_status(current=42, total=350)
    result = format_progress(status)
    assert result == "42/350 (12%)"


def test_format_progress_zero_total():
    status = _sample_status(current=0, total=0)
    result = format_progress(status)
    assert result == "0/0 (0%)"


def test_format_progress_complete():
    status = _sample_status(current=100, total=100)
    result = format_progress(status)
    assert result == "100/100 (100%)"


# ---------------------------------------------------------------------------
# Tests: avg_duration_ms
# ---------------------------------------------------------------------------

def test_avg_duration_returns_none_on_empty():
    status = _sample_status(last_10_durations=[])
    assert avg_duration_ms(status) is None


def test_avg_duration_returns_correct_average():
    status = _sample_status(last_10_durations=[100, 200, 300])
    result = avg_duration_ms(status)
    assert result == pytest.approx(200.0)


def test_avg_duration_single_value():
    status = _sample_status(last_10_durations=[500])
    result = avg_duration_ms(status)
    assert result == pytest.approx(500.0)
