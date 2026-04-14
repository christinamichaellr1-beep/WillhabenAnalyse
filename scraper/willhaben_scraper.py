"""
willhaben_scraper.py

Scrapt alle Konzert-Anzeigen von willhaben.at.
Gibt pro Anzeige ein vollständiges Dict zurück + speichert Rohtext in raw_cache/.

Rückgabe-Dict pro Anzeige:
  id, link, titel, preis_roh, text_komplett,
  verkäufer_id, verkäufername, verkäufertyp, mitglied_seit, scraped_at
"""
import asyncio
import json
import re
import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_CACHE = BASE_DIR / "data" / "raw_cache"
RAW_CACHE.mkdir(parents=True, exist_ok=True)

TARGET_URL = (
    "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/"
    "tickets-gutscheine/konzerte-musikfestivals-6702"
    "?rows=90&isNavigation=true&areaId=900"
)
MAX_LIST_PAGES = 5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _normalize_url(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if "/iad/kaufen-und-verkaufen/d/" not in raw:
        return None
    return urljoin("https://www.willhaben.at", raw).split("?", 1)[0]


def _extract_id_from_url(url: str) -> str | None:
    """Letzte numerische Sequenz in der URL als Willhaben-ID."""
    m = re.search(r"-(\d+)/?$", url)
    return m.group(1) if m else None


async def _dismiss_cookies(page) -> None:
    selectors = [
        "button#didomi-notice-agree-button",
        "button:has-text('Cookies akzeptieren')",
        "button:has-text('Annehmen und Schließen')",
    ]
    for sel in selectors:
        try:
            await page.locator(sel).first.click(timeout=3000)
            await asyncio.sleep(1)
            return
        except Exception:
            continue


async def _collect_listing_urls(page, seen: set) -> list[str]:
    """Sammelt URLs aus JSON-LD und Anchor-Tags auf einer Übersichtsseite."""
    urls: list[str] = []

    # JSON-LD ItemList
    scripts = await page.locator("script[type='application/ld+json']").all_text_contents()
    for raw in scripts:
        try:
            payload = json.loads(raw or "")
        except Exception:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict) or item.get("@type") != "ItemList":
                continue
            for el in item.get("itemListElement", []):
                u = _normalize_url(el.get("url") if isinstance(el, dict) else None)
                if u and u not in seen:
                    seen.add(u)
                    urls.append(u)

    # Anchor fallback
    raw_links = await page.eval_on_selector_all(
        "a[href*='/iad/kaufen-und-verkaufen/d/']",
        "els => els.map(e => e.getAttribute('href'))",
    )
    for raw in raw_links:
        u = _normalize_url(raw)
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    return urls


async def _parse_detail_page(page, url: str) -> dict:
    """Extrahiert alle Felder aus einer Willhaben-Detailseite."""
    ad_id = _extract_id_from_url(url) or url

    # Volltext
    text_komplett: str = ""
    try:
        text_komplett = await page.evaluate("document.body ? document.body.innerText : ''")
    except Exception:
        pass

    # Titel
    titel = ""
    for sel in ["h1", "[data-testid='ad-detail-header'] h1", "h1.sc-item-title"]:
        try:
            titel = (await page.locator(sel).first.inner_text(timeout=3000)).strip()
            if titel:
                break
        except Exception:
            continue

    # Preis (Rohtext)
    preis_roh = ""
    for sel in [
        "[data-testid='price-box-price-value']",
        "[data-testid='ad-price']",
        "span.price",
        "span:has-text('€')",
    ]:
        try:
            preis_roh = (await page.locator(sel).first.inner_text(timeout=2000)).strip()
            if preis_roh:
                break
        except Exception:
            continue
    # Fallback via Regex aus Volltext
    if not preis_roh:
        m = re.search(r"(\d[\d\.,]* ?€|\€ ?\d[\d\.,]*)", text_komplett)
        if m:
            preis_roh = m.group(0)

    # Verkäufertyp (Privat / Händler)
    verkäufertyp = "unbekannt"
    if re.search(r"Gewerblicher Anbieter|Händler|Gewerblich", text_komplett, re.IGNORECASE):
        verkäufertyp = "Händler"
    elif re.search(r"Privater Anbieter|Privatperson|Privat", text_komplett, re.IGNORECASE):
        verkäufertyp = "Privat"

    # Verkäufer-ID aus Profil-Link (zuverlässigste Methode)
    # Willhaben-URL-Format: /iad/kaufen-und-verkaufen/vendor/{id}/
    verkäufer_id = ""
    verkäufername = ""
    mitglied_seit = ""

    try:
        vendor_hrefs = await page.eval_on_selector_all(
            "a[href*='/vendor/']",
            "els => els.map(e => e.getAttribute('href'))",
        )
        for href in vendor_hrefs:
            m = re.search(r"/vendor/(\d+)", href or "")
            if m:
                verkäufer_id = m.group(1)
                break
    except Exception:
        pass

    # Fallback: Verkäufer-ID aus JSON-LD
    if not verkäufer_id:
        scripts = await page.locator("script[type='application/ld+json']").all_text_contents()
        for raw in scripts:
            try:
                payload = json.loads(raw or "")
            except Exception:
                continue
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if not isinstance(item, dict):
                    continue
                seller = item.get("seller") or item.get("author") or {}
                if isinstance(seller, dict):
                    verkäufername = verkäufername or seller.get("name", "")
                    verkäufer_id = verkäufer_id or str(seller.get("identifier", ""))

    # Verkäufername aus DOM falls noch nicht gefunden
    if not verkäufername:
        for sel in [
            "[data-testid='seller-profile-name']",
            "[class*='SellerName']",
            "[class*='UserName']",
        ]:
            try:
                name = (await page.locator(sel).first.inner_text(timeout=2000)).strip()
                if name:
                    verkäufername = name
                    break
            except Exception:
                continue

    # Letzter Fallback: Name aus Volltext nach "Verkäuferdetails"
    if not verkäufername:
        m = re.search(r"Verkäuferdetails\s*\n\s*(.+)", text_komplett)
        if m:
            verkäufername = m.group(1).strip()

    # Mitglied seit aus Text
    # Willhaben-Format: "User:in seit 07/2009" oder "Mitglied seit 07/2009"
    m = re.search(
        r"(?:User:in seit|Mitglied seit|seit)\s+(\d{2}/\d{4})",
        text_komplett,
        re.IGNORECASE,
    )
    if m:
        mitglied_seit = m.group(1).strip()

    return {
        "id": ad_id,
        "link": url,
        "titel": titel,
        "preis_roh": preis_roh,
        "text_komplett": text_komplett,
        "verkäufertyp": verkäufertyp,
        "verkäufer_id": verkäufer_id,
        "verkäufername": verkäufername,
        "mitglied_seit": mitglied_seit,
        "scraped_at": datetime.datetime.now().isoformat(),
    }


def _save_raw_cache(ad: dict) -> None:
    path = RAW_CACHE / f"{ad['id']}.json"
    path.write_text(json.dumps(ad, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_raw_cache(ad_id: str) -> dict | None:
    path = RAW_CACHE / f"{ad_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

async def scrape(max_pages: int = MAX_LIST_PAGES, headless: bool = True) -> list[dict]:
    """
    Scrapet Willhaben Ticket-Marktplatz.
    Gibt eine Liste von Anzeigen-Dicts zurück.
    Bereits gecachte Anzeigen werden nicht erneut besucht.
    """
    results: list[dict] = []
    seen_urls: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="de-AT",
        )
        page = await context.new_page()
        page.set_default_timeout(90000)

        all_ad_urls: list[str] = []

        try:
            # ---- Übersichtsseiten ----
            for page_num in range(1, max_pages + 1):
                url = f"{TARGET_URL}&page={page_num}"
                _log(f"Übersicht Seite {page_num}: {url}")
                loaded = False
                for attempt in range(1, 3):
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        loaded = True
                        break
                    except PlaywrightTimeoutError:
                        _log(f"Timeout Seite {page_num} (Versuch {attempt}/2)")

                if not loaded:
                    _log(f"Fehler: Seite {page_num} nicht ladbar – übersprungen.")
                    continue

                if page_num == 1:
                    await _dismiss_cookies(page)

                await page.wait_for_timeout(2000)
                for _ in range(5):
                    await page.mouse.wheel(0, 1800)
                    await page.wait_for_timeout(400)

                new_urls = await _collect_listing_urls(page, seen_urls)
                all_ad_urls.extend(new_urls)
                _log(f"  → {len(new_urls)} neue Links (gesamt: {len(all_ad_urls)})")

            _log(f"Starte Detail-Scraping für {len(all_ad_urls)} Anzeigen …")

            # ---- Detailseiten ----
            for idx, ad_url in enumerate(all_ad_urls, 1):
                ad_id = _extract_id_from_url(ad_url) or ad_url

                cached = _load_raw_cache(ad_id)
                if cached:
                    _log(f"  ({idx}/{len(all_ad_urls)}) Cache-Hit: {ad_id}")
                    results.append(cached)
                    continue

                _log(f"  ({idx}/{len(all_ad_urls)}) Lade: {ad_url}")
                ok = False
                for attempt in range(1, 3):
                    try:
                        await page.goto(ad_url, wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(1200)
                        ad = await _parse_detail_page(page, ad_url)
                        _save_raw_cache(ad)
                        results.append(ad)
                        ok = True
                        break
                    except Exception as exc:
                        _log(f"  Fehler Detailseite Versuch {attempt}/2: {exc}")

                if not ok:
                    results.append({
                        "id": ad_id,
                        "link": ad_url,
                        "titel": "",
                        "preis_roh": "",
                        "text_komplett": "FEHLER: Seite nicht ladbar",
                        "verkäufertyp": "unbekannt",
                        "verkäufer_id": "",
                        "verkäufername": "",
                        "mitglied_seit": "",
                        "scraped_at": datetime.datetime.now().isoformat(),
                    })

                await page.wait_for_timeout(600)

        except Exception as exc:
            _log(f"FATALER FEHLER: {exc}")
        finally:
            await browser.close()

    _log(f"Scraping abgeschlossen. {len(results)} Anzeigen.")
    return results


if __name__ == "__main__":
    ads = asyncio.run(scrape())
    print(json.dumps(ads[:2], ensure_ascii=False, indent=2))
