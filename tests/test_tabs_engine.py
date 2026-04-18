"""Tests for app/tabs/engine.py — headless (no Tk display required)."""
import sys
import os
import importlib

import pytest


# ---------------------------------------------------------------------------
# Test 1: module imports without exception
# ---------------------------------------------------------------------------

def test_engine_tab_imports_cleanly():
    """Importing engine.py must not raise any exception."""
    import app.tabs.engine  # noqa: F401 — just testing the import


# ---------------------------------------------------------------------------
# Test 2: class exists and is a type
# ---------------------------------------------------------------------------

def test_engine_tab_class_exists():
    from app.tabs.engine import EngineTab
    assert isinstance(EngineTab, type)


# ---------------------------------------------------------------------------
# Test 3: compute_max_listings returns None for "Alle"
# ---------------------------------------------------------------------------

def test_engine_tab_max_listings_none_when_alle():
    from app.tabs.engine import EngineTab
    assert EngineTab.compute_max_listings("Alle") is None


# ---------------------------------------------------------------------------
# Test 4: compute_max_listings returns int for numeric string
# ---------------------------------------------------------------------------

def test_engine_tab_max_listings_int_for_number():
    from app.tabs.engine import EngineTab
    result = EngineTab.compute_max_listings("200")
    assert result == 200
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Test 5: compute_max_listings strips whitespace
# ---------------------------------------------------------------------------

def test_engine_tab_max_listings_strips_whitespace():
    from app.tabs.engine import EngineTab
    assert EngineTab.compute_max_listings("  Alle  ") is None
    assert EngineTab.compute_max_listings("  50  ") == 50
