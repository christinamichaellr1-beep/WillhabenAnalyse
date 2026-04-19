"""Normalize and enrich venue names with capacity and type metadata."""
from __future__ import annotations

# (kapazität, typ, lowercase_aliases)
_VENUE_DB: dict[str, tuple[int | None, str, tuple[str, ...]]] = {
    "Ernst-Happel-Stadion": (
        51000, "Stadion",
        ("ernst happel", "happel stadion", "prater stadion", "happel"),
    ),
    "Wiener Stadthalle": (
        16000, "Halle",
        ("stadthalle wien", "stadthalle", "tipsarena"),
    ),
    "Gasometer Wien": (
        4800, "Halle",
        ("gasometer",),
    ),
    "Szene Wien": (
        1200, "Club",
        ("szene wien",),
    ),
    "Arena Wien": (
        2200, "Club",
        ("arena wien",),
    ),
    "Wiener Konzerthaus": (
        1840, "Halle",
        ("konzerthaus wien", "konzerthaus"),
    ),
    "Musikverein Wien": (
        1744, "Halle",
        ("musikverein",),
    ),
    "Open Air Donauinsel": (
        200000, "Festival",
        ("donauinsel",),
    ),
    "Wiener Volksoper": (
        1400, "Halle",
        ("volksoper",),
    ),
}

_EMPTY: dict = {"venue_normiert": None, "venue_kapazität": None, "venue_typ": None}


def lookup(venue: str | None) -> dict:
    """
    Returns {venue_normiert, venue_kapazität, venue_typ}.

    Tries exact match (case-insensitive), then alias match, then partial alias match.
    Unknown venues: venue_normiert=raw string, kapazität=None, typ='unbekannt'.
    """
    if not venue or not venue.strip():
        return dict(_EMPTY)

    raw = venue.strip()
    lower = raw.lower()

    for canonical, (kap, typ, aliases) in _VENUE_DB.items():
        if lower == canonical.lower() or lower in aliases:
            return {"venue_normiert": canonical, "venue_kapazität": kap, "venue_typ": typ}

    for canonical, (kap, typ, aliases) in _VENUE_DB.items():
        if any(alias in lower for alias in aliases) or canonical.lower() in lower:
            return {"venue_normiert": canonical, "venue_kapazität": kap, "venue_typ": typ}

    return {"venue_normiert": raw, "venue_kapazität": None, "venue_typ": "unbekannt"}
