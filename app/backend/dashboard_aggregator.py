"""
dashboard_aggregator.py

Reads the 'Hauptübersicht' sheet and produces a grouped market analysis DataFrame.
Groups by (event_name_normalized, event_datum, kategorie).
Sprint-2: adds historical columns (Aktiv_7_Tage, Privat/Händler Ø aktuell/historisch,
Preis_Bewegung) based on zuletzt_gesehen filter and preis_aktuell/preis_vor_7_tagen fields.
"""
import math
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


_EXCEL_COLUMN_MAP: dict[str, str] = {
    "Event-Name":               "event_name",
    "Event-Datum":              "event_datum",
    "Venue":                    "venue",
    "Stadt":                    "stadt",
    "Kategorie":                "kategorie",
    "Verkäufertyp":             "anbieter_typ",
    "Verkäufername":            "verkäufername",
    "Anzahl Karten":            "anzahl_karten",
    "Angebotspreis gesamt":     "angebotspreis_gesamt",
    "Angebotspreis pro Karte":  "preis_pro_karte",
    "Originalpreis pro Karte":  "originalpreis_pro_karte",
    "Confidence":               "confidence",
    # Sprint 1
    "Venue (normiert)":         "venue_normiert",
    "Venue-Kapazität":          "venue_kapazität",
    "Venue-Typ":                "venue_typ",
    "Vertriebsklasse":          "vertrieb_klasse",
    "Eingestellt am":           "eingestellt_am",
    # Sprint 2 — Historien-Architektur
    "Zuletzt gesehen":          "zuletzt_gesehen",
    "Status":                   "status",
    "Preis aktuell €/K":        "preis_aktuell",
    "Preis vor 7+ Tagen €/K":  "preis_vor_7_tagen",
}

_ANBIETER_TYP_COL = "anbieter_typ"
_PREIS_COL        = "preis_pro_karte"
_GESAMT_COL       = "angebotspreis_gesamt"
_ANZAHL_COL       = "anzahl_karten"
_OVP_COL          = "originalpreis_pro_karte"
_CONFIDENCE_COL   = "confidence"
_VERKAEUFER_COL   = "verkäufername"
_VERTRIEB_COL     = "vertrieb_klasse"

_OUTPUT_COLUMNS: list[str] = [
    "Event", "Kategorie", "Datum", "Venue", "Stadt",
    "Venue_normiert", "Venue_typ", "Venue_kapazität",
    "Gesamt_Anzahl",
    "Privat_Anzahl", "Privat_Min", "Privat_Avg", "Privat_Max",
    "Haendler_Anzahl", "Haendler_Min", "Haendler_Avg", "Haendler_Max",
    "OVP",
    "Marge_Haendler_EUR", "Marge_Privat_EUR",
    "Marge_Haendler_Pct", "Marge_Privat_Pct",
    "Top_Verkaeufer", "Top_Verkaeufer_Anzahl",
    "Confidence_Modal", "Vertrieb_Gewerblich_Anteil_Pct",
    # Sprint 2 — Historische Spalten
    "Aktiv_7_Tage",
    "Privat_Avg_Aktuell", "Privat_Avg_Historisch",
    "Haendler_Avg_Aktuell", "Haendler_Avg_Historisch",
    "Preis_Bewegung",
]

_SPRINT2_DF_COLS = ["zuletzt_gesehen", "status", "preis_aktuell", "preis_vor_7_tagen"]
_PREIS_BEWEGUNG_THRESHOLD_PCT = 3.0


def _safe_mean(series: "pd.Series") -> float | None:
    valid = series.dropna()
    return round(float(valid.mean()), 2) if not valid.empty else None


def _preis_bewegung(aktuell: float | None, historisch: float | None) -> str:
    """Gibt Preis-Bewegungs-Indikator zurück: 📉 -X% / ➡ stabil / 📈 +X%.

    Schwelle: ±3%. X ist die gerundete prozentuale Änderung.
    """
    if aktuell is None or historisch is None or historisch == 0:
        return "➡ stabil"
    pct = (aktuell - historisch) / abs(historisch) * 100
    if pct <= -_PREIS_BEWEGUNG_THRESHOLD_PCT:
        return f"📉 {round(pct):.0f}%"
    if pct >= _PREIS_BEWEGUNG_THRESHOLD_PCT:
        return f"📈 +{round(pct):.0f}%"
    return "➡ stabil"


def _normalize_event_name(name) -> str:
    if not name or not str(name).strip():
        return ""
    return re.sub(r"\s+", " ", str(name).strip()).lower()


def _normalize_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Fills preis_pro_karte from angebotspreis_gesamt / anzahl_karten where missing."""
    df = df.copy()
    if _PREIS_COL not in df.columns:
        df[_PREIS_COL] = float("nan")
    if _GESAMT_COL in df.columns and _ANZAHL_COL in df.columns:
        mask = (
            df[_PREIS_COL].isna()
            & df[_GESAMT_COL].notna()
            & df[_ANZAHL_COL].notna()
            & (df[_ANZAHL_COL] > 0)
        )
        df.loc[mask, _PREIS_COL] = (
            df.loc[mask, _GESAMT_COL] / df.loc[mask, _ANZAHL_COL]
        )
    return df


def _stats(sub: pd.DataFrame, prefix: str) -> dict:
    prices = sub[_PREIS_COL].dropna() if _PREIS_COL in sub.columns else pd.Series(dtype=float)
    if prices.empty:
        return {
            f"{prefix}_Anzahl": 0,
            f"{prefix}_Min":    float("nan"),
            f"{prefix}_Avg":    float("nan"),
            f"{prefix}_Max":    float("nan"),
        }
    return {
        f"{prefix}_Anzahl": len(prices),
        f"{prefix}_Min":    round(float(prices.min()), 2),
        f"{prefix}_Avg":    round(float(prices.mean()), 2),
        f"{prefix}_Max":    round(float(prices.max()), 2),
    }


def _top_verkaeufer(grp: pd.DataFrame) -> tuple:
    if _VERKAEUFER_COL not in grp.columns:
        return None, 0
    counts = grp[_VERKAEUFER_COL].dropna().value_counts()
    if counts.empty:
        return None, 0
    return str(counts.index[0]), int(counts.iloc[0])


def _confidence_modal(grp: pd.DataFrame) -> str | None:
    if _CONFIDENCE_COL not in grp.columns:
        return None
    vals = grp[_CONFIDENCE_COL].dropna()
    if vals.empty:
        return None
    mode = vals.mode()
    return str(mode.iloc[0]) if len(mode) > 0 else None


def load_excel(path: Path) -> pd.DataFrame:
    """Reads 'Hauptübersicht', renames columns, normalizes preis_pro_karte."""
    try:
        df = pd.read_excel(path, sheet_name="Hauptübersicht", engine="openpyxl")
        df = df.rename(columns=_EXCEL_COLUMN_MAP)
        for col in _SPRINT2_DF_COLS:
            if col not in df.columns:
                df[col] = None
        return _normalize_prices(df)
    except (FileNotFoundError, Exception):
        return pd.DataFrame()


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Groups by (event_name_normalized, event_datum, kategorie).
    Computes per-group: Privat/Händler price stats, OVP, margins,
    top seller, confidence modal, venue metadata, commercial share.
    """
    if df.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    df = _normalize_prices(df)

    for col in [_ANBIETER_TYP_COL, _OVP_COL, _CONFIDENCE_COL,
                _VERKAEUFER_COL, _VERTRIEB_COL]:
        if col not in df.columns:
            df = df.copy()
            df[col] = None

    df = df.copy()
    for col in _SPRINT2_DF_COLS:
        if col not in df.columns:
            df[col] = None
    df[_ANBIETER_TYP_COL] = df[_ANBIETER_TYP_COL].fillna("Privat")
    df["_event_key"] = df["event_name"].apply(_normalize_event_name)

    _7_tage_ago = (date.today() - timedelta(days=7)).isoformat()

    group_keys = ["_event_key", "event_datum", "kategorie"]
    for col in group_keys + ["event_name", "venue", "stadt"]:
        if col not in df.columns:
            df[col] = None

    rows = []
    for keys, grp in df.groupby(group_keys, dropna=False):
        privat   = grp[grp[_ANBIETER_TYP_COL] == "Privat"]
        haendler = grp[grp[_ANBIETER_TYP_COL] == "Händler"]

        privat_stats   = _stats(privat,   "Privat")
        haendler_stats = _stats(haendler, "Haendler")

        ovp_vals = grp[_OVP_COL].dropna()
        ovp = float(ovp_vals.median()) if not ovp_vals.empty else float("nan")

        def _marge_pct(avg: float) -> float:
            if math.isnan(ovp) or math.isnan(avg) or ovp == 0:
                return float("nan")
            return (ovp - avg) / ovp * 100

        def _marge_eur(avg: float) -> float:
            if math.isnan(ovp) or math.isnan(avg):
                return float("nan")
            return round(avg - ovp, 2)

        def _first(col: str):
            return grp[col].iloc[0] if col in grp.columns and not grp.empty else None

        top_name, top_count = _top_verkaeufer(grp)
        conf_modal = _confidence_modal(grp)

        gewerblich_n = int((grp[_VERTRIEB_COL] == "gewerblich").sum()) \
            if _VERTRIEB_COL in grp.columns else 0
        gewerblich_anteil = round(gewerblich_n / len(grp) * 100, 1) if len(grp) > 0 else float("nan")

        h_avg = haendler_stats["Haendler_Avg"]
        p_avg = privat_stats["Privat_Avg"]

        # Sprint-2: Zuletzt-gesehen-Filter für aktuell vs historisch
        zuletzt_ser = grp["zuletzt_gesehen"].fillna("").astype(str)
        aktuell_mask = zuletzt_ser >= _7_tage_ago
        grp_akt  = grp[aktuell_mask]
        grp_hist = grp[~aktuell_mask]

        aktiv_7_tage = int(
            (grp["status"].eq("aktiv") & aktuell_mask).sum()
        )

        privat_akt  = grp_akt[grp_akt[_ANBIETER_TYP_COL]  == "Privat"]
        privat_hist = grp_hist[grp_hist[_ANBIETER_TYP_COL] == "Privat"]
        haendl_akt  = grp_akt[grp_akt[_ANBIETER_TYP_COL]  == "Händler"]
        haendl_hist = grp_hist[grp_hist[_ANBIETER_TYP_COL] == "Händler"]

        privat_avg_akt   = _safe_mean(privat_akt[_PREIS_COL])  if _PREIS_COL in privat_akt.columns  else None
        privat_avg_hist  = _safe_mean(privat_hist[_PREIS_COL]) if _PREIS_COL in privat_hist.columns else None
        haendl_avg_akt   = _safe_mean(haendl_akt[_PREIS_COL])  if _PREIS_COL in haendl_akt.columns  else None
        haendl_avg_hist  = _safe_mean(haendl_hist[_PREIS_COL]) if _PREIS_COL in haendl_hist.columns else None

        # Preis-Bewegung: group-Mittelwert preis_aktuell vs preis_vor_7_tagen
        pa_vals = grp["preis_aktuell"].dropna()
        pv_vals = grp["preis_vor_7_tagen"].dropna()
        pa_mean = float(pa_vals.mean()) if not pa_vals.empty else None
        pv_mean = float(pv_vals.mean()) if not pv_vals.empty else None
        preis_bew = _preis_bewegung(pa_mean, pv_mean)

        _, event_datum, kategorie = keys
        rows.append({
            "Event":                           _first("event_name"),
            "Kategorie":                       kategorie,
            "Datum":                           event_datum,
            "Venue":                           _first("venue"),
            "Stadt":                           _first("stadt"),
            "Venue_normiert":                  _first("venue_normiert"),
            "Venue_typ":                       _first("venue_typ"),
            "Venue_kapazität":                 _first("venue_kapazität"),
            "Gesamt_Anzahl":                   len(grp),
            **privat_stats,
            **haendler_stats,
            "OVP":                             ovp,
            "Marge_Haendler_EUR":              _marge_eur(h_avg),
            "Marge_Privat_EUR":                _marge_eur(p_avg),
            "Marge_Haendler_Pct":              _marge_pct(h_avg),
            "Marge_Privat_Pct":                _marge_pct(p_avg),
            "Top_Verkaeufer":                  top_name,
            "Top_Verkaeufer_Anzahl":           top_count,
            "Confidence_Modal":                conf_modal,
            "Vertrieb_Gewerblich_Anteil_Pct":  gewerblich_anteil,
            # Sprint 2
            "Aktiv_7_Tage":                    aktiv_7_tage,
            "Privat_Avg_Aktuell":              privat_avg_akt,
            "Privat_Avg_Historisch":           privat_avg_hist,
            "Haendler_Avg_Aktuell":            haendl_avg_akt,
            "Haendler_Avg_Historisch":         haendl_avg_hist,
            "Preis_Bewegung":                  preis_bew,
        })

    if not rows:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    return pd.DataFrame(rows)


def export_csv(df: pd.DataFrame, path: Path) -> None:
    """Writes aggregated DataFrame as UTF-8 CSV."""
    df.to_csv(path, index=False, encoding="utf-8")
