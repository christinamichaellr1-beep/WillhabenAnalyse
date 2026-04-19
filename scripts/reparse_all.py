"""
reparse_all.py
Löscht parse_cache + Excel, parsed alle raw_cache-Anzeigen neu,
schreibt Excel, kopiert nach Google Drive.
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

LOG_FILE = BASE_DIR / "logs" / "reparse_v2.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

EXCEL_PATH = BASE_DIR / "data" / "willhaben_markt.xlsx"
RAW_CACHE_DIR = BASE_DIR / "data" / "raw_cache"
PARSE_CACHE_DIR = BASE_DIR / "data" / "parse_cache"


def main():
    t0 = time.time()

    # 1. Parse-Cache löschen (erzwingt Reparse mit neuem Prompt)
    cache_files = list(PARSE_CACHE_DIR.glob("*.json"))
    logger.info("Lösche %d Parse-Cache-Dateien ...", len(cache_files))
    for f in cache_files:
        f.unlink(missing_ok=True)
    logger.info("Parse-Cache geleert.")

    # 2. Excel löschen
    if EXCEL_PATH.exists():
        EXCEL_PATH.unlink()
        logger.info("Excel gelöscht: %s", EXCEL_PATH)

    # 3. Alle raw_cache laden
    raw_files = sorted(RAW_CACHE_DIR.glob("*.json"))
    logger.info("Lade %d Anzeigen aus raw_cache ...", len(raw_files))
    ads = []
    for f in raw_files:
        try:
            ads.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("Fehler beim Lesen von %s: %s", f.name, e)
    logger.info("%d Anzeigen geladen.", len(ads))

    # 4. Parsing mit neuem Prompt (use_cache=True, aber Cache ist leer → Ollama)
    logger.info("=== START PARSING (%d Anzeigen) ===", len(ads))
    from parser.gemma_parser import parse_ads
    events = parse_ads(ads, use_cache=True)
    logger.info("Parsing fertig: %d Events aus %d Anzeigen.", len(events), len(ads))

    # 5. OVP-Check
    logger.info("=== OVP-CHECK ===")
    try:
        from ovp.ovp_checker import check_events
        events = asyncio.run(check_events(events, log_fn=logger.info))
        ovp_count = sum(1 for e in events if e.get("originalpreis_pro_karte") is not None)
        logger.info("OVP: %d Events mit Originalpreis.", ovp_count)
    except Exception as e:
        logger.warning("OVP-Check fehlgeschlagen (nicht kritisch): %s", e)

    # 6. Excel schreiben
    logger.info("=== EXCEL SCHREIBEN ===")
    from export.excel_writer import finalisiere_lauf
    stats = finalisiere_lauf(events, EXCEL_PATH)
    logger.info("Excel-Stats: %s", stats)

    # 7. Google Drive
    logger.info("=== GOOGLE DRIVE UPLOAD ===")
    try:
        from export.gdrive_upload import upload_to_gdrive
        ok = upload_to_gdrive(EXCEL_PATH)
        logger.info("Google Drive: %s", "OK" if ok else "fehlgeschlagen")
    except Exception as e:
        logger.warning("Google Drive Upload fehlgeschlagen: %s", e)

    elapsed = time.time() - t0
    logger.info(
        "=== REPARSE FERTIG in %.0f Min | Events: %d | Excel: %s ===",
        elapsed / 60, len(events), stats,
    )


if __name__ == "__main__":
    main()
