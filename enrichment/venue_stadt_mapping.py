"""Map canonical venue names to their city (Stadt)."""
from __future__ import annotations

_VENUE_STADT: dict[str, str] = {
    "Ernst-Happel-Stadion": "Wien",
    "Wiener Stadthalle": "Wien",
    "Gasometer Wien": "Wien",
    "Szene Wien": "Wien",
    "Arena Wien": "Wien",
    "Wiener Konzerthaus": "Wien",
    "Musikverein Wien": "Wien",
    "Open Air Donauinsel": "Wien",
    "Wiener Volksoper": "Wien",
}


def get_stadt(venue_normiert: str | None) -> str | None:
    """Returns city for a canonical venue name, or None if unknown."""
    if not venue_normiert:
        return None
    return _VENUE_STADT.get(venue_normiert)
