"""Tests for app/tabs/zeitplan.py — headless (no Tk display required)."""
import pytest


# ---------------------------------------------------------------------------
# Test 1: module imports without exception
# ---------------------------------------------------------------------------

def test_zeitplan_tab_imports_cleanly():
    """Importing zeitplan.py must not raise any exception."""
    import app.tabs.zeitplan  # noqa: F401


# ---------------------------------------------------------------------------
# Test 2: class exists
# ---------------------------------------------------------------------------

def test_zeitplan_tab_class_exists():
    from app.tabs.zeitplan import ZeitplanTab
    assert isinstance(ZeitplanTab, type)


# ---------------------------------------------------------------------------
# Test 3: build_launchd_config produces expected dict structure
# ---------------------------------------------------------------------------

def test_launchd_config_structure():
    from app.tabs.zeitplan import ZeitplanTab
    cfg = ZeitplanTab.build_launchd_config(
        label="com.willhaben.analyse",
        hour=3,
        minute=15,
        enabled=True,
    )
    assert "launchd" in cfg
    assert cfg["launchd"]["label"] == "com.willhaben.analyse"
    assert cfg["launchd"]["hour"] == 3
    assert cfg["launchd"]["minute"] == 15
    assert "schedule" in cfg
    assert cfg["schedule"]["enabled"] is True


# ---------------------------------------------------------------------------
# Test 4: build_launchd_config reflects disabled state
# ---------------------------------------------------------------------------

def test_launchd_config_disabled_state():
    from app.tabs.zeitplan import ZeitplanTab
    cfg = ZeitplanTab.build_launchd_config(
        label="com.test", hour=0, minute=0, enabled=False
    )
    assert cfg["schedule"]["enabled"] is False


# ---------------------------------------------------------------------------
# Test 5: build_launchd_config hour/minute boundaries
# ---------------------------------------------------------------------------

def test_launchd_config_boundary_values():
    from app.tabs.zeitplan import ZeitplanTab
    cfg = ZeitplanTab.build_launchd_config(
        label="com.test", hour=23, minute=59, enabled=True
    )
    assert cfg["launchd"]["hour"] == 23
    assert cfg["launchd"]["minute"] == 59
