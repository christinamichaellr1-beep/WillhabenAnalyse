"""Tests für die neuen CLI-Flags in main.py."""
import subprocess
import sys
from pathlib import Path


MAIN_PY = str(Path(__file__).resolve().parent.parent / "main.py")
# Use the currently-running Python so tests work regardless of venv location
VENV_PYTHON = sys.executable


def _run(*args, timeout=10):
    result = subprocess.run(
        [VENV_PYTHON, MAIN_PY] + list(args),
        capture_output=True, text=True, timeout=timeout
    )
    return result


def test_help_shows_new_flags():
    r = _run("--help")
    assert "--model" in r.stdout
    assert "--parser-version" in r.stdout
    assert "--test-batch" in r.stdout
    assert "--dry-run" in r.stdout


def test_existing_flags_still_present():
    r = _run("--help")
    assert "--gui" in r.stdout
    assert "--once" in r.stdout
    assert "--daemon" in r.stdout
    assert "--ovp" in r.stdout


def test_invalid_model_choice_errors():
    r = _run("--model", "unknown-model", "--once")
    assert r.returncode != 0


def test_invalid_parser_version_errors():
    r = _run("--parser-version", "v99", "--once")
    assert r.returncode != 0


def test_max_listings_in_help():
    """--max-listings muss in --help erscheinen."""
    r = _run("--help")
    assert "--max-listings" in r.stdout


def test_max_listings_invalid_type_errors():
    """--max-listings erwartet int; ein String-Wert muss einen Fehler verursachen."""
    r = _run("--max-listings", "notanumber", "--once")
    assert r.returncode != 0


# ---------------------------------------------------------------------------
# Unit-Tests für run_pipeline() max_listings ohne echtes Scraping
# ---------------------------------------------------------------------------

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))


def test_run_pipeline_max_listings_truncates(monkeypatch):
    """run_pipeline() soll ads[:max_listings] abschneiden bevor es parst."""
    import main as _main

    collected: dict = {}

    def _fake_scrape():
        # Gibt 5 Dummy-Anzeigen zurück
        return [{"id": str(i), "title": f"Ad {i}"} for i in range(5)]

    async def _fake_scrape_async():
        return _fake_scrape()

    def _fake_parse_ads(ads, **kwargs):
        collected["ads_count"] = len(ads)
        return []

    # Patch scrape
    import asyncio

    monkeypatch.setattr("main.asyncio.run", lambda coro: _fake_scrape())
    monkeypatch.setattr(
        "main._select_parse_ads",
        lambda version: _fake_parse_ads,
    )
    # Patch OVP and Excel to no-ops so pipeline doesn't crash
    import importlib, types

    ovp_mod = types.ModuleType("ovp.ovp_checker")
    ovp_mod.check_events = lambda events, log_fn=None: events  # type: ignore
    monkeypatch.setitem(sys.modules, "ovp.ovp_checker", ovp_mod)

    _main.run_pipeline(
        parser_version="v2",
        dry_run=True,
        max_listings=3,
    )

    assert collected.get("ads_count") == 3, (
        f"Erwartet 3 Anzeigen nach max_listings=3, aber got {collected.get('ads_count')}"
    )


def test_run_pipeline_without_max_listings_uses_all(monkeypatch):
    """Ohne --max-listings werden alle Anzeigen geparst."""
    import main as _main

    collected: dict = {}

    def _fake_scrape():
        return [{"id": str(i), "title": f"Ad {i}"} for i in range(7)]

    def _fake_parse_ads(ads, **kwargs):
        collected["ads_count"] = len(ads)
        return []

    monkeypatch.setattr("main.asyncio.run", lambda coro: _fake_scrape())
    monkeypatch.setattr("main._select_parse_ads", lambda version: _fake_parse_ads)

    import types
    ovp_mod = types.ModuleType("ovp.ovp_checker")
    ovp_mod.check_events = lambda events, log_fn=None: events  # type: ignore
    monkeypatch.setitem(sys.modules, "ovp.ovp_checker", ovp_mod)

    _main.run_pipeline(parser_version="v2", dry_run=True, max_listings=None)

    assert collected.get("ads_count") == 7
