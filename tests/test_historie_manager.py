"""15 Unit-Tests für parser/v2/historie_manager.py"""
from datetime import date

import pytest

from parser.v2.historie_manager import (
    markiere_inaktive,
    merge_scrape_mit_historie,
    update_preis_mit_progression,
)

D0  = date(2026, 4, 1)
D3  = date(2026, 4, 4)
D7  = date(2026, 4, 8)
D14 = date(2026, 4, 15)
D21 = date(2026, 4, 22)


# ── update_preis_mit_progression (6 Tests) ────────────────────────────────

def test_preis_erstmals_gesetzt():
    """Kein bisheriger Preis → preis_aktuell setzen, letzte_preisaenderung_am setzen."""
    row = {
        "preis_aktuell": None,
        "letzte_preisaenderung_am": None,
        "erstmals_gesehen": "2026-04-01",
        "preis_vor_7_tagen": None,
        "preis_aenderungen_count": 0,
    }
    result = update_preis_mit_progression(row, 50.0, D0)
    assert result["preis_aktuell"] == 50.0
    assert result["letzte_preisaenderung_am"] == "2026-04-01"
    assert result.get("preis_vor_7_tagen") is None


def test_preis_unveraendert_kein_update():
    """Gleicher Preis → keine Änderung an irgendeinem Feld."""
    row = {
        "preis_aktuell": 50.0,
        "letzte_preisaenderung_am": "2026-04-01",
        "preis_aenderungen_count": 2,
        "preis_vor_7_tagen": 55.0,
        "erstmals_gesehen": "2026-04-01",
    }
    result = update_preis_mit_progression(row, 50.0, D7)
    assert result["preis_aktuell"] == 50.0
    assert result["preis_aenderungen_count"] == 2
    assert result["preis_vor_7_tagen"] == 55.0


def test_preis_aenderung_unter_7_tage_kein_historisch():
    """Preisänderung < 7 Tage → preis_aktuell überschreiben, NICHT nach preis_vor_7_tagen."""
    row = {
        "preis_aktuell": 50.0,
        "letzte_preisaenderung_am": "2026-04-05",  # 3 Tage vor D7
        "preis_aenderungen_count": 0,
        "preis_vor_7_tagen": None,
        "erstmals_gesehen": "2026-04-05",
    }
    result = update_preis_mit_progression(row, 45.0, D7)
    assert result["preis_aktuell"] == 45.0
    assert result.get("preis_vor_7_tagen") is None
    assert result["preis_aenderungen_count"] == 1


def test_preis_aenderung_nach_7_tagen_verschiebt_zu_historisch():
    """Preisänderung nach >=7 Tagen → alter Preis nach preis_vor_7_tagen, Count+1."""
    row = {
        "preis_aktuell": 50.0,
        "letzte_preisaenderung_am": "2026-04-01",  # exakt 7 Tage vor D7
        "preis_aenderungen_count": 1,
        "preis_vor_7_tagen": None,
        "erstmals_gesehen": "2026-04-01",
    }
    result = update_preis_mit_progression(row, 45.0, D7)
    assert result["preis_vor_7_tagen"] == 50.0
    assert result["preis_aktuell"] == 45.0
    assert result["preis_aenderungen_count"] == 2
    assert result["letzte_preisaenderung_am"] == "2026-04-08"


def test_preis_keine_letzte_aenderung_nutzt_erstmals_gesehen():
    """Kein letzte_preisaenderung_am → erstmals_gesehen als Altersreferenz."""
    row = {
        "preis_aktuell": 60.0,
        "letzte_preisaenderung_am": None,
        "erstmals_gesehen": "2026-04-01",
        "preis_aenderungen_count": 0,
        "preis_vor_7_tagen": None,
    }
    result = update_preis_mit_progression(row, 55.0, D7)
    assert result["preis_vor_7_tagen"] == 60.0
    assert result["preis_aktuell"] == 55.0


def test_preis_1_eur_aenderung_wird_erkannt():
    """Preisdifferenz von 1 EUR gilt als echte Änderung (nicht unter 0,01 EUR-Schwelle)."""
    row = {
        "preis_aktuell": 100.0,
        "letzte_preisaenderung_am": "2026-04-01",
        "preis_aenderungen_count": 0,
        "preis_vor_7_tagen": None,
        "erstmals_gesehen": "2026-04-01",
    }
    result = update_preis_mit_progression(row, 101.0, D7)
    assert result["preis_aktuell"] == 101.0
    assert result["preis_aenderungen_count"] == 1


# ── merge_scrape_mit_historie (5 Tests) ───────────────────────────────────

def _base_existing(wid: str = "123") -> dict:
    return {
        "willhaben_id": wid,
        "scan_anzahl": 3,
        "zuletzt_gesehen": "2026-04-01",
        "erstmals_gesehen": "2026-03-01",
        "status": "aktiv",
        "angebotspreis_pro_karte": 50.0,
        "preis_aktuell": 50.0,
        "letzte_preisaenderung_am": "2026-04-01",
        "preis_aenderungen_count": 0,
        "preis_vor_7_tagen": None,
        "event_name": "Konzert X",
        "originalpreis_pro_karte": 89.90,
        "ovp_quelle": "oeticket",
    }


def test_merge_erhoet_scan_anzahl():
    """Jeder Merge-Aufruf inkrementiert scan_anzahl um 1."""
    existing = _base_existing()
    new_event = {"willhaben_id": "123", "angebotspreis_pro_karte": 50.0, "event_name": "Konzert X"}
    result = merge_scrape_mit_historie(existing, new_event, D7)
    assert result["scan_anzahl"] == 4


def test_merge_aktualisiert_zuletzt_gesehen():
    """zuletzt_gesehen wird auf scan_datum aktualisiert."""
    existing = _base_existing()
    new_event = {"willhaben_id": "123", "angebotspreis_pro_karte": 50.0}
    result = merge_scrape_mit_historie(existing, new_event, D7)
    assert result["zuletzt_gesehen"] == "2026-04-08"


def test_merge_setzt_status_aktiv_auch_wenn_vorher_inaktiv():
    """Wiedergefundene Zeile erhält status=aktiv, auch wenn vorher inaktiv."""
    existing = {**_base_existing(), "status": "inaktiv", "zuletzt_gesehen": "2026-01-01"}
    new_event = {"willhaben_id": "123", "angebotspreis_pro_karte": 40.0}
    result = merge_scrape_mit_historie(existing, new_event, D7)
    assert result["status"] == "aktiv"


def test_merge_schuetzt_ovp_felder():
    """OVP-Felder werden durch den Scrape nicht überschrieben."""
    existing = {**_base_existing(), "originalpreis_pro_karte": 89.90}
    new_event = {
        "willhaben_id": "123",
        "angebotspreis_pro_karte": 50.0,
        "originalpreis_pro_karte": 99.99,  # soll ignoriert werden
    }
    result = merge_scrape_mit_historie(existing, new_event, D7)
    assert result["originalpreis_pro_karte"] == 89.90


def test_merge_uebernimmt_preisaenderung_nach_7_tagen():
    """Preisänderung nach 7 Tagen: alter Preis wandert nach preis_vor_7_tagen."""
    existing = _base_existing()  # preis_aktuell=50, letzte_aenderung=2026-04-01
    new_event = {"willhaben_id": "123", "angebotspreis_pro_karte": 45.0}
    result = merge_scrape_mit_historie(existing, new_event, D7)
    assert result["preis_vor_7_tagen"] == 50.0
    assert result["preis_aktuell"] == 45.0


# ── markiere_inaktive (4 Tests) ──────────────────────────────────────────

def test_inaktiv_nach_grace_period():
    """Zeile nicht im Scan + zuletzt_gesehen >= 21 Tage → status=inaktiv."""
    rows = [{"willhaben_id": "A", "status": "aktiv", "zuletzt_gesehen": "2026-04-01"}]
    result = markiere_inaktive(rows, set(), D21, grace_days=21)
    assert result[0]["status"] == "inaktiv"


def test_aktiv_innerhalb_grace_period_bleibt_aktiv():
    """Nicht im Scan, aber nur 6 Tage weg → bleibt aktiv."""
    rows = [{"willhaben_id": "A", "status": "aktiv", "zuletzt_gesehen": "2026-04-16"}]
    result = markiere_inaktive(rows, set(), D21, grace_days=21)
    assert result[0]["status"] == "aktiv"


def test_verkauft_wird_nicht_geaendert():
    """status=verkauft wird nie durch markiere_inaktive verändert."""
    rows = [{"willhaben_id": "A", "status": "verkauft", "zuletzt_gesehen": "2026-01-01"}]
    result = markiere_inaktive(rows, set(), D21, grace_days=21)
    assert result[0]["status"] == "verkauft"


def test_in_current_scan_wird_aktiv():
    """ID im aktuellen Scan → status=aktiv, auch wenn vorher inaktiv."""
    rows = [{"willhaben_id": "A", "status": "inaktiv", "zuletzt_gesehen": "2026-04-01"}]
    result = markiere_inaktive(rows, {"A"}, D21, grace_days=21)
    assert result[0]["status"] == "aktiv"
