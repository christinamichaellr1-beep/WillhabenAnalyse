"""
status_monitor.py

Reads BASE_DIR/.willhaben_status.json and provides helper functions
for interpreting pipeline run status.
"""
import json
from pathlib import Path


def read_status(base_dir: Path) -> dict | None:
    """Returns parsed status dict or None if file missing/invalid."""
    status_file = base_dir / ".willhaben_status.json"
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def is_running(status: dict) -> bool:
    """True if status['status'] == 'running'"""
    return status.get("status") == "running"


def format_progress(status: dict) -> str:
    """Returns human-readable progress string like '42/350 (12%)'"""
    current = status.get("current", 0)
    total = status.get("total", 0)
    if total and total > 0:
        pct = int(current / total * 100)
    else:
        pct = 0
    return f"{current}/{total} ({pct}%)"


def avg_duration_ms(status: dict) -> float | None:
    """Average of last_10_durations, or None if empty."""
    durations = status.get("last_10_durations", [])
    if not durations:
        return None
    return sum(durations) / len(durations)
