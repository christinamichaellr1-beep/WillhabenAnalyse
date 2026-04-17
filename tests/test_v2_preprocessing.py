"""Tests for parser/v2/preprocessing.py"""

NAV_TEXT = (
    "Zum Inhalt\nZu den Suchergebnissen\nNachrichten\nEinloggen|Registrieren\n"
    "Neue Anzeige aufgeben\nMARKTPLATZ\n13.692.412\nIMMOBILIEN\n110.105\n"
    "AUTO & MOTOR\n201.604\nJOBS\n15.166\n\nStartseite\n\nMarktplatz\n\n"
)

REAL_AD_TEXT = (
    NAV_TEXT +
    "Konzerte / Musikfestivals\n\n"
    "Rammstein Wien 15.06.2025\n"
    "1070 Wien, 07. Bezirk\n"
    "€ 180\n\n"
    "Verkaufe 2 Tickets für Rammstein Wien am 15.06.2025 im Ernst Happel Stadion. "
    "Originalpreis je 75 €. Privatverkauf."
)


# --- is_category_page ---

def test_category_page_detected_by_title():
    from parser.v2.preprocessing import is_category_page
    ad = {
        "titel": "4.126 Anzeigen in Konzerte / Musikfestivals - Tickets / Gutscheine",
        "text_komplett": NAV_TEXT,
    }
    assert is_category_page(ad) is True


def test_real_ad_not_category_page():
    from parser.v2.preprocessing import is_category_page
    ad = {
        "titel": "Rammstein Wien 15.06.2025 - 2x Tickets",
        "text_komplett": REAL_AD_TEXT,
    }
    assert is_category_page(ad) is False


def test_nav_only_text_is_category_page():
    from parser.v2.preprocessing import is_category_page
    ad = {
        "titel": "Seiler & Speer LIVE! BURG CLAM 24.07.",
        "text_komplett": NAV_TEXT,  # nur Navigation, kein echter Inhalt
    }
    assert is_category_page(ad) is True


def test_empty_ad_is_category_page():
    from parser.v2.preprocessing import is_category_page
    assert is_category_page({"titel": "", "text_komplett": ""}) is True


# --- strip_nav_prefix ---

def test_strip_nav_removes_leading_navigation():
    from parser.v2.preprocessing import strip_nav_prefix
    result = strip_nav_prefix(REAL_AD_TEXT)
    assert "Zum Inhalt" not in result
    assert "Rammstein" in result


def test_strip_nav_noop_on_clean_text():
    from parser.v2.preprocessing import strip_nav_prefix
    text = "Rammstein Tickets Wien 15.06.2025\nOriginalpreis 75€"
    result = strip_nav_prefix(text)
    assert "Rammstein" in result


# --- build_context ---

def test_build_context_includes_titel_and_preis():
    from parser.v2.preprocessing import build_context
    ad = {
        "titel": "Rammstein Wien",
        "preis_roh": "180 €",
        "text_komplett": REAL_AD_TEXT,
    }
    ctx = build_context(ad)
    assert "Titel: Rammstein Wien" in ctx
    assert "Preis: 180 €" in ctx


def test_build_context_strips_navigation():
    from parser.v2.preprocessing import build_context
    ad = {
        "titel": "Rammstein Wien",
        "preis_roh": "180 €",
        "text_komplett": REAL_AD_TEXT,
    }
    ctx = build_context(ad)
    assert "Zum Inhalt" not in ctx


def test_build_context_truncates_to_max_chars():
    from parser.v2.preprocessing import build_context
    long_text = "Konzert Details. " * 1000
    ad = {"titel": "Test", "preis_roh": "10 €", "text_komplett": long_text}
    ctx = build_context(ad, max_chars=500)
    assert len(ctx) < 700  # overhead von Titel+Preis-Zeilen eingerechnet


def test_build_context_default_max_chars_is_6000():
    from parser.v2.preprocessing import build_context
    long_text = "x" * 10000
    ad = {"titel": "T", "preis_roh": "1 €", "text_komplett": long_text}
    ctx = build_context(ad)
    # Nur der reine Text nach "Beschreibung:\n" darf max 6000 Zeichen haben
    text_part = ctx.split("Beschreibung:\n", 1)[-1]
    assert len(text_part) <= 6000
