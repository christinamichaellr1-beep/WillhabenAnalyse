"""Songkick API client for concert lookup."""
from __future__ import annotations
import datetime
import logging
import os
import requests

from .base import BaseClient, EventCandidate

logger = logging.getLogger(__name__)
SK_BASE = "https://api.songkick.com/api/3.0/"

class SongkickClient(BaseClient):
    SOURCE_NAME = "songkick"

    def __init__(self, api_key: str | None = None, timeout: int = 10):
        super().__init__(api_key=api_key or os.getenv("SONGKICK_API_KEY"), timeout=timeout)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, event_name: str, event_datum: datetime.date | None = None, stadt: str | None = None) -> list[EventCandidate]:
        if not self.is_available():
            logger.debug("SongkickClient: kein API-Key, überspringe")
            return []
        params = {"apikey": self.api_key, "query": event_name, "per_page": 5}
        if stadt:
            params["location"] = f"clientip"  # simplified; real impl would geocode
        try:
            resp = requests.get(SK_BASE + "events/search.json", params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("SongkickClient.search fehlgeschlagen: %s", exc)
            return []

        candidates = []
        for ev in data.get("resultsPage", {}).get("results", {}).get("event", []):
            date_str = ev.get("start", {}).get("date", "")
            date = None
            if date_str:
                try:
                    date = datetime.date.fromisoformat(date_str)
                except ValueError:
                    pass
            venue = ev.get("venue", {}).get("displayName", "")
            city = ev.get("venue", {}).get("metroArea", {}).get("displayName", "")
            candidates.append(EventCandidate(
                event_name=ev.get("displayName", ""),
                event_datum=date,
                venue=venue,
                stadt=city,
                source=self.SOURCE_NAME,
                confidence_score=0.7,
                raw=ev,
            ))
        return candidates
