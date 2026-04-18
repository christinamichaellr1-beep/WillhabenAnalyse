"""
dashboard_aggregator.py

Aggregates Excel 'Hauptübersicht' sheet data into a market analysis summary
using pandas. Groups by (event_name, event_datum, kategorie) and
separates Privat vs Haendler sellers.
"""
import math
from pathlib import Path

import pandas as pd


# Maps Excel display-header names → aggregator snake_case column names.
# The Excel sheet uses German display names (written by excel_writer.py);
# the aggregator works with snake_case keys.  load_excel() applies this
# rename immediately after pd.read_excel so the rest of the module never
# has to deal with German column names.
_EXCEL_COLUMN_MAP: dict[str, str] = {
    "Event-Name":             "event_name",
    "Event-Datum":            "event_datum",
    "Venue":                  "venue",
    "Stadt":                  "stadt",
    "Kategorie":              "kategorie",
    "Verkäufertyp":           "anbieter_typ",
    "Anzahl Karten":          "anzahl_karten",
    "Angebotspreis gesamt":   "angebotspreis_gesamt",
    "Angebotspreis pro Karte": "preis_pro_karte",
    "Originalpreis pro Karte": "originalpreis_pro_karte",
}

# Column name used to identify seller type in the Excel sheet
_ANBIETER_TYP_COL = "anbieter_typ"
_PREIS_COL = "preis_pro_karte"
_GESAMT_COL = "angebotspreis_gesamt"
_ANZAHL_COL = "anzahl_karten"
_OVP_COL = "originalpreis_pro_karte"


def load_excel(path: Path) -> pd.DataFrame:
    """Reads 'Hauptübersicht' sheet from Excel. Returns empty DataFrame if file missing."""
    try:
        df = pd.read_excel(path, sheet_name="Hauptübersicht", engine="openpyxl")
        return df.rename(columns=_EXCEL_COLUMN_MAP)
    except (FileNotFoundError, Exception):
        return pd.DataFrame()


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Groups by (event_name, event_datum, kategorie).
    Separates 'Privat' vs 'Händler' sellers by anbieter_typ column.
    Computes per-group: count, min/mean/max of preis_pro_karte.
    Attaches median originalpreis_pro_karte as OVP.
    Computes Marge % = (OVP - mean_preis) / OVP * 100 for each seller type.
    Returns DataFrame with the dashboard columns.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "Event", "Kategorie", "Datum", "Venue", "Stadt",
            "Privat_Anzahl", "Privat_Min", "Privat_Avg", "Privat_Max",
            "Haendler_Anzahl", "Haendler_Min", "Haendler_Avg", "Haendler_Max",
            "OVP", "Marge_Haendler_Pct", "Marge_Privat_Pct",
        ])

    df = df.copy()

    # Compute preis_pro_karte if not already present
    if _PREIS_COL not in df.columns:
        if _GESAMT_COL in df.columns and _ANZAHL_COL in df.columns:
            df[_PREIS_COL] = df[_GESAMT_COL] / df[_ANZAHL_COL]
        else:
            df[_PREIS_COL] = float("nan")

    # Normalise anbieter_typ: None / NaN → "Privat"
    if _ANBIETER_TYP_COL not in df.columns:
        df[_ANBIETER_TYP_COL] = "Privat"
    else:
        df[_ANBIETER_TYP_COL] = df[_ANBIETER_TYP_COL].fillna("Privat")

    group_keys = ["event_name", "event_datum", "kategorie"]
    # Also capture venue/stadt for display — take first value per group
    meta_keys = ["venue", "stadt"]

    # Make sure meta columns exist
    for col in meta_keys + group_keys:
        if col not in df.columns:
            df[col] = None

    # --- helper: compute stats for one seller-type subset ---
    def _stats(sub: pd.DataFrame, prefix: str) -> dict:
        prices = sub[_PREIS_COL].dropna()
        if len(prices) == 0:
            return {
                f"{prefix}_Anzahl": 0,
                f"{prefix}_Min": float("nan"),
                f"{prefix}_Avg": float("nan"),
                f"{prefix}_Max": float("nan"),
            }
        return {
            f"{prefix}_Anzahl": len(prices),
            f"{prefix}_Min": prices.min(),
            f"{prefix}_Avg": prices.mean(),
            f"{prefix}_Max": prices.max(),
        }

    rows = []
    for keys, grp in df.groupby(group_keys, dropna=False):
        event_name, event_datum, kategorie = keys

        privat = grp[grp[_ANBIETER_TYP_COL] == "Privat"]
        haendler = grp[grp[_ANBIETER_TYP_COL] == "Händler"]

        privat_stats = _stats(privat, "Privat")
        haendler_stats = _stats(haendler, "Haendler")

        # OVP: median of originalpreis_pro_karte across entire group
        if _OVP_COL in grp.columns:
            ovp_vals = grp[_OVP_COL].dropna()
            ovp = ovp_vals.median() if len(ovp_vals) > 0 else float("nan")
        else:
            ovp = float("nan")

        # Marge %: (OVP - mean_preis) / OVP * 100
        def _marge(avg: float) -> float:
            if math.isnan(ovp) or math.isnan(avg) or ovp == 0:
                return float("nan")
            return (ovp - avg) / ovp * 100

        row = {
            "Event": event_name,
            "Kategorie": kategorie,
            "Datum": event_datum,
            "Venue": grp["venue"].iloc[0] if "venue" in grp.columns else None,
            "Stadt": grp["stadt"].iloc[0] if "stadt" in grp.columns else None,
            **privat_stats,
            **haendler_stats,
            "OVP": ovp,
            "Marge_Haendler_Pct": _marge(haendler_stats["Haendler_Avg"]),
            "Marge_Privat_Pct": _marge(privat_stats["Privat_Avg"]),
        }
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=[
            "Event", "Kategorie", "Datum", "Venue", "Stadt",
            "Privat_Anzahl", "Privat_Min", "Privat_Avg", "Privat_Max",
            "Haendler_Anzahl", "Haendler_Min", "Haendler_Avg", "Haendler_Max",
            "OVP", "Marge_Haendler_Pct", "Marge_Privat_Pct",
        ])

    return pd.DataFrame(rows)


def export_csv(df: pd.DataFrame, path: Path) -> None:
    """Writes aggregated DataFrame as UTF-8 CSV."""
    df.to_csv(path, index=False, encoding="utf-8")
