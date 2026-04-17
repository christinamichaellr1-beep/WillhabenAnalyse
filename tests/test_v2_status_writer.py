"""Tests für parser/v2/status_writer.py"""
import json
from pathlib import Path

import pytest

from parser.v2.status_writer import StatusWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_writer(tmp_path: Path, total: int = 10, model: str = "gemma3:27b") -> tuple[StatusWriter, Path]:
    status_file = tmp_path / ".willhaben_status.json"
    writer = StatusWriter(total=total, model=model, _status_file=status_file)
    return writer, status_file


def _read(status_file: Path) -> dict:
    return json.loads(status_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_status_file_created_with_correct_schema(tmp_path):
    """Nach Initialisierung muss die Datei existieren und alle Pflichtfelder haben."""
    writer, status_file = _make_writer(tmp_path, total=100, model="gemma3:27b")

    assert status_file.exists(), "Status-Datei wurde nicht erstellt"
    data = _read(status_file)

    assert "run_id" in data
    assert "started_at" in data
    assert data["model"] == "gemma3:27b"
    assert data["total"] == 100
    assert data["current"] == 0
    assert data["current_id"] is None
    assert data["current_title"] is None
    assert data["last_10_durations"] == []
    assert data["errors_count"] == 0
    assert data["last_error"] is None
    assert data["status"] == "running"


def test_update_increments_current_and_sets_fields(tmp_path):
    """update() setzt current, current_id und current_title korrekt."""
    writer, status_file = _make_writer(tmp_path, total=5)

    writer.update(current=1, ad_id="abc123", title="Taylor Swift Tickets")
    data = _read(status_file)

    assert data["current"] == 1
    assert data["current_id"] == "abc123"
    assert data["current_title"] == "Taylor Swift Tickets"


def test_update_multiple_times_current_advances(tmp_path):
    """Mehrfache update()-Aufrufe aktualisieren den Zähler sequenziell."""
    writer, status_file = _make_writer(tmp_path, total=5)

    for i in range(1, 4):
        writer.update(current=i, ad_id=f"id{i}", title=f"Ad {i}")

    data = _read(status_file)
    assert data["current"] == 3
    assert data["current_id"] == "id3"


def test_last_10_durations_ring_buffer(tmp_path):
    """last_10_durations hält maximal 10 Werte; ältere werden verdrängt."""
    writer, status_file = _make_writer(tmp_path, total=15)

    for i in range(12):
        writer.update(current=i + 1, ad_id=f"id{i}", title=f"Ad {i}", duration_ms=(i + 1) * 100)

    data = _read(status_file)
    durations = data["last_10_durations"]

    assert len(durations) == 10, f"Erwartet 10 Werte, got {len(durations)}"
    # Die ersten zwei Werte (100, 200) müssen verdrängt sein
    assert 100 not in durations
    assert 200 not in durations
    # Der letzte Wert (1200) muss vorhanden sein
    assert 1200 in durations


def test_error_increments_errors_count(tmp_path):
    """error() inkrementiert errors_count und setzt last_error."""
    writer, status_file = _make_writer(tmp_path)

    writer.error("Timeout beim Ollama-Aufruf")
    data = _read(status_file)
    assert data["errors_count"] == 1
    assert data["last_error"] == "Timeout beim Ollama-Aufruf"
    assert data["status"] == "running"  # Status bleibt running

    writer.error("Noch ein Fehler")
    data = _read(status_file)
    assert data["errors_count"] == 2
    assert data["last_error"] == "Noch ein Fehler"


def test_finish_sets_status_done(tmp_path):
    """finish() setzt status='done'."""
    writer, status_file = _make_writer(tmp_path)

    writer.update(current=5, ad_id="xyz", title="Konzert")
    writer.finish()

    data = _read(status_file)
    assert data["status"] == "done"


def test_fail_sets_status_error_and_last_error(tmp_path):
    """fail() setzt status='error' und last_error."""
    writer, status_file = _make_writer(tmp_path)

    writer.fail("Kritischer Verbindungsfehler")

    data = _read(status_file)
    assert data["status"] == "error"
    assert data["last_error"] == "Kritischer Verbindungsfehler"


def test_run_id_is_uuid_string(tmp_path):
    """run_id soll ein gültiger UUID4-String sein."""
    import uuid
    writer, status_file = _make_writer(tmp_path)
    data = _read(status_file)
    # Muss ohne Exception parsebar sein
    parsed = uuid.UUID(data["run_id"])
    assert parsed.version == 4


def test_custom_run_id_is_preserved(tmp_path):
    """Wenn run_id explizit übergeben, wird er nicht überschrieben."""
    status_file = tmp_path / ".willhaben_status.json"
    writer = StatusWriter(total=1, model="gemma3:27b", run_id="my-fixed-id", _status_file=status_file)
    data = _read(status_file)
    assert data["run_id"] == "my-fixed-id"


def test_atomic_write_no_tmp_file_left(tmp_path):
    """Nach dem Schreiben darf keine .tmp-Datei übrig bleiben."""
    writer, status_file = _make_writer(tmp_path)
    tmp_file = status_file.with_suffix(".json.tmp")
    assert not tmp_file.exists(), "Temporäre Datei wurde nicht umbenannt/gelöscht"
