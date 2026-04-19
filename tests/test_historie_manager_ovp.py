"""Tests for Phase 3: MANUELLE_SPALTEN protection in historie_manager."""
import datetime
import pytest
from parser.v2.historie_manager import (
    merge_scrape_mit_historie,
    update_bestehende_zeile,
    MANUELLE_SPALTEN,
)


def _base_existing():
    return {
        "willhaben_id": "123",
        "event_name": "Konzert",
        "erstmals_gesehen": "2026-04-01",
        "zuletzt_gesehen": "2026-04-01",
        "status": "aktiv",
        "scan_anzahl": 1,
        "ovp_manuell": 89.9,
        "ovp_anbieter_link": "https://oeticket.com/linkinpark",
        "ovp_final_quelle": "manuell",
        "ovp_manuell_eingetragen_am": "2026-04-10",
        "ovp_notiz": "Offizieller Preis",
    }


def test_manuelle_spalten_not_overwritten_by_scrape():
    """merge_scrape_mit_historie() darf MANUELLE_SPALTEN nicht überschreiben."""
    existing = _base_existing()
    new_event = {
        "willhaben_id": "123",
        "event_name": "Konzert Updated",
        "ovp_manuell": 0.0,  # Scrape-Result (falsy/wrong)
        "ovp_anbieter_link": None,
        "ovp_final_quelle": "extrahiert",
        "ovp_manuell_eingetragen_am": None,
        "ovp_notiz": "Überschrieben?",
        "angebotspreis_pro_karte": 120.0,
    }
    result = merge_scrape_mit_historie(existing, new_event, datetime.date(2026, 4, 19))
    assert result["ovp_manuell"] == 89.9
    assert result["ovp_anbieter_link"] == "https://oeticket.com/linkinpark"
    assert result["ovp_final_quelle"] == "manuell"
    assert result["ovp_manuell_eingetragen_am"] == "2026-04-10"
    assert result["ovp_notiz"] == "Offizieller Preis"


def test_non_manual_fields_still_updated():
    """Nicht-manuelle Felder werden normal aktualisiert."""
    existing = _base_existing()
    new_event = {"event_name": "Neuer Name", "angebotspreis_pro_karte": 99.0}
    result = merge_scrape_mit_historie(existing, new_event, datetime.date(2026, 4, 19))
    assert result["event_name"] == "Neuer Name"


def test_manuelle_spalten_constant_contains_all_five():
    """MANUELLE_SPALTEN enthält alle 5 OVP-Felder."""
    assert "ovp_manuell" in MANUELLE_SPALTEN
    assert "ovp_anbieter_link" in MANUELLE_SPALTEN
    assert "ovp_final_quelle" in MANUELLE_SPALTEN
    assert "ovp_manuell_eingetragen_am" in MANUELLE_SPALTEN
    assert "ovp_notiz" in MANUELLE_SPALTEN


def test_update_bestehende_zeile_skips_manual():
    """update_bestehende_zeile() überschreibt MANUELLE_SPALTEN nicht."""
    existing = _base_existing()
    updates = {"event_name": "Aktualisiert", "ovp_manuell": 999.0, "ovp_notiz": "Böse"}
    result = update_bestehende_zeile(existing, updates)
    assert result["event_name"] == "Aktualisiert"
    assert result["ovp_manuell"] == 89.9  # nicht überschrieben
    assert result["ovp_notiz"] == "Offizieller Preis"  # nicht überschrieben


def test_update_bestehende_zeile_does_not_mutate():
    """update_bestehende_zeile() mutiert keine Inputs."""
    existing = _base_existing()
    updates = {"event_name": "Neu"}
    result = update_bestehende_zeile(existing, updates)
    assert existing["event_name"] == "Konzert"
    assert result["event_name"] == "Neu"


def test_update_bestehende_zeile_non_manual_fields_updated():
    """update_bestehende_zeile() aktualisiert nicht-manuelle Felder."""
    existing = _base_existing()
    updates = {"verif_status": "verifiziert", "verif_score": "0.9"}
    result = update_bestehende_zeile(existing, updates)
    assert result["verif_status"] == "verifiziert"
    assert result["verif_score"] == "0.9"
