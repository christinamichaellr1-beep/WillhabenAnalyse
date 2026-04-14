"""
gdrive_upload.py

Lädt die Excel-Datei nach Google Drive hoch.

Strategie (in Reihenfolge):
  1. Lokaler Google Drive Sync-Ordner gefunden → Datei hineinkopieren (sofort sync)
  2. gdrive CLI vorhanden → Hochladen via CLI
  3. Weder noch → Warnung + Setup-Anleitung loggen, kein Absturz

Google Drive Sync-Ordner-Kandidaten (macOS):
  ~/Library/CloudStorage/GoogleDrive-*/My Drive/
  ~/Google Drive/
  ~/Google Drive - *
"""
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Unterordner im Google Drive, in den die Datei kopiert wird
GDRIVE_SUBFOLDER = "WillhabenAnalyse"

# ---------------------------------------------------------------------------
# Auto-Detection: Google Drive Sync-Ordner
# ---------------------------------------------------------------------------

def _find_gdrive_sync_folder() -> Path | None:
    """
    Gibt den ersten gefundenen Google Drive My-Drive-Ordner zurück oder None.
    """
    candidates = [
        # Google Drive for Desktop (neu, macOS 12+)
        *sorted(Path.home().glob("Library/CloudStorage/GoogleDrive-*/My Drive")),
        # Deutsch: "Meine Ablage" = "My Drive"
        *sorted(Path.home().glob("Library/CloudStorage/GoogleDrive-*/Meine Ablage")),
        *sorted(Path.home().glob("Library/CloudStorage/GoogleDrive-*")),
        # Ältere Versionen
        Path.home() / "Google Drive",
        *sorted(Path.home().glob("Google Drive - *")),
        # Backup and Sync
        Path.home() / "Google Drive" / "My Drive",
    ]
    for path in candidates:
        if path.exists() and path.is_dir():
            logger.info("Google Drive Sync-Ordner gefunden: %s", path)
            return path
    return None


# ---------------------------------------------------------------------------
# Upload via Sync-Ordner
# ---------------------------------------------------------------------------

def _upload_via_sync(excel_path: Path, sync_root: Path) -> bool:
    target_dir = sync_root / GDRIVE_SUBFOLDER
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / excel_path.name
        shutil.copy2(excel_path, dest)
        logger.info("Google Drive: Datei kopiert nach %s", dest)
        return True
    except Exception as exc:
        logger.error("Google Drive Sync-Kopie fehlgeschlagen: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Upload via gdrive CLI
# ---------------------------------------------------------------------------

def _find_gdrive_cli() -> str | None:
    for name in ("gdrive", "gdrive3", "gdrive2"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _upload_via_cli(excel_path: Path, cli_path: str) -> bool:
    """
    Hochladen via gdrive CLI.
    Versucht erst ein Update (falls Datei bereits existiert), dann Upload.
    """
    try:
        # gdrive3 syntax: gdrive files upload --print-only-id <file>
        result = subprocess.run(
            [cli_path, "files", "upload", str(excel_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            logger.info("Google Drive CLI Upload erfolgreich: %s", result.stdout.strip())
            return True
        # Fallback: gdrive2 syntax
        result2 = subprocess.run(
            [cli_path, "upload", str(excel_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result2.returncode == 0:
            logger.info("Google Drive CLI Upload erfolgreich.")
            return True
        logger.warning("gdrive CLI Fehler: %s", (result.stderr or result2.stderr).strip())
        return False
    except subprocess.TimeoutExpired:
        logger.warning("gdrive CLI Timeout")
        return False
    except Exception as exc:
        logger.error("gdrive CLI Exception: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_to_gdrive(excel_path: Path) -> bool:
    """
    Lädt die Excel-Datei nach Google Drive hoch.
    Gibt True zurück wenn erfolgreich, False sonst.
    Wirft keine Exceptions – Fehler werden nur geloggt.
    """
    if not excel_path.exists():
        logger.warning("Excel-Datei nicht gefunden: %s", excel_path)
        return False

    # Strategie 1: Sync-Ordner
    sync_folder = _find_gdrive_sync_folder()
    if sync_folder:
        return _upload_via_sync(excel_path, sync_folder)

    # Strategie 2: CLI
    cli = _find_gdrive_cli()
    if cli:
        logger.info("Nutze gdrive CLI: %s", cli)
        return _upload_via_cli(excel_path, cli)

    # Kein Weg gefunden
    logger.warning(
        "Google Drive nicht konfiguriert. Excel-Datei NICHT hochgeladen.\n"
        "Setup-Optionen:\n"
        "  A) Google Drive for Desktop installieren: https://www.google.com/drive/download/\n"
        "     → Datei wird danach automatisch in den Sync-Ordner kopiert.\n"
        "  B) gdrive CLI installieren: brew install gdrive\n"
        "     → Dann: gdrive account add (einmalige Authentifizierung)"
    )
    return False
