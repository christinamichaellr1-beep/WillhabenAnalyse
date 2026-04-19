"""
historie_manager.py

Pure functions für history-aware Scrape-Merge und Preis-Progression.
Keine Seiteneffekte, keine Excel-Abhängigkeit — nur dict → dict Transformationen.
"""
from datetime import date

# Felder, die vom HistorieManager verwaltet werden — nie blind überschreiben
HISTORY_FIELDS = frozenset({
    "erstmals_gesehen",
    "zuletzt_gesehen",
    "status",
    "scan_anzahl",
    "preis_aktuell",
    "preis_vor_7_tagen",
    "preis_aenderungen_count",
    "letzte_preisaenderung_am",
})

# OVP-Felder — einmal gesetzt, nie durch Scrape überschreiben
OVP_PROTECTED = frozenset({"originalpreis_pro_karte", "ovp_quelle", "ausverkauft"})

# Felder, die Michael manuell pflegt — dürfen durch Parser/Scraper nie überschrieben werden
MANUELLE_SPALTEN: frozenset[str] = frozenset({
    "ovp_manuell",
    "ovp_anbieter_link",
    "ovp_final_quelle",
    "ovp_manuell_eingetragen_am",
    "ovp_notiz",
})

INAKTIV_GRACE_DAYS = 21
_PRICE_HISTORY_DAYS = 7


def merge_scrape_mit_historie(
    existing: dict,
    new_event: dict,
    scan_datum: date,
) -> dict:
    """Merged neues Scrape-Ergebnis in bestehende Zeile unter Erhalt von History + OVP-Feldern.

    Gibt neues dict zurück — mutiert keine Inputs.
    """
    merged = existing.copy()
    skip = HISTORY_FIELDS | OVP_PROTECTED | MANUELLE_SPALTEN

    for field, value in new_event.items():
        if field not in skip:
            merged[field] = value

    merged["zuletzt_gesehen"] = scan_datum.isoformat()
    merged["scan_anzahl"] = int(existing.get("scan_anzahl") or 0) + 1
    merged["status"] = "aktiv"

    new_preis = new_event.get("angebotspreis_pro_karte")
    if new_preis is not None:
        merged = update_preis_mit_progression(merged, float(new_preis), scan_datum)

    return merged


def update_bestehende_zeile(existing: dict, updates: dict) -> dict:
    """Applies partial updates to an existing row, never overwriting MANUELLE_SPALTEN.

    Use for non-scrape updates (e.g. verification results, computed fields).
    Returns new dict — does not mutate inputs.
    """
    result = existing.copy()
    for field, value in updates.items():
        if field not in MANUELLE_SPALTEN:
            result[field] = value
    return result


def update_preis_mit_progression(
    row: dict,
    new_preis: float,
    scan_datum: date,
) -> dict:
    """Wendet 7-Tage-Preis-Progressionsregel an.

    - Kein bestehender Preis → preis_aktuell setzen.
    - Preis unverändert → keine Änderung.
    - Preis geändert, aktueller Preis >= 7 Tage alt → alten Preis nach preis_vor_7_tagen verschieben.
    - Preis geändert, aktueller Preis < 7 Tage alt → nur preis_aktuell überschreiben.

    Gibt neues dict zurück — mutiert keinen Input.
    """
    result = row.copy()
    current_preis = result.get("preis_aktuell")

    if current_preis in (None, ""):
        result["preis_aktuell"] = new_preis
        result["letzte_preisaenderung_am"] = scan_datum.isoformat()
        return result

    current_preis = float(current_preis)
    if abs(current_preis - new_preis) < 0.01:
        return result  # Keine wesentliche Änderung

    # Preis hat sich verändert — Alter des aktuellen Preises bestimmen
    letzte_aenderung = result.get("letzte_preisaenderung_am")
    if letzte_aenderung and str(letzte_aenderung).strip():
        alter_tage = (scan_datum - date.fromisoformat(str(letzte_aenderung)[:10])).days
    else:
        erstmals = result.get("erstmals_gesehen")
        alter_tage = (
            (scan_datum - date.fromisoformat(str(erstmals)[:10])).days
            if erstmals and str(erstmals).strip()
            else 0
        )

    if alter_tage >= _PRICE_HISTORY_DAYS:
        result["preis_vor_7_tagen"] = current_preis

    result["preis_aktuell"] = new_preis
    result["preis_aenderungen_count"] = int(result.get("preis_aenderungen_count") or 0) + 1
    result["letzte_preisaenderung_am"] = scan_datum.isoformat()
    return result


def markiere_inaktive(
    rows: list[dict],
    current_ids: set[str],
    scan_datum: date,
    grace_days: int = INAKTIV_GRACE_DAYS,
) -> list[dict]:
    """Aktualisiert status-Feld aller Zeilen.

    - ID im aktuellen Scan → "aktiv"
    - ID nicht im Scan UND zuletzt_gesehen >= grace_days → "inaktiv"
    - status == "verkauft" → niemals ändern

    Gibt neue Liste zurück — mutiert keine Inputs.
    """
    result = []
    for row in rows:
        updated = row.copy()
        wid = str(row.get("willhaben_id") or "")

        if row.get("status") == "verkauft":
            result.append(updated)
            continue

        if wid in current_ids:
            updated["status"] = "aktiv"
        else:
            zuletzt = row.get("zuletzt_gesehen")
            if zuletzt and str(zuletzt).strip():
                tage = (scan_datum - date.fromisoformat(str(zuletzt)[:10])).days
                if tage >= grace_days:
                    updated["status"] = "inaktiv"

        result.append(updated)
    return result
