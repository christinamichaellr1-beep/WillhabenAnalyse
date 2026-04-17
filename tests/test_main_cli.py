"""Tests für die neuen CLI-Flags in main.py."""
import subprocess
import sys
from pathlib import Path


MAIN_PY = str(Path(__file__).resolve().parent.parent / "main.py")
VENV_PYTHON = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python3")


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
