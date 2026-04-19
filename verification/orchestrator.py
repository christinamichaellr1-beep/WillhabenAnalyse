"""Verification orchestrator: Layer 1-4 pipeline."""
from __future__ import annotations
import datetime
import logging
from dataclasses import dataclass, field
from enum import Enum

from verification.clients.base import BaseClient, EventCandidate
from verification.clients.musicbrainz import MusicBrainzClient
from verification.clients.wikidata import WikidataClient
from verification.clients.songkick import SongkickClient
from verification.clients.bandsintown import BandsintownClient
from verification.matcher import MatchResult, match

logger = logging.getLogger(__name__)


class VerifStatus(str, Enum):
    VERIFIED   = "verifiziert"
    LIKELY     = "wahrscheinlich"
    UNVERIFIED = "nicht_verifiziert"
    FAILED     = "fehler"
    SKIPPED    = "übersprungen"


@dataclass
class VerificationResult:
    status: VerifStatus
    best_match: MatchResult | None = None
    sources_checked: list[str] = field(default_factory=list)
    sources_confirmed: list[str] = field(default_factory=list)
    verif_datum: str = ""
    notes: str = ""


class Orchestrator:
    """Runs the 4-layer verification pipeline."""

    def __init__(
        self,
        musicbrainz: MusicBrainzClient | None = None,
        wikidata: WikidataClient | None = None,
        songkick: SongkickClient | None = None,
        bandsintown: BandsintownClient | None = None,
    ):
        self._layers: list[BaseClient] = []
        self._layers.append(musicbrainz or MusicBrainzClient())   # Layer 1
        self._layers.append(wikidata or WikidataClient())          # Layer 2
        self._layers.append(songkick or SongkickClient())          # Layer 3
        self._layers.append(bandsintown or BandsintownClient())    # Layer 4

    def verify(
        self,
        event_name: str | None,
        event_datum: datetime.date | None = None,
        stadt: str | None = None,
    ) -> VerificationResult:
        """Run 4-layer pipeline for one event."""
        today = datetime.date.today().isoformat()

        if not event_name or not event_name.strip():
            return VerificationResult(status=VerifStatus.SKIPPED, verif_datum=today, notes="event_name leer")

        sources_checked: list[str] = []
        sources_confirmed: list[str] = []
        best_match: MatchResult | None = None
        all_failed = True

        for client in self._layers:
            if not client.is_available():
                continue
            try:
                candidates = client.search(event_name, event_datum, stadt)
                sources_checked.append(client.SOURCE_NAME)
                all_failed = False
                mr = match(event_name, event_datum, stadt, candidates)
                if mr and mr.total_score >= 0.5:
                    sources_confirmed.append(client.SOURCE_NAME)
                    if best_match is None or mr.total_score > best_match.total_score:
                        best_match = mr
            except Exception as exc:
                logger.warning("Layer %s fehlgeschlagen: %s", client.SOURCE_NAME, exc)

        if not sources_checked and all_failed:
            return VerificationResult(status=VerifStatus.FAILED, verif_datum=today, notes="Alle Layer fehlgeschlagen")

        if len(sources_confirmed) >= 2 and best_match and best_match.total_score >= 0.6:
            status = VerifStatus.VERIFIED
        elif len(sources_confirmed) >= 1 and best_match and best_match.total_score >= 0.5:
            status = VerifStatus.LIKELY
        else:
            status = VerifStatus.UNVERIFIED

        return VerificationResult(
            status=status,
            best_match=best_match,
            sources_checked=sources_checked,
            sources_confirmed=sources_confirmed,
            verif_datum=today,
        )
