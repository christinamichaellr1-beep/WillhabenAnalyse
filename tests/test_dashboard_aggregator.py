"""Tests für dashboard_aggregator: filtere_dashboard_input + normalisiere_event_name."""
import pandas as pd
import pytest

from app.backend.dashboard_aggregator import filtere_dashboard_input, normalisiere_event_name


def _df(*rows):
    return pd.DataFrame(list(rows))


def _row(name="Konzert", datum="2026-08-01", preis=100.0):
    return {"event_name": name, "event_datum": datum, "angebotspreis_gesamt": preis}


# --- normalisiere_event_name ---

def test_normalisiere_kleinbuchstaben():
    assert normalisiere_event_name("Coldplay LIVE") == "coldplay live"


def test_normalisiere_whitespace_kollabiert():
    assert normalisiere_event_name("Foo   Bar") == "foo bar"


def test_normalisiere_leer_gibt_leer():
    assert normalisiere_event_name("") == ""
    assert normalisiere_event_name(None) == ""


def test_normalisiere_strips_rand_whitespace():
    assert normalisiere_event_name("  Test  ") == "test"


# --- filtere_dashboard_input ---

def test_filtere_behaelt_valide_zeile():
    df = _df(_row())
    result = filtere_dashboard_input(df)
    assert len(result) == 1


def test_filtere_entfernt_unbekannter_name():
    df = _df(_row(name="Unbekannt"))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_none_name():
    df = _df(_row(name="none"))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_leerer_name():
    df = _df(_row(name=""))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_python_none_name():
    df = _df(_row(name=None))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_fehlendes_datum():
    df = _df(_row(datum=None))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_leeres_datum():
    df = _df(_row(datum=""))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_preis_null():
    df = _df(_row(preis=0.0))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_preis_negativ():
    df = _df(_row(preis=-5.0))
    assert filtere_dashboard_input(df).empty


def test_filtere_entfernt_preis_none():
    df = _df(_row(preis=None))
    assert filtere_dashboard_input(df).empty


def test_filtere_behaelt_mehrere_valide_zeilen():
    df = _df(_row("Coldplay"), _row("Rammstein"))
    assert len(filtere_dashboard_input(df)) == 2


def test_filtere_gemischte_liste():
    df = _df(_row("Coldplay"), _row(name="Unbekannt"), _row(preis=None))
    result = filtere_dashboard_input(df)
    assert len(result) == 1
    assert result.iloc[0]["event_name"] == "Coldplay"


def test_filtere_leerer_dataframe():
    df = pd.DataFrame()
    assert filtere_dashboard_input(df).empty


def test_filtere_kein_preis_spalte_behaelt_zeile():
    """Wenn angebotspreis_gesamt-Spalte fehlt, wird Preis-Filter übersprungen."""
    df = pd.DataFrame([{"event_name": "Konzert", "event_datum": "2026-01-01"}])
    result = filtere_dashboard_input(df)
    assert len(result) == 1


def test_filtere_reset_index():
    df = _df(_row(name="Unbekannt"), _row("Coldplay"))
    result = filtere_dashboard_input(df)
    assert list(result.index) == [0]
