"""Tests for app/tabs/status.py — headless (no Tk display required)."""
import pytest


# ---------------------------------------------------------------------------
# Test 1: module imports without exception
# ---------------------------------------------------------------------------

def test_status_tab_imports_cleanly():
    """Importing status.py must not raise any exception."""
    import app.tabs.status  # noqa: F401


# ---------------------------------------------------------------------------
# Test 2: class exists
# ---------------------------------------------------------------------------

def test_status_tab_class_exists():
    from app.tabs.status import StatusTab
    assert isinstance(StatusTab, type)


# ---------------------------------------------------------------------------
# Test 3: status_to_display with None returns safe defaults
# ---------------------------------------------------------------------------

def test_refresh_with_none_status():
    from app.tabs.status import StatusTab
    result = StatusTab.status_to_display(None)
    assert result["progress"] == "Kein Status verfügbar"
    assert result["status_color"] == "gray"
    assert result["last_error"] == ""


# ---------------------------------------------------------------------------
# Test 4: status_to_display with running status
# ---------------------------------------------------------------------------

def test_status_to_display_running():
    from app.tabs.status import StatusTab
    # Use real StatusWriter field name "errors_count" (not "errors") — C05 fix
    status = {
        "status": "running",
        "current": 42,
        "total": 350,
        "model": "gemma3:27b",
        "errors_count": 1,
        "last_error": "some error",
        "last_10_durations": [100, 200, 300],
    }
    result = StatusTab.status_to_display(status)
    assert result["status_text"] == "running"
    assert result["status_color"] == "green"
    assert result["progress"] == "42/350 (12%)"
    assert result["model"] == "gemma3:27b"
    assert result["errors"] == "1"
    assert result["last_error"] == "some error"
    assert "200" in result["avg_duration"]  # avg of 100,200,300 = 200


# ---------------------------------------------------------------------------
# Test 5: status_to_display with error status
# ---------------------------------------------------------------------------

def test_status_to_display_error():
    from app.tabs.status import StatusTab
    status = {
        "status": "error",
        "current": 5,
        "total": 100,
        "errors_count": 3,
        "last_10_durations": [],
    }
    result = StatusTab.status_to_display(status)
    assert result["status_color"] == "red"
    assert result["avg_duration"] == "—"


# ---------------------------------------------------------------------------
# Test 6: status_to_display with done status
# ---------------------------------------------------------------------------

def test_status_to_display_done():
    from app.tabs.status import StatusTab
    status = {
        "status": "done",
        "current": 100,
        "total": 100,
        "errors_count": 0,
        "last_10_durations": [500],
    }
    result = StatusTab.status_to_display(status)
    assert result["status_color"] == "blue"
    assert result["status_text"] == "done"
