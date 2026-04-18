"""
Preprocessing für Parser v2.0.
Filtert Category-Pages, entfernt Navigations-Rausch, baut LLM-Kontext.
"""
import re

NAV_KEYWORDS: frozenset[str] = frozenset([
    "zum inhalt", "zu den suchergebnissen", "nachrichten",
    "einloggen", "registrieren", "neue anzeige aufgeben",
    "marktplatz", "rechtlicher hinweis", "noch mehr ähnliche anzeigen",
    "startseite", "auto & motor", "immobilien",
])

# Pattern für Inhalts-Startpunkte (Preis, Datum, Konzert-Keyword)
_CONTENT_PATTERNS = re.compile(
    r"(?:€|\beur\b|\d{1,2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}|"
    r"\bkonzert\b|\bticket\b|\bstehplatz\b|\bsitzplatz\b|\bverkaufe\b)",
    re.IGNORECASE,
)

_CATEGORY_TITLE = re.compile(r"^\d[\d.,]+ Anzeigen in ", re.IGNORECASE)

# Marker lines that separate the main ad body from related-ad suggestions
_SIMILAR_ADS_MARKER = re.compile(
    r"noch mehr ähnliche anzeigen|weitere anzeigen von\s+\S|sende eine nachricht",
    re.IGNORECASE,
)

# Keywords indicating a ticket/event ad
_EVENT_KEYWORDS = re.compile(
    r"\btickets?\b|\bkarten?\b|\beintrittskarten?\b|\bkonzert\b|\bfestival\b|"
    r"\bevent\b|\bveranstaltung(?:en)?\b|\blive\b|\btour\b|\bstehplatz\b|\bsitzplatz\b",
    re.IGNORECASE,
)

# Phrases that could confuse or hijack the LLM parser
_INJECTION_PATTERNS = re.compile(
    r"ignoriere\s+(?:alle\s+)?(?:bisherigen?\s+)?(?:anweisungen?|instruktionen?)|"
    r"ignore\s+(?:all\s+)?(?:previous\s+)?(?:instructions?)|"
    r"(?:^|\n)\s*system\s*:",
    re.IGNORECASE | re.MULTILINE,
)


def sanitize_ad_text(text: str) -> str:
    """Remove LLM prompt-injection markers from ad text.

    Replaces known injection phrases with a placeholder so the LLM parser
    cannot be steered by seller-controlled content.
    """
    return _INJECTION_PATTERNS.sub("[ENTFERNT]", text)


def _extract_main_description(text: str) -> str:
    """Returns the ad's main body text, stripped of nav prefix and similar-ads section."""
    stripped = strip_nav_prefix(text)
    match = _SIMILAR_ADS_MARKER.search(stripped)
    if match:
        return stripped[: match.start()]
    return stripped


def is_non_ticket_ad(ad: dict) -> bool:
    """
    True wenn Titel + Hauptbeschreibung keine Event-/Ticket-Keywords enthalten.
    Verhindert LLM-Aufruf für Anzeigen die zufällig in der Tickets-Kategorie landen.
    """
    titel = ad.get("titel", "") or ""
    text = ad.get("text_komplett", "") or ""
    combined = titel + "\n" + _extract_main_description(text)
    return not _EVENT_KEYWORDS.search(combined)


def is_category_page(ad: dict) -> bool:
    """
    True wenn die Anzeige eine Willhaben-Category-Page ist (kein echtes Inserat).
    Kriterien:
    - Titel matcht "4.126 Anzeigen in ..."
    - ODER text_komplett nach Nav-Strip enthält keinen Preis/Datum/Konzert-Hinweis
    """
    titel = ad.get("titel", "") or ""
    text = ad.get("text_komplett", "") or ""

    if _CATEGORY_TITLE.match(titel):
        return True

    stripped = strip_nav_prefix(text)
    if not stripped.strip():
        return True

    if not _CONTENT_PATTERNS.search(stripped):
        return True

    return False


def strip_nav_prefix(text: str) -> str:
    """
    Entfernt den führenden Willhaben-Navigationsblock.
    Sucht die erste Zeile, die nicht rein navigational ist.
    """
    if not text:
        return text

    lines = text.split("\n")
    start_idx = 0

    for i, line in enumerate(lines):
        line_lower = line.strip().lower()
        # Leerzeile überspringen
        if not line_lower:
            continue
        # Navigations-Keywords überspringen
        if any(kw in line_lower for kw in NAV_KEYWORDS):
            start_idx = i + 1
            continue
        # Reine Zahlen (Anzeigen-Counter wie "13.692.412") überspringen
        if re.match(r"^[\d.,\s]+$", line.strip()):
            start_idx = i + 1
            continue
        # Erste nicht-navigationale Zeile gefunden
        break

    return "\n".join(lines[start_idx:]).lstrip("\n")


def build_context(ad: dict, max_chars: int = 6000) -> str:
    """
    Baut den LLM-Kontext aus einem Anzeigen-Dict.
    Format: 'Titel: ...\nPreis: ...\n\nBeschreibung:\n{text[:max_chars]}'
    Navigation wird vor dem Truncating entfernt.
    """
    titel = ad.get("titel", "") or ""
    preis_roh = ad.get("preis_roh", "") or ""
    text = ad.get("text_komplett", "") or ""

    stripped = strip_nav_prefix(text)
    truncated = stripped[:max_chars]

    safe_titel = sanitize_ad_text(titel)
    safe_text = sanitize_ad_text(truncated)

    return f"Titel: {safe_titel}\nPreis: {preis_roh}\n\nBeschreibung:\n{safe_text}"
