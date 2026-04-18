"""
launchd_manager.py

Generates launchd plist XML and manages launchctl for scheduling
the WillhabenAnalyse pipeline on macOS.
"""
import subprocess
from pathlib import Path

# Path to the plist template relative to this file's location
_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "launchd.plist.template"

_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


def generate_plist(
    label: str,
    python_path: str,
    project_dir: str,
    model: str,
    max_listings: int | None,
    hour: int,
    minute: int,
) -> str:
    """Returns plist XML string by rendering the template at app/templates/launchd.plist.template"""
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")

    if max_listings is not None:
        max_listings_arg = f"<string>--max-listings={max_listings}</string>"
    else:
        max_listings_arg = ""

    return template.format(
        LABEL=label,
        PYTHON_PATH=python_path,
        PROJECT_DIR=project_dir,
        MODEL=model,
        MAX_LISTINGS_ARG=max_listings_arg,
        HOUR=hour,
        MINUTE=minute,
    )


def install_plist(plist_xml: str, label: str) -> tuple[bool, str]:
    """
    Writes plist to ~/Library/LaunchAgents/{label}.plist and runs launchctl load.
    Returns (success, message).
    """
    _LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    plist_path = _LAUNCH_AGENTS_DIR / f"{label}.plist"

    try:
        plist_path.write_text(plist_xml, encoding="utf-8")
    except OSError as exc:
        return False, f"Failed to write plist: {exc}"

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        return False, f"launchctl load failed: {err}"

    return True, f"Installed and loaded {plist_path}"


def uninstall_plist(label: str) -> tuple[bool, str]:
    """
    Runs launchctl unload and removes plist file.
    Returns (success, message).
    """
    plist_path = _LAUNCH_AGENTS_DIR / f"{label}.plist"

    if plist_path.exists():
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return False, f"launchctl unload failed: {err}"

        try:
            plist_path.unlink()
        except OSError as exc:
            return False, f"Failed to remove plist file: {exc}"

        return True, f"Unloaded and removed {plist_path}"

    return False, f"Plist not found: {plist_path}"


def is_installed(label: str) -> bool:
    """Returns True if ~/Library/LaunchAgents/{label}.plist exists."""
    return (_LAUNCH_AGENTS_DIR / f"{label}.plist").exists()
