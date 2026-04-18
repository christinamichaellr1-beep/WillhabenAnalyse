"""
willhaben_scraper.py

Scrapt alle Konzert-Anzeigen von willhaben.at.
Gibt pro Anzeige ein vollständiges Dict zurück + speichert Rohtext in raw_cache/.

Rückgabe-Dict pro Anzeige:
  id, link, titel, preis_roh, text_komplett,
  verkäufer_id, verkäufername, verkäufertyp, mitglied_seit, scraped_at,
  eingestellt_am
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
    "?rows=90&isNavigation=true&areaId=900&sort=3"
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


def _is_first_run() -> bool:
    """True wenn raw_cache leer ist (noch keine Anzeigen gecacht wurden)."""
    return not any(RAW_CACHE.glob("*.json"))


def _parse_willhaben_date(text_komplett: str, scripts: list[str]) -> datetime.date | None:
    """
    Parst das Einstelldatum aus dem Volltext oder JSON-LD einer Willhaben-Anzeige.
    Unterstützt: ISO-Datum (JSON-LD), 'Heute', 'Gestern', 'vor X Tagen', 'DD.MM.YYYY'.
    """
    today = datetime.date.today()

    # JSON-LD datePosted (zuverlässigste Methode, ISO-Format)
    for raw in scripts:
        try:
            payload = json.loads(raw or "")
        except Exception:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            date_str = item.get("datePosted") or item.get("dateCreated") or item.get("datePublished")
            if date_str:
                try:
                    return datetime.date.fromisoformat(str(date_str)[:10])
                except ValueError:
                    pass

    # "Heute" → today
    if re.search(r"\bHeute\b", text_komplett, re.IGNORECASE):
        return today

    # "Gestern" → yesterday
    if re.search(r"\bGestern\b", text_komplett, re.IGNORECASE):
        return today - datetime.timedelta(days=1)

    # "vor X Tagen"
    m = re.search(r"vor\s+(\d+)\s+Tag", text_komplett, re.IGNORECASE)
    if m:
        return today - datetime.timedelta(days=int(m.group(1)))

    # "DD.MM.YYYY"
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text_komplett)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    return None


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

    # JSON-LD scripts (für Datum und Verkäuferinfos)
    scripts = await page.locator("script[type='application/ld+json']").all_text_contents()

    # Einstelldatum
    eingestellt_am: str = ""
    parsed_date = _parse_willhaben_date(text_komplett, scripts)
    if parsed_date:
        eingestellt_am = parsed_date.isoformat()

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
        "eingestellt_am": eingestellt_am,
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

async def scrape(
    max_pages: int = MAX_LIST_PAGES,
    headless: bool = True,
    max_age_days: int | None = None,
    max_listings: int | None = None,
) -> list[dict]:
    """
    Scrapt Willhaben Ticket-Marktplatz, sortiert nach neuesten Anzeigen (sort=3).

    max_age_days:  Maximales Alter einer Anzeige in Tagen.
                   None = Wert aus config.json oder Auto-Detect.
    max_listings:  Sobald diese Anzahl qualifizierender Anzeigen gesammelt ist,
                   stoppen sowohl Übersichtsseiten- als auch Detailseiten-Loop.
                   Übersichtsseiten werden auf ceil(max_listings/90)+1 begrenzt.

    Bereits gecachte Anzeigen (raw_cache/{id}.json existiert) werden
    übersprungen und nicht erneut besucht.
    """
    # Auto-detect max_age_days wenn nicht explizit angegeben
    if max_age_days is None:
        config_path = BASE_DIR / "config.json"
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            if _is_first_run():
                max_age_days = cfg.get("first_run_max_age_days", 3)
                _log(f"Erster Lauf erkannt → max_age_days={max_age_days}")
            else:
                max_age_days = cfg.get("max_age_days", 1)
        except Exception:
            max_age_days = 3 if _is_first_run() else 1

    cutoff_date = datetime.date.today() - datetime.timedelta(days=max_age_days)
    _log(f"Scraping neue Anzeigen (max_age_days={max_age_days}, cutoff={cutoff_date})")

    results: list[dict] = []
    seen_urls: set[str] = set()
    stop_scraping = False

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
        # Mit sort=3 (neueste zuerst) reichen wenige Seiten für max_listings Treffer.
        pages_to_load = min(max_pages, (max_listings // 90) + 2) if max_listings else max_pages

        try:
            # ---- Übersichtsseiten ----
            for page_num in range(1, pages_to_load + 1):
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
                if stop_scraping:
                    break

                ad_id = _extract_id_from_url(ad_url) or ad_url

                # Bereits gecacht → überspringen (zählt nicht für Alters-Check,
                # da es sich um bereits verarbeitete Anzeigen handelt)
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

                        # Alters-Check: Anzeige zu alt → überspringen
                        if ad.get("eingestellt_am"):
                            ad_date = datetime.date.fromisoformat(ad["eingestellt_am"])
                            if ad_date < cutoff_date:
                                _log(
                                    f"  ({idx}) Anzeige {ad_id} vom {ad_date} "
                                    f"ist älter als cutoff {cutoff_date} → übersprungen."
                                )
                                ok = True
                                break

                        _save_raw_cache(ad)
                        results.append(ad)
                        ok = True
                        if max_listings is not None and len(results) >= max_listings:
                            _log(f"  → max_listings={max_listings} erreicht – stoppe.")
                            stop_scraping = True
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
                        "eingestellt_am": "",
                        "scraped_at": datetime.datetime.now().isoformat(),
                    })

                if not stop_scraping:
                    await page.wait_for_timeout(600)

        except Exception as exc:
            _log(f"FATALER FEHLER: {exc}")
        finally:
            await browser.close()

    skipped = len(all_ad_urls) - len(results)
    _log(f"Scraping abgeschlossen. {len(results)} Anzeigen verarbeitet, {skipped} übersprungen.")
    return results


if __name__ == "__main__":
    ads = asyncio.run(scrape())
    print(json.dumps(ads[:2], ensure_ascii=False, indent=2))
