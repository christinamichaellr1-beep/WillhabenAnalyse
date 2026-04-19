"""
ovp_logic.py

Pure functions for resolving the final OVP from extracted vs. manual input.
No side effects, no Excel dependency.
"""
import logging
import warnings
from typing import Optional

logger = logging.getLogger(__name__)

_KONFLIKT_SCHWELLE = 0.05  # 5% deviation triggers conflict


def berechne_finaler_ovp(
    ovp_extrahiert: Optional[float],
    ovp_manuell: Optional[float],
) -> tuple[Optional[float], str]:
    """Resolves the final OVP from extracted and manual values.

    Returns:
        (ovp_final, quelle) where quelle is one of:
        "", "extrahiert", "manuell", "beide_übereinstimmend", "konflikt"

    Rules:
    - Both None/empty → (None, "")
    - Only manuell → (manuell, "manuell")
    - Only extrahiert → (extrahiert, "extrahiert")
    - Both present, deviation < 5% → (manuell, "beide_übereinstimmend")
    - Both present, deviation ≥ 5% → (manuell, "konflikt") + log warning
    """
    ext = _parse_float(ovp_extrahiert)
    man = _parse_float(ovp_manuell)

    if ext is None and man is None:
        return None, ""
    if man is None:
        return ext, "extrahiert"
    if ext is None:
        return man, "manuell"

    # Both present
    abweichung = abs(ext - man) / max(abs(ext), abs(man))
    if abweichung < _KONFLIKT_SCHWELLE:
        return man, "beide_übereinstimmend"
    else:
        logger.warning(
            "OVP-Konflikt: extrahiert=%.2f, manuell=%.2f, Abweichung=%.1f%%",
            ext, man, abweichung * 100,
        )
        return man, "konflikt"


def _parse_float(value: object) -> Optional[float]:
    """Converts value to float, returns None for falsy/invalid."""
    if value is None or value == "":
        return None
    try:
        f = float(value)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def validiere_ovp_anbieter_link(url: Optional[str]) -> bool:
    """Soft validation: returns True if URL starts with http:// or https://, or is empty."""
    if not url or not str(url).strip():
        return True  # empty is valid (not yet filled)
    return str(url).strip().startswith(("http://", "https://"))
