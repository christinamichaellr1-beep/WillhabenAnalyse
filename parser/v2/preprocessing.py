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

    return f"Titel: {titel}\nPreis: {preis_roh}\n\nBeschreibung:\n{truncated}"
