"""
reparse_test.py

Testet den neuen Gemma-Prompt auf 20 zufälligen cached Anzeigen.
Vergleicht OVP-Treffer vorher vs. nachher.
Falls Verbesserung: löscht alle parse_cache und parst alle 453 neu.
Erstellt dann neue Excel und lädt auf Google Drive hoch.

Verwendung:
    python reparse_test.py [--force-all]
"""
import json
import random
import sys
import shutil
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Pfade – immer Haupt-Repo, nicht Worktree
# Worktree liegt unter .claude/worktrees/cranky-wu/, daher 4 Ebenen rauf
MAIN_REPO = Path(__file__).resolve().parent.parent.parent.parent  # .../WillhabenAnalyse
RAW_CACHE_DIR = MAIN_REPO / "data" / "raw_cache"
PARSE_CACHE_DIR = MAIN_REPO / "data" / "parse_cache"
EXCEL_PATH = MAIN_REPO / "data" / "willhaben_markt.xlsx"

# Worktree-Code ins sys.path einfügen
WORKTREE = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKTREE))

from parser.gemma_parser import parse_ad, PARSE_CACHE_DIR as _PARSER_CACHE_DIR

# Parser-Modul auf das richtige Cache-Verzeichnis zeigen lassen
import parser.gemma_parser as _gp
_gp.PARSE_CACHE_DIR = PARSE_CACHE_DIR
PARSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def count_ovp(events: list[dict]) -> int:
    return sum(1 for e in events if e.get("originalpreis_pro_karte") is not None)


def load_raw_cache_all() -> list[dict]:
    ads = []
    for f in sorted(RAW_CACHE_DIR.glob("*.json")):
        try:
            ads.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return ads


def load_parse_cache(ad_id: str) -> list[dict] | None:
    p = PARSE_CACHE_DIR / f"{ad_id}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_parse_cache(ad_id: str, events: list[dict]):
    p = PARSE_CACHE_DIR / f"{ad_id}.json"
    p.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


def reparse_ad(ad: dict) -> list[dict]:
    """Parst eine Anzeige mit neuem Prompt, speichert Cache."""
    ad_id = str(ad.get("id", ""))
    events = parse_ad(ad)
    if ad_id:
        save_parse_cache(ad_id, events)
    return events


def test_20_random(all_ads: list[dict]) -> tuple[int, int, int]:
    """
    Testet 20 zufällige Anzeigen. Gibt zurück: (vorher_ovp, nachher_ovp, anzahl).
    """
    # Nur Anzeigen mit existierendem parse_cache nehmen
    cached_ads = [a for a in all_ads if (PARSE_CACHE_DIR / f"{a['id']}.json").exists()]
    if len(cached_ads) < 20:
        logger.warning("Nur %d gecachte Anzeigen vorhanden, nehme alle.", len(cached_ads))
        sample = cached_ads
    else:
        sample = random.sample(cached_ads, 20)

    vorher_ovp = 0
    nachher_ovp = 0

    for ad in sample:
        ad_id = str(ad.get("id", ""))

        # Vorher: aus bestehendem Cache
        old_events = load_parse_cache(ad_id) or []
        vorher_ovp += count_ovp(old_events)

        # Nachher: neu parsen (löscht alten Cache implizit durch Überschreiben)
        new_events = reparse_ad(ad)
        nachher_ovp += count_ovp(new_events)

        logger.info(
            "  %s | vorher OVP=%s | nachher OVP=%s",
            ad_id,
            count_ovp(old_events),
            count_ovp(new_events),
        )

    return vorher_ovp, nachher_ovp, len(sample)


def reparse_all(all_ads: list[dict]) -> list[dict]:
    """Löscht alle parse_cache und parst alle Anzeigen neu."""
    logger.info("Lösche alle %d parse_cache Dateien...", len(list(PARSE_CACHE_DIR.glob("*.json"))))
    for f in PARSE_CACHE_DIR.glob("*.json"):
        f.unlink()

    all_events = []
    total = len(all_ads)
    for i, ad in enumerate(all_ads, 1):
        ad_id = str(ad.get("id", ""))
        logger.info("Reparse %d/%d: %s", i, total, ad_id)
        events = reparse_ad(ad)
        all_events.extend(events)

    return all_events


def build_excel(events: list[dict]):
    """Löscht alte Excel und erstellt neue."""
    if EXCEL_PATH.exists():
        EXCEL_PATH.unlink()
        logger.info("Alte Excel gelöscht: %s", EXCEL_PATH)

    from export.excel_writer import upsert_events
    stats = upsert_events(events, EXCEL_PATH)
    logger.info("Excel erstellt: %s | Stats: %s", EXCEL_PATH, stats)
    return stats


def upload_drive():
    from export.gdrive_upload import upload_to_gdrive
    ok = upload_to_gdrive(EXCEL_PATH)
    logger.info("Google Drive Upload: %s", "OK" if ok else "FEHLER")
    return ok


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-all", action="store_true",
                    help="Alle Anzeigen ohne Vortest neu parsen")
    args = ap.parse_args()

    logger.info("Lade raw_cache (%s)...", RAW_CACHE_DIR)
    all_ads = load_raw_cache_all()
    logger.info("%d Anzeigen gefunden.", len(all_ads))

    if not all_ads:
        logger.error("Kein raw_cache vorhanden. Zuerst Scraping ausführen.")
        sys.exit(1)

    if args.force_all:
        logger.info("--force-all: Überspringe Test, parse direkt alle neu.")
        do_full_reparse = True
    else:
        # ---- Schritt 1: 20 zufällige testen ----
        logger.info("=== TEST: 20 zufällige Anzeigen mit neuem Prompt ===")
        random.seed(42)
        vorher, nachher, n = test_20_random(all_ads)
        print(f"\n{'='*50}")
        print(f"VERGLEICH (n={n} Anzeigen):")
        print(f"  OVP vorher:  {vorher}")
        print(f"  OVP nachher: {nachher}")
        print(f"  Differenz:   {nachher - vorher:+d}")
        print(f"{'='*50}\n")

        if nachher > vorher:
            print("✓ Verbesserung erkannt! Starte vollständigen Reparse...")
            do_full_reparse = True
        elif nachher == vorher:
            print("~ Kein Unterschied. Trotzdem vollständigen Reparse starten? (j/n): ", end="")
            ans = input().strip().lower()
            do_full_reparse = ans == "j"
        else:
            print("✗ Verschlechterung! Kein vollständiger Reparse.")
            do_full_reparse = False

    if do_full_reparse:
        # ---- Schritt 2: Alle neu parsen ----
        logger.info("=== VOLLSTÄNDIGER REPARSE aller %d Anzeigen ===", len(all_ads))
        all_events = reparse_all(all_ads)
        ovp_total = count_ovp(all_events)
        logger.info("Fertig: %d Events, davon %d mit OVP", len(all_events), ovp_total)

        # ---- Schritt 3: Excel neu erstellen ----
        logger.info("=== EXCEL neu erstellen ===")
        stats = build_excel(all_events)
        print(f"\nExcel Stats: {stats}")

        # ---- Schritt 4: Google Drive Upload ----
        logger.info("=== GOOGLE DRIVE UPLOAD ===")
        upload_drive()
    else:
        logger.info("Kein vollständiger Reparse. Fertig.")
