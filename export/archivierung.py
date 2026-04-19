"""Archive expired events from Hauptübersicht → Archiv sheet."""
import datetime
from pathlib import Path


def archive_expired(excel_path: Path, cutoff_date: datetime.date | None = None) -> int:
    raise NotImplementedError
