"""Classify willhaben sellers as gewerblich | privat | unbekannt."""
from __future__ import annotations

_BUSINESS_KEYWORDS: frozenset[str] = frozenset([
    "ticket", "tickets", "event", "events", "concert", "concerts",
    "box office", "agency", "gmbh", "kg", "ltd", "resell", "shop",
])


def classify(ad: dict) -> str:
    """
    Returns 'gewerblich' | 'privat' | 'unbekannt'.

    - Händler → gewerblich
    - Privat → privat unless verkäufername contains a business keyword
    - unbekannt/missing → check name, else unbekannt
    """
    typ = (ad.get("verkäufertyp") or "").strip()
    name_lower = (ad.get("verkäufername") or "").lower()

    if typ == "Händler":
        return "gewerblich"
    if typ == "Privat":
        if any(kw in name_lower for kw in _BUSINESS_KEYWORDS):
            return "gewerblich"
        return "privat"
    if any(kw in name_lower for kw in _BUSINESS_KEYWORDS):
        return "gewerblich"
    return "unbekannt"
