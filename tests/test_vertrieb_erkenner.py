import pytest
from enrichment.vertrieb_erkenner import classify


@pytest.mark.parametrize("ad,expected", [
    # Händler → immer gewerblich
    ({"verkäufertyp": "Händler", "verkäufername": "Anna"}, "gewerblich"),
    # Privat ohne Keyword → privat
    ({"verkäufertyp": "Privat", "verkäufername": "Max Muster"}, "privat"),
    # Privat mit Business-Keyword → gewerblich
    ({"verkäufertyp": "Privat", "verkäufername": "TicketShop Wien"}, "gewerblich"),
    ({"verkäufertyp": "Privat", "verkäufername": "eventsgmbh"}, "gewerblich"),
    # unbekannt ohne Keyword → unbekannt
    ({"verkäufertyp": "unbekannt", "verkäufername": "Peter"}, "unbekannt"),
    # unbekannt mit Keyword → gewerblich
    ({"verkäufertyp": "unbekannt", "verkäufername": "Tickets4You"}, "gewerblich"),
    # leere Felder → unbekannt
    ({"verkäufertyp": "", "verkäufername": ""}, "unbekannt"),
    ({}, "unbekannt"),
])
def test_classify(ad, expected):
    assert classify(ad) == expected
