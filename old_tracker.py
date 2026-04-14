import asyncio
import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

# --- Konfiguration ---
TARGET_URL = "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/tickets-gutscheine/konzerte-musikfestivals-6702?rows=90&isNavigation=true&areaId=900"
ACCOUNT = os.getenv("GOG_ACCOUNT", "christina.michael.l.r.1@gmail.com")
BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "scraping_protocol.log"
MAX_LIST_PAGES = 3


def log_event(message: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        # Logging darf den Lauf niemals abbrechen.
        pass


def reset_log_file() -> None:
    try:
        LOG_FILE.write_text("", encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] Konnte Logdatei nicht zurücksetzen: {exc}", flush=True)


def normalize_ad_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    raw_url = raw_url.strip()
    if not raw_url:
        return None

    # Relevante Anzeigen haben das Muster /iad/kaufen-und-verkaufen/d/...
    if "/iad/kaufen-und-verkaufen/d/" not in raw_url:
        return None

    absolute = urljoin("https://www.willhaben.at", raw_url)
    return absolute.split("?", 1)[0]


async def click_cookie_banner(page) -> None:
    selectors = [
        "button#didomi-notice-agree-button",
        "button#didomi-notice-agree-button span",
        "button:has-text('Cookies akzeptieren')",
        "button:has-text('Annehmen und Schließen')",
    ]

    for selector in selectors:
        try:
            await page.locator(selector).first.click(timeout=3000)
            log_event(f"Cookie-Banner akzeptiert via Selektor: {selector}")
            await asyncio.sleep(1)
            return
        except Exception:
            continue

    log_event("Kein Cookie-Banner gefunden oder bereits geschlossen.")


async def extract_urls_from_jsonld(page) -> list[str]:
    scripts = await page.locator("script[type='application/ld+json']").all_text_contents()
    urls: list[str] = []

    for raw in scripts:
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue

        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("@type") != "ItemList":
                continue

            for item in candidate.get("itemListElement", []):
                if not isinstance(item, dict):
                    continue
                normalized = normalize_ad_url(item.get("url"))
                if normalized:
                    urls.append(normalized)

    return urls


async def extract_urls_from_anchors(page) -> list[str]:
    raw_links = await page.eval_on_selector_all(
        "a[href*='/iad/kaufen-und-verkaufen/d/']",
        "elements => elements.map(e => e.getAttribute('href'))",
    )
    urls = []
    for raw in raw_links:
        normalized = normalize_ad_url(raw)
        if normalized:
            urls.append(normalized)
    return urls


async def scrape_willhaben() -> None:
    reset_log_file()
    log_event("START: Willhaben Tracker (Playwright robust)")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="de-AT",
        )
        page = await context.new_page()
        page.set_default_timeout(90000)

        ad_urls: list[str] = []
        seen = set()

        try:
            for page_num in range(1, MAX_LIST_PAGES + 1):
                url = f"{TARGET_URL}&page={page_num}"
                log_event(f"ÜBERSICHT: Lade Seite {page_num}: {url}")

                loaded = False
                for attempt in range(1, 3):
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        loaded = True
                        break
                    except PlaywrightTimeoutError:
                        log_event(f"Warnung: Timeout bei Seite {page_num} (Versuch {attempt}/2)")

                if not loaded:
                    log_event(f"FEHLER: Seite {page_num} konnte nicht stabil geladen werden.")
                    continue

                if page_num == 1:
                    await click_cookie_banner(page)

                await page.wait_for_timeout(2000)
                for _ in range(5):
                    await page.mouse.wheel(0, 1800)
                    await page.wait_for_timeout(500)

                jsonld_urls = await extract_urls_from_jsonld(page)
                anchor_urls = await extract_urls_from_anchors(page)
                page_urls = jsonld_urls + anchor_urls

                added = 0
                for ad_url in page_urls:
                    if ad_url in seen:
                        continue
                    seen.add(ad_url)
                    ad_urls.append(ad_url)
                    added += 1

                log_event(
                    "ÜBERSICHT: "
                    f"{added} neue Links auf Seite {page_num} gefunden "
                    f"(jsonld={len(jsonld_urls)}, anchors={len(anchor_urls)}, gesamt={len(ad_urls)})"
                )

            if not ad_urls:
                log_event("FEHLER: Keine Anzeigen-Links gefunden. Hauptursache sind meist selektoren/Timing/Blocker.")
                return

            extracted_texts: list[str] = []
            for idx, ad_url in enumerate(ad_urls, 1):
                log_event(f"DETAIL ({idx}/{len(ad_urls)}): Öffne {ad_url}")
                detail_ok = False

                for attempt in range(1, 3):
                    try:
                        await page.goto(ad_url, wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(1200)
                        content = await page.evaluate("document.body ? document.body.innerText : ''")
                        extracted_texts.append(f"LINK: {ad_url}\n\n{content}")
                        log_event(f"DETAIL: Kopiert ({len(content)} Zeichen, Versuch {attempt}/2).")
                        detail_ok = True
                        break
                    except Exception as exc:
                        log_event(f"Warnung: Detailseite Fehler ({attempt}/2): {exc}")

                if not detail_ok:
                    extracted_texts.append(f"LINK: {ad_url}\n\nFEHLER: Seite konnte nicht geladen werden.")

                await page.wait_for_timeout(800)

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            filepath = BASE_DIR / f"willhaben_full_export_{timestamp}.txt"

            chunks = []
            for i, text in enumerate(extracted_texts, 1):
                chunks.append("=" * 40)
                chunks.append(f"ANZEIGE {i}")
                chunks.append("=" * 40)
                chunks.append("")
                chunks.append(text)
                chunks.append("\n")

            filepath.write_text("\n".join(chunks), encoding="utf-8")
            log_event(f"Datei gespeichert: {filepath}")

            if shutil.which("gog") and ACCOUNT:
                doc_name = f"Willhaben_Komplett_Scrape_{timestamp}"
                log_event(f"Erstelle Google Doc: {doc_name}")
                cmd = [
                    "gog",
                    "drive",
                    "upload",
                    str(filepath),
                    "--account",
                    ACCOUNT,
                    "--name",
                    doc_name,
                    "--convert-to",
                    "doc",
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                output = (result.stdout or result.stderr or "").strip()
                log_event(output if output else f"gog Rückgabecode: {result.returncode}")
            else:
                log_event("gog nicht gefunden oder ACCOUNT leer. Upload wird übersprungen.")

        except Exception as exc:
            log_event(f"FATALER FEHLER im Hauptlauf: {exc}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(scrape_willhaben())
