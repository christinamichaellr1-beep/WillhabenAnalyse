"""
launchd_manager.py

Generates launchd plist XML and manages launchctl for scheduling
the WillhabenAnalyse pipeline on macOS.
"""
import subprocess
from pathlib import Path

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
    """Returns plist XML string built with plistlib — no template injection possible."""
    import plistlib

    program_args = [
        python_path,
        f"{project_dir}/main.py",
        "--once",
        "--parser-version=v2",
        f"--model={model}",
    ]
    if max_listings is not None:
        program_args.append(f"--max-listings={max_listings}")

    plist_data = {
        "Label": label,
        "ProgramArguments": program_args,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": f"{project_dir}/logs/launchd.log",
        "StandardErrorPath": f"{project_dir}/logs/launchd.log",
        "WorkingDirectory": project_dir,
        "RunAtLoad": False,
    }

    return plistlib.dumps(plist_data, fmt=plistlib.FMT_XML).decode("utf-8")


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
