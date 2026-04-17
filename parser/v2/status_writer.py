"""
StatusWriter — schreibt eine JSON-Heartbeat-Datei während des Parsing-Laufs.
Datei: BASE_DIR/.willhaben_status.json
Schreibt atomar: erst .tmp, dann rename.
"""
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATUS_FILE = BASE_DIR / ".willhaben_status.json"


class StatusWriter:
    def __init__(
        self,
        total: int,
        model: str,
        run_id: str | None = None,
        _status_file: Path | None = None,
    ) -> None:
        self._file = _status_file or STATUS_FILE
        self._state: dict = {
            "run_id": run_id or str(uuid.uuid4()),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "total": total,
            "current": 0,
            "current_id": None,
            "current_title": None,
            "last_10_durations": [],
            "errors_count": 0,
            "last_error": None,
            "status": "running",
        }
        self._durations: deque[int] = deque(maxlen=10)
        self._write()

    # ------------------------------------------------------------------
    def update(
        self,
        current: int,
        ad_id: str,
        title: str,
        duration_ms: int | None = None,
    ) -> None:
        self._state["current"] = current
        self._state["current_id"] = ad_id
        self._state["current_title"] = title
        if duration_ms is not None:
            self._durations.append(duration_ms)
            self._state["last_10_durations"] = list(self._durations)
        self._write()

    def error(self, msg: str) -> None:
        """Inkrementiert errors_count, setzt last_error (Status bleibt 'running')."""
        self._state["errors_count"] += 1
        self._state["last_error"] = msg
        self._write()

    def finish(self) -> None:
        """Setzt status='done'."""
        self._state["status"] = "done"
        self._write()

    def fail(self, msg: str) -> None:
        """Setzt status='error' und last_error."""
        self._state["status"] = "error"
        self._state["last_error"] = msg
        self._write()

    # ------------------------------------------------------------------
    def _write(self) -> None:
        tmp = self._file.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._file)
        except Exception:
            pass  # Best-effort — nie die Pipeline blockieren
