"""Tests for app/backend/launchd_manager.py"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.backend.launchd_manager import (
    generate_plist,
    install_plist,
    is_installed,
    uninstall_plist,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_KWARGS = dict(
    label="com.willhaben.analyse",
    python_path="/path/to/.venv/bin/python3",
    project_dir="/Users/Boti/WillhabenAnalyse",
    model="gemma3:27b",
    max_listings=None,
    hour=2,
    minute=0,
)


# ---------------------------------------------------------------------------
# Tests: generate_plist
# ---------------------------------------------------------------------------

def test_generate_plist_contains_label():
    xml = generate_plist(**_SAMPLE_KWARGS)
    assert "com.willhaben.analyse" in xml


def test_generate_plist_contains_python_path():
    xml = generate_plist(**_SAMPLE_KWARGS)
    assert "/path/to/.venv/bin/python3" in xml


def test_generate_plist_with_max_listings():
    kwargs = {**_SAMPLE_KWARGS, "max_listings": 350}
    xml = generate_plist(**kwargs)
    assert "--max-listings=350" in xml


def test_generate_plist_without_max_listings_omits_arg():
    xml = generate_plist(**_SAMPLE_KWARGS)
    assert "--max-listings" not in xml


def test_generate_plist_contains_hour_and_minute():
    kwargs = {**_SAMPLE_KWARGS, "hour": 3, "minute": 30}
    xml = generate_plist(**kwargs)
    assert "<integer>3</integer>" in xml
    assert "<integer>30</integer>" in xml


def test_generate_plist_contains_project_dir():
    xml = generate_plist(**_SAMPLE_KWARGS)
    assert "/Users/Boti/WillhabenAnalyse" in xml


def test_generate_plist_contains_model():
    xml = generate_plist(**_SAMPLE_KWARGS)
    assert "gemma3:27b" in xml


def test_generate_plist_is_valid_xml_structure():
    xml = generate_plist(**_SAMPLE_KWARGS)
    assert xml.strip().startswith("<?xml")
    assert "<plist" in xml
    assert "</plist>" in xml


# ---------------------------------------------------------------------------
# Tests: is_installed
# ---------------------------------------------------------------------------

def test_is_installed_false_when_missing(tmp_path):
    with patch("app.backend.launchd_manager._LAUNCH_AGENTS_DIR", tmp_path):
        assert is_installed("com.willhaben.analyse") is False


def test_is_installed_true_when_file_exists(tmp_path):
    plist_path = tmp_path / "com.willhaben.analyse.plist"
    plist_path.write_text("<plist/>")
    with patch("app.backend.launchd_manager._LAUNCH_AGENTS_DIR", tmp_path):
        assert is_installed("com.willhaben.analyse") is True


# ---------------------------------------------------------------------------
# Tests: install_plist (mocked launchctl)
# ---------------------------------------------------------------------------

def test_install_plist_success(tmp_path):
    fake_result = MagicMock()
    fake_result.returncode = 0
    with patch("app.backend.launchd_manager._LAUNCH_AGENTS_DIR", tmp_path), \
         patch("subprocess.run", return_value=fake_result):
        ok, msg = install_plist("<plist/>", "com.willhaben.test")
        assert ok is True
        assert (tmp_path / "com.willhaben.test.plist").exists()


def test_install_plist_failure_on_launchctl_error(tmp_path):
    fake_result = MagicMock()
    fake_result.returncode = 1
    fake_result.stderr = "Permission denied"
    fake_result.stdout = ""
    with patch("app.backend.launchd_manager._LAUNCH_AGENTS_DIR", tmp_path), \
         patch("subprocess.run", return_value=fake_result):
        ok, msg = install_plist("<plist/>", "com.willhaben.test")
        assert ok is False
        assert "Permission denied" in msg


# ---------------------------------------------------------------------------
# Tests: uninstall_plist (mocked launchctl)
# ---------------------------------------------------------------------------

def test_uninstall_plist_not_found(tmp_path):
    with patch("app.backend.launchd_manager._LAUNCH_AGENTS_DIR", tmp_path):
        ok, msg = uninstall_plist("com.willhaben.notexist")
        assert ok is False
        assert "not found" in msg.lower() or "Plist not found" in msg


def test_generate_plist_injection_in_label_is_safe():
    """Malicious label value must not inject XML tags (C02 fix)."""
    kwargs = {**_SAMPLE_KWARGS, "label": "</string><string>/bin/bash"}
    xml = generate_plist(**kwargs)
    # plistlib escapes < and > — the injected tag must not appear verbatim
    assert "</string><string>/bin/bash" not in xml
    # The label value IS present but safely escaped
    assert "/bin/bash" in xml or "&lt;" in xml


def test_generate_plist_injection_in_python_path_is_safe():
    """Malicious python_path must not inject extra ProgramArguments (C02 fix)."""
    kwargs = {**_SAMPLE_KWARGS, "python_path": "</string><string>-c<string>rm -rf /"}
    xml = generate_plist(**kwargs)
    assert "rm -rf /" not in xml or "&lt;" in xml
