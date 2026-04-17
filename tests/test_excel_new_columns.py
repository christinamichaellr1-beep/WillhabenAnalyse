"""Tests für die 4 neuen Spalten in excel_writer.py."""
import datetime
import tempfile
from pathlib import Path


NEW_FIELDS = ["confidence_grund", "modell", "pipeline_version", "parse_dauer_ms"]
NEW_HEADERS = ["Confidence-Grund", "Modell", "Pipeline-Version", "Parse-Dauer ms"]


def test_main_columns_contains_new_fields():
    from export.excel_writer import MAIN_COLUMNS
    fields = [f for f, _ in MAIN_COLUMNS]
    for field in NEW_FIELDS:
        assert field in fields, f"Feld '{field}' fehlt in MAIN_COLUMNS"


def test_main_headers_contains_new_headers():
    from export.excel_writer import MAIN_COLUMNS
    headers = [h for _, h in MAIN_COLUMNS]
    for header in NEW_HEADERS:
        assert header in headers, f"Header '{header}' fehlt in MAIN_COLUMNS"


def test_new_columns_at_end_of_main_columns():
    """Neue Spalten müssen NACH den bestehenden 24 Spalten kommen (backward-compat)."""
    from export.excel_writer import MAIN_COLUMNS
    fields = [f for f, _ in MAIN_COLUMNS]
    for field in NEW_FIELDS:
        assert fields.index(field) >= 24, f"Feld '{field}' muss nach Spalte 24 sein"


def test_upsert_writes_new_fields_to_excel():
    from export.excel_writer import upsert_events, MAIN_FIELDS
    import openpyxl

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        event = {
            "willhaben_id": "TEST001",
            "willhaben_link": "https://willhaben.at/test",
            "event_name": "Testkonzert",
            "event_datum": "2026-12-31",
            "confidence": "hoch",
            "confidence_grund": None,
            "modell": "gemma3:27b",
            "pipeline_version": "v2.0",
            "parse_dauer_ms": 1234,
            "verkäufertyp": "Privat",
            "verkäufername": "Test",
            "verkäufer_id": "123",
            "mitglied_seit": "01/2020",
            "kategorie": "Stehplatz",
            "anzahl_karten": 2,
            "angebotspreis_gesamt": 100.0,
            "preis_ist_pro_karte": False,
            "originalpreis_pro_karte": 50.0,
            "preis_roh": "100 €",
        }
        stats = upsert_events([event], path)
        assert stats["inserted"] == 1

        wb = openpyxl.load_workbook(path)
        ws = wb["Hauptübersicht"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]

        assert "Modell" in headers
        assert "Pipeline-Version" in headers
        assert "Parse-Dauer ms" in headers
        assert "Confidence-Grund" in headers

        # Werte in Zeile 2 prüfen
        modell_col = headers.index("Modell") + 1
        assert ws.cell(2, modell_col).value == "gemma3:27b"

        version_col = headers.index("Pipeline-Version") + 1
        assert ws.cell(2, version_col).value == "v2.0"

        dauer_col = headers.index("Parse-Dauer ms") + 1
        assert ws.cell(2, dauer_col).value == 1234


def test_old_data_compatible_new_columns_empty():
    """Bestehende Zeilen (v1) bekommen leere neue Spalten — kein Crash."""
    from export.excel_writer import upsert_events
    import openpyxl

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        event_v1 = {
            "willhaben_id": "V1_001",
            "event_name": "Altes Event",
            "event_datum": "2026-11-01",
            "confidence": "hoch",
            "verkäufertyp": "Privat",
            "verkäufername": "Old",
            "verkäufer_id": "1",
            "mitglied_seit": "01/2018",
            "kategorie": "Unbekannt",
            "anzahl_karten": 1,
            "angebotspreis_gesamt": 50.0,
            "preis_ist_pro_karte": True,
            "originalpreis_pro_karte": None,
            "preis_roh": "50 €",
            # v2-Felder fehlen absichtlich
        }
        stats = upsert_events([event_v1], path)
        assert stats["inserted"] == 1
        # Kein Crash = Test bestanden
