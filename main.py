"""
WillhabenAnalyse – Haupt-Orchestrator.
Pipeline: scrape → parse → ovp_check → excel_write
Scheduling via `schedule`-Library.
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Callable

import schedule

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Fehler beim Lesen von config.json: %s", exc)
    return {
        "schedule": {"scrape_interval_minutes": 120, "ovp_interval_minutes": 60, "enabled": False},
        "export_path": str(BASE_DIR / "data" / "willhaben_analyse.xlsx"),
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _select_parse_ads(parser_version: str):
    if parser_version == "v2":
        from parser.v2 import parse_ads
    else:
        from parser.gemma_parser import parse_ads
    return parse_ads


def run_pipeline(
    log_callback: Callable[[str], None] | None = None,
    parser_version: str = "v2",
    model_override: str | None = None,
    dry_run: bool = False,
    max_listings: int | None = None,
) -> dict:
    """
    Führt die komplette Pipeline aus:
    1. Scraping
    2. Parsing (Gemma/Ollama) — parser_version wählt v1 oder v2
    3. OVP-Check
    4. Excel-Update (übersprungen bei dry_run=True)

    Gibt Statistik-Dict zurück.
    """
    def _log(msg: str):
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    cfg = load_config()
    excel_path = Path(cfg.get("export_path", str(BASE_DIR / "data" / "willhaben_analyse.xlsx")))
    excel_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "scraped": 0,
        "parsed_events": 0,
        "ovp_checked": 0,
        "excel_inserted": 0,
        "excel_updated": 0,
        "errors": [],
    }

    # ---- 1. Scraping ----
    _log("=== SCHRITT 1: Scraping ===")
    try:
        from scraper.willhaben_scraper import scrape
        ads = asyncio.run(scrape())
        stats["scraped"] = len(ads)
        _log(f"Scraping: {len(ads)} Anzeigen gefunden.")
    except Exception as exc:
        logger.exception("Fehler beim Scraping")
        stats["errors"].append(f"Scraping: {exc}")
        ads = []

    if not ads:
        _log("Keine Anzeigen – Pipeline abgebrochen.")
        return stats

    if max_listings is not None:
        ads = ads[:max_listings]
        _log(f"--max-listings: auf {max_listings} begrenzt.")

    # ---- 2. Parsing ----
    _log(f"=== SCHRITT 2: Parsing ({parser_version}) ===")
    try:
        parse_ads = _select_parse_ads(parser_version)
        kwargs: dict = {}
        if parser_version == "v2" and model_override:
            kwargs["model"] = model_override
        events = parse_ads(ads, **kwargs)
        stats["parsed_events"] = len(events)
        _log(f"Parsing: {len(events)} Events extrahiert.")
    except Exception as exc:
        logger.exception("Fehler beim Parsing")
        stats["errors"].append(f"Parsing: {exc}")
        events = []

    # ---- 3. OVP-Check ----
    # OVP wird pro Event (name+datum) einmalig geprüft, Ergebnis direkt in events eingetragen
    _log("=== SCHRITT 3: OVP-Check ===")
    try:
        from ovp.ovp_checker import check_events
        events = asyncio.run(check_events(events, log_fn=_log))
        ovp_found = sum(1 for e in events if e.get("originalpreis_pro_karte") is not None)
        stats["ovp_checked"] = ovp_found
        _log(f"OVP: {ovp_found} Events mit Originalpreis gefunden.")
    except Exception as exc:
        logger.warning("OVP-Check fehlgeschlagen (nicht kritisch): %s", exc)

    # ---- 4. Excel ----
    if dry_run:
        _log("=== SCHRITT 4: Excel-Update (dry-run, übersprungen) ===")
        _log(f"=== PIPELINE FERTIG (dry-run): {stats} ===")
        return stats

    _log("=== SCHRITT 4: Excel-Update ===")
    if events:
        try:
            from export.excel_writer import upsert_events, archive_expired
            excel_stats = upsert_events(events, excel_path)
            stats["excel_inserted"] = excel_stats.get("inserted", 0)
            stats["excel_updated"] = excel_stats.get("updated", 0)
            _log(
                f"Excel: {excel_stats.get('inserted', 0)} neu, "
                f"{excel_stats.get('updated', 0)} aktualisiert, "
                f"{excel_stats.get('review_added', 0)} in Review Queue."
            )
            # Abgelaufene Events ins Archiv verschieben
            archived = archive_expired(excel_path)
            if archived:
                _log(f"Archiv: {archived} abgelaufene Events verschoben.")

            # ---- 4b. Google Drive Upload ----
            _log("=== SCHRITT 4b: Google Drive Upload ===")
            try:
                from export.gdrive_upload import upload_to_gdrive
                ok = upload_to_gdrive(excel_path, raw_cache_dir=BASE_DIR / "data" / "raw_cache")
                stats["gdrive_upload"] = ok
                _log(f"Google Drive: {'hochgeladen' if ok else 'nicht verfügbar (siehe Log)'}.")
            except Exception as exc:
                logger.warning("Google Drive Upload fehlgeschlagen (nicht kritisch): %s", exc)
                stats["gdrive_upload"] = False

        except Exception as exc:
            logger.exception("Fehler beim Excel-Update")
            stats["errors"].append(f"Excel: {exc}")

    _log(f"=== PIPELINE FERTIG: {stats} ===")
    return stats


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _setup_schedule(cfg: dict):
    sched_cfg = cfg.get("schedule", {})
    scrape_mins = sched_cfg.get("scrape_interval_minutes", 360)

    schedule.every(scrape_mins).minutes.do(run_pipeline)
    logger.info("Pipeline alle %d Minuten geplant.", scrape_mins)


def run_daemon():
    """Startet den Scheduling-Daemon (Endlosschleife)."""
    cfg = load_config()
    if not cfg.get("schedule", {}).get("enabled", False):
        logger.info("Scheduling deaktiviert. Einmaliger Run.")
        run_pipeline()
        return

    _setup_schedule(cfg)

    # Sofortiger erster Run
    run_pipeline()

    logger.info("Scheduler gestartet. STRG+C zum Beenden.")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="WillhabenAnalyse Pipeline")
    parser.add_argument("--gui", action="store_true", help="GUI starten")
    parser.add_argument("--once", action="store_true", help="Einmaliger Pipeline-Run")
    parser.add_argument("--daemon", action="store_true", help="Scheduling-Daemon starten")
    parser.add_argument("--ovp", action="store_true", help="Nur OVP-Check")
    parser.add_argument(
        "--model",
        choices=["gemma3:27b", "gemma4:26b", "gemma4:latest"],
        default=None,
        help="Ollama-Modell überschreiben (nur mit --parser-version v2 wirksam)",
    )
    parser.add_argument(
        "--parser-version",
        choices=["v1", "v2"],
        default="v2",
        dest="parser_version",
        help="Parser-Version: v2=parser/v2/ (default), v1=gemma_parser (Rollback)",
    )
    parser.add_argument(
        "--test-batch",
        type=int,
        metavar="N",
        dest="test_batch",
        help="Teste Parser auf ersten N raw_cache-Einträgen, kein Excel-Write",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Komplette Pipeline ohne Excel- und Drive-Write",
    )
    parser.add_argument(
        "--max-listings",
        type=int,
        default=None,
        metavar="N",
        dest="max_listings",
        help="Begrenze die Anzahl der zu parsenden Anzeigen auf N",
    )
    args = parser.parse_args()

    if args.test_batch:
        raw_cache_dir = BASE_DIR / "data" / "raw_cache"
        cached_ads = []
        for f in sorted(raw_cache_dir.glob("*.json"))[: args.test_batch]:
            try:
                cached_ads.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        if not cached_ads:
            print("Kein raw_cache vorhanden. Zuerst --once ausführen.")
            sys.exit(1)
        parse_ads = _select_parse_ads(args.parser_version)
        kwargs: dict = {}
        if args.parser_version == "v2" and args.model:
            kwargs["model"] = args.model
        events = parse_ads(cached_ads, use_cache=False, **kwargs)
        print(json.dumps(
            [
                {k: v for k, v in e.items()
                 if k in ("event_name", "event_datum", "confidence",
                          "modell", "pipeline_version", "parse_dauer_ms",
                          "originalpreis_pro_karte", "angebotspreis_gesamt")}
                for e in events
            ],
            indent=2, ensure_ascii=False,
        ))
    elif args.gui:
        from app.gui import main as gui_main
        gui_main()
    elif args.once:
        result = run_pipeline(
            parser_version=args.parser_version,
            model_override=args.model,
            dry_run=args.dry_run,
            max_listings=args.max_listings,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.ovp:
        raw_cache_dir = BASE_DIR / "data" / "raw_cache"
        cached_ads = []
        for f in sorted(raw_cache_dir.glob("*.json"))[:20]:
            try:
                cached_ads.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        if cached_ads:
            from parser.gemma_parser import parse_ads
            from ovp.ovp_checker import check_events
            events = parse_ads(cached_ads)
            results = asyncio.run(check_events(events))
            print(json.dumps(results[:5], indent=2, ensure_ascii=False))
        else:
            print("Kein raw_cache vorhanden. Zuerst --once ausführen.")
    elif args.daemon:
        run_daemon()
    else:
        # Default: GUI
        from app.gui import main as gui_main
        gui_main()
