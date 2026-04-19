"""Bandsintown API client for artist/concert lookup."""
from __future__ import annotations
import datetime
import logging
import os
import requests

from .base import BaseClient, EventCandidate

logger = logging.getLogger(__name__)
BIT_BASE = "https://rest.bandsintown.com/"

class BandsintownClient(BaseClient):
    SOURCE_NAME = "bandsintown"

    def __init__(self, api_key: str | None = None, timeout: int = 10):
        super().__init__(api_key=api_key or os.getenv("BANDSINTOWN_APP_ID"), timeout=timeout)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, event_name: str, event_datum: datetime.date | None = None, stadt: str | None = None) -> list[EventCandidate]:
        if not self.is_available():
            logger.debug("BandsintownClient: kein APP_ID, überspringe")
            return []
        params = {"app_id": self.api_key}
        url = BIT_BASE + f"artists/{requests.utils.quote(event_name)}/events"
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            events = resp.json()
        except Exception as exc:
            logger.warning("BandsintownClient.search fehlgeschlagen: %s", exc)
            return []

        if not isinstance(events, list):
            return []

        candidates = []
        for ev in events[:5]:
            date_str = ev.get("datetime", "")[:10] if ev.get("datetime") else ""
            date = None
            if date_str:
                try:
                    date = datetime.date.fromisoformat(date_str)
                except ValueError:
                    pass
            venue = ev.get("venue", {}).get("name", "")
            city = ev.get("venue", {}).get("city", "")
            candidates.append(EventCandidate(
                event_name=event_name,
                event_datum=date,
                venue=venue,
                stadt=city,
                source=self.SOURCE_NAME,
                confidence_score=0.75,
                raw=ev,
            ))
        return candidates
