"""Tests for app/tabs/dashboard.py — headless (no Tk display required)."""
import pytest


# ---------------------------------------------------------------------------
# Test 1: module imports without exception
# ---------------------------------------------------------------------------

def test_dashboard_tab_imports_cleanly():
    """Importing dashboard.py must not raise any exception."""
    import app.tabs.dashboard  # noqa: F401


# ---------------------------------------------------------------------------
# Test 2: class exists
# ---------------------------------------------------------------------------

def test_dashboard_tab_class_exists():
    from app.tabs.dashboard import DashboardTab
    assert isinstance(DashboardTab, type)


# ---------------------------------------------------------------------------
# Test 3: filter_df with empty DataFrame does not crash
# ---------------------------------------------------------------------------

def test_apply_filters_with_empty_df():
    from app.tabs.dashboard import DashboardTab
    from app.backend.dashboard_aggregator import aggregate
    import pandas as pd

    empty_df = pd.DataFrame()
    aggregated = aggregate(empty_df)
    result = DashboardTab.filter_df(aggregated)
    # Should return the empty aggregated DataFrame without crashing
    assert result is not None
    assert result.empty


# ---------------------------------------------------------------------------
# Test 4: filter_df with None does not crash
# ---------------------------------------------------------------------------

def test_apply_filters_with_none():
    from app.tabs.dashboard import DashboardTab
    result = DashboardTab.filter_df(None)
    assert result is None


# ---------------------------------------------------------------------------
# Test 5: filter_df text search is case-insensitive
# ---------------------------------------------------------------------------

def test_apply_filters_case_insensitive_search():
    from app.tabs.dashboard import DashboardTab
    import pandas as pd

    df = pd.DataFrame({
        "Event": ["Linkin Park Wien", "Rammstein Graz", "Metallica Wien"],
        "Kategorie": ["Rock", "Metal", "Metal"],
        "Datum": [None, None, None],
        "Venue": [None, None, None],
        "Stadt": ["Wien", "Graz", "Wien"],
        "Privat_Anzahl": [0, 0, 0],
        "Privat_Min": [0.0, 0.0, 0.0],
        "Privat_Avg": [0.0, 0.0, 0.0],
        "Privat_Max": [0.0, 0.0, 0.0],
        "Haendler_Anzahl": [0, 0, 0],
        "Haendler_Min": [0.0, 0.0, 0.0],
        "Haendler_Avg": [0.0, 0.0, 0.0],
        "Haendler_Max": [0.0, 0.0, 0.0],
        "OVP": [0.0, 0.0, 0.0],
        "Marge_Haendler_Pct": [0.0, 0.0, 0.0],
        "Marge_Privat_Pct": [0.0, 0.0, 0.0],
    })

    result = DashboardTab.filter_df(df, search="linkin")
    assert len(result) == 1
    assert "Linkin Park Wien" in result["Event"].values


# ---------------------------------------------------------------------------
# Test 6: filter_df sort column works
# ---------------------------------------------------------------------------

def test_apply_filters_sort_by_event():
    from app.tabs.dashboard import DashboardTab
    import pandas as pd

    df = pd.DataFrame({
        "Event": ["Rammstein", "Linkin Park", "Metallica"],
        "Kategorie": ["", "", ""],
        "Datum": [None, None, None],
        "Venue": [None, None, None],
        "Stadt": [None, None, None],
        "Privat_Anzahl": [0, 0, 0],
        "Privat_Min": [0.0, 0.0, 0.0],
        "Privat_Avg": [0.0, 0.0, 0.0],
        "Privat_Max": [0.0, 0.0, 0.0],
        "Haendler_Anzahl": [0, 0, 0],
        "Haendler_Min": [0.0, 0.0, 0.0],
        "Haendler_Avg": [0.0, 0.0, 0.0],
        "Haendler_Max": [0.0, 0.0, 0.0],
        "OVP": [0.0, 0.0, 0.0],
        "Marge_Haendler_Pct": [0.0, 0.0, 0.0],
        "Marge_Privat_Pct": [0.0, 0.0, 0.0],
    })

    result = DashboardTab.filter_df(df, sort_col="Event")
    events = list(result["Event"].values)
    assert events == sorted(events)
