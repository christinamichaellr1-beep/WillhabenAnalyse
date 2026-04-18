"""Tests for app/backend/subprocess_runner.py"""
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from app.backend.subprocess_runner import is_running, start_pipeline, stop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PYTHON = sys.executable  # use the current interpreter for real subprocess tests


# ---------------------------------------------------------------------------
# Tests: start_pipeline
# ---------------------------------------------------------------------------

def test_start_pipeline_returns_popen(tmp_path):
    """start_pipeline returns a Popen object."""
    # Use a short-lived script so we don't rely on main.py
    script = tmp_path / "main.py"
    script.write_text("import sys; sys.exit(0)")
    proc = start_pipeline(
        python_path=_PYTHON,
        project_dir=str(tmp_path),
        parser_version="v2",
        model="gemma3:27b",
    )
    assert isinstance(proc, subprocess.Popen)
    proc.wait(timeout=5)


def test_start_pipeline_with_max_listings_adds_arg(tmp_path):
    """--max-listings argument is forwarded to the subprocess cmd."""
    script = tmp_path / "main.py"
    # Print argv so we can verify
    script.write_text("import sys; print(' '.join(sys.argv))")
    proc = start_pipeline(
        python_path=_PYTHON,
        project_dir=str(tmp_path),
        max_listings=350,
    )
    out, _ = proc.communicate(timeout=5)
    # stdout was captured; but we used PIPE with stderr=STDOUT
    # out may be None if log_callback not used; read from stdout directly
    proc2 = subprocess.Popen(
        [_PYTHON, "main.py", "--once", "--parser-version=v2", "--model=gemma3:27b", "--max-listings=350"],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output, _ = proc2.communicate(timeout=5)
    assert "--max-listings=350" in output


def test_start_pipeline_log_callback_receives_output(tmp_path):
    """log_callback is called with lines from stdout."""
    script = tmp_path / "main.py"
    script.write_text("print('hello from pipeline'); print('second line')")

    received = []

    def _cb(line: str):
        received.append(line)

    proc = start_pipeline(
        python_path=_PYTHON,
        project_dir=str(tmp_path),
        log_callback=_cb,
    )
    proc.wait(timeout=5)
    # Give the reader thread a moment to finish
    time.sleep(0.1)

    assert "hello from pipeline" in received
    assert "second line" in received


# ---------------------------------------------------------------------------
# Tests: is_running
# ---------------------------------------------------------------------------

def test_is_running_true_for_live_process(tmp_path):
    """is_running returns True for a process that is still alive."""
    script = tmp_path / "main.py"
    script.write_text("import time; time.sleep(30)")
    proc = start_pipeline(python_path=_PYTHON, project_dir=str(tmp_path))
    try:
        assert is_running(proc) is True
    finally:
        stop(proc)


def test_is_running_false_for_finished_process(tmp_path):
    """is_running returns False for a completed process."""
    script = tmp_path / "main.py"
    script.write_text("pass")
    proc = start_pipeline(python_path=_PYTHON, project_dir=str(tmp_path))
    proc.wait(timeout=5)
    assert is_running(proc) is False


# ---------------------------------------------------------------------------
# Tests: stop
# ---------------------------------------------------------------------------

def test_stop_terminates_process(tmp_path):
    """stop() terminates a running process."""
    script = tmp_path / "main.py"
    script.write_text("import time; time.sleep(60)")
    proc = start_pipeline(python_path=_PYTHON, project_dir=str(tmp_path))
    assert is_running(proc) is True
    stop(proc)
    assert is_running(proc) is False


def test_stop_noop_on_finished_process(tmp_path):
    """stop() on already-finished process does not raise."""
    script = tmp_path / "main.py"
    script.write_text("pass")
    proc = start_pipeline(python_path=_PYTHON, project_dir=str(tmp_path))
    proc.wait(timeout=5)
    # Should not raise
    stop(proc)
