"""MusicBrainz client for artist/event lookup."""
from __future__ import annotations
import datetime
import logging
import requests

from .base import BaseClient, EventCandidate

logger = logging.getLogger(__name__)

MB_BASE = "https://musicbrainz.org/ws/2/"
USER_AGENT = "WillhabenVerifier/1.0 (willhaben-analyse)"

class MusicBrainzClient(BaseClient):
    SOURCE_NAME = "musicbrainz"

    def search(self, event_name: str, event_datum: datetime.date | None = None, stadt: str | None = None) -> list[EventCandidate]:
        # Search artists first, then could extend to events
        params = {"query": event_name, "fmt": "json", "limit": 5}
        try:
            resp = requests.get(
                MB_BASE + "artist",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("MusicBrainzClient.search fehlgeschlagen: %s", exc)
            return []

        candidates = []
        for artist in data.get("artists", []):
            score = float(artist.get("score", 0)) / 100.0
            candidates.append(EventCandidate(
                event_name=artist.get("name", ""),
                source=self.SOURCE_NAME,
                confidence_score=score,
                raw=artist,
            ))
        return candidates
