import pytest
from enrichment.venue_lookup import lookup


def test_exact_canonical_match():
    result = lookup("Ernst-Happel-Stadion")
    assert result == {
        "venue_normiert": "Ernst-Happel-Stadion",
        "venue_kapazität": 51000,
        "venue_typ": "Stadion",
    }


def test_alias_match():
    result = lookup("happel stadion")
    assert result["venue_normiert"] == "Ernst-Happel-Stadion"
    assert result["venue_kapazität"] == 51000
    assert result["venue_typ"] == "Stadion"


def test_partial_match_in_longer_string():
    result = lookup("Ernst Happel Wien")
    assert result["venue_normiert"] == "Ernst-Happel-Stadion"


def test_gasometer():
    result = lookup("Gasometer")
    assert result["venue_normiert"] == "Gasometer Wien"
    assert result["venue_typ"] == "Halle"


def test_unknown_venue_preserves_raw():
    result = lookup("Unbekannte Halle Linz")
    assert result["venue_normiert"] == "Unbekannte Halle Linz"
    assert result["venue_kapazität"] is None
    assert result["venue_typ"] == "unbekannt"


def test_none_input():
    result = lookup(None)
    assert result == {"venue_normiert": None, "venue_kapazität": None, "venue_typ": None}


def test_empty_string():
    result = lookup("")
    assert result == {"venue_normiert": None, "venue_kapazität": None, "venue_typ": None}


def test_case_insensitive():
    result = lookup("GASOMETER")
    assert result["venue_normiert"] == "Gasometer Wien"
