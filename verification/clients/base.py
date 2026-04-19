"""BaseClient ABC for all external verification clients."""
from __future__ import annotations
import abc
import datetime
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EventCandidate:
    """Normalized event candidate returned by any client."""
    event_name: str
    event_datum: datetime.date | None = None
    venue: str | None = None
    stadt: str | None = None
    source: str = ""
    confidence_score: float = 0.0   # 0.0–1.0
    raw: dict = field(default_factory=dict)


class BaseClient(abc.ABC):
    """Abstract base for all verification API clients."""

    SOURCE_NAME: str = ""           # override in subclass

    def __init__(self, api_key: str | None = None, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout

    @abc.abstractmethod
    def search(self, event_name: str, event_datum: datetime.date | None = None, stadt: str | None = None) -> list[EventCandidate]:
        """Search for an event. Returns list of candidates (empty if not found or error)."""
        ...

    def is_available(self) -> bool:
        """Returns True if the client can make requests (API key set if required)."""
        return True
