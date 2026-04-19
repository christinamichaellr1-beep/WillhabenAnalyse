"""
test_ovp_logic.py

Unit tests for export.ovp_logic module.
Tests all branches of berechne_finaler_ovp() and validiere_ovp_anbieter_link().
"""
import logging
import pytest
from export.ovp_logic import berechne_finaler_ovp, validiere_ovp_anbieter_link


class TestBerechneFinalerOVP:
    """Test suite for berechne_finaler_ovp() function."""

    def test_beide_leer(self):
        """Both None → (None, '')"""
        ovp_final, quelle = berechne_finaler_ovp(None, None)
        assert ovp_final is None
        assert quelle == ""

    def test_nur_manuell(self):
        """Only manuell present → (manuell_value, 'manuell')"""
        ovp_final, quelle = berechne_finaler_ovp(None, 150.0)
        assert ovp_final == 150.0
        assert quelle == "manuell"

    def test_nur_extrahiert(self):
        """Only extrahiert present → (extrahiert_value, 'extrahiert')"""
        ovp_final, quelle = berechne_finaler_ovp(100.0, None)
        assert ovp_final == 100.0
        assert quelle == "extrahiert"

    def test_beide_übereinstimmend(self):
        """Both present, <5% deviation → (manuell, 'beide_übereinstimmend')"""
        # 100 vs 102 = 2% deviation
        ovp_final, quelle = berechne_finaler_ovp(100.0, 102.0)
        assert ovp_final == 102.0
        assert quelle == "beide_übereinstimmend"

    def test_konflikt_warnung(self, caplog):
        """Both present, >5% deviation → (manuell, 'konflikt') + warning log"""
        with caplog.at_level(logging.WARNING, logger="export.ovp_logic"):
            ovp_final, quelle = berechne_finaler_ovp(100.0, 200.0)

        assert quelle == "konflikt"
        assert ovp_final == 200.0
        # Check that warning was logged
        assert any("OVP-Konflikt" in r.message for r in caplog.records)

    def test_konflikt_genau_5pct(self):
        """Exactly 5% deviation → 'konflikt' (boundary: ≥5% is konflikt)"""
        # 100 vs 105.27 ≈ 5.006% deviation (just over threshold)
        ovp_final, quelle = berechne_finaler_ovp(100.0, 105.27)
        assert ovp_final == 105.27
        assert quelle == "konflikt"


class TestValidiereOVPAnbieterLink:
    """Test suite for validiere_ovp_anbieter_link() function."""

    def test_link_validierung_gueltig(self):
        """Valid URLs and empty string return True"""
        assert validiere_ovp_anbieter_link("https://example.com") is True
        assert validiere_ovp_anbieter_link("http://example.com") is True
        assert validiere_ovp_anbieter_link("") is True
        assert validiere_ovp_anbieter_link(None) is True
        assert validiere_ovp_anbieter_link("   ") is True  # whitespace-only

    def test_link_validierung_ungueltig(self):
        """Non-http URL returns False"""
        assert validiere_ovp_anbieter_link("example.com") is False
        assert validiere_ovp_anbieter_link("ftp://example.com") is False
        assert validiere_ovp_anbieter_link("htp://example.com") is False
        assert validiere_ovp_anbieter_link("notaurl") is False
