"""Regression test: TARGET_URL must use sort=3 (newest first).

sort=5 (oldest first) causes the age-cutoff early-stop to fire on the very
first listing, resulting in 0 scraped ads.  This test pins sort=3 so the
bug cannot silently reappear.
"""
from scraper.willhaben_scraper import TARGET_URL


def test_target_url_uses_sort3():
    """sort=3 (neueste zuerst) muss in TARGET_URL enthalten sein.

    sort=5 (älteste zuerst) würde den Cutoff-Early-Stop bei der ersten
    Anzeige auslösen und 0 Ergebnisse liefern (Phase-B-Regression C07).
    """
    assert "sort=3" in TARGET_URL, (
        f"TARGET_URL muss 'sort=3' (neueste zuerst) enthalten, gefunden: {TARGET_URL}"
    )


def test_target_url_does_not_use_sort5():
    """Explizit sicherstellen dass sort=5 (älteste zuerst) nicht verwendet wird."""
    assert "sort=5" not in TARGET_URL, (
        f"TARGET_URL enthält 'sort=5' (älteste zuerst) — das bricht den Cutoff-Early-Stop."
    )
