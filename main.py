import asyncio
import csv
from datetime import datetime

from core.browser_controller import BrowserController
from core.historical_browser_controller import HistoricalBrowserController
from config import CrawlConfig
from core.injector import Injector
import core.consent
import core.logging
from pathlib import Path
from utils.check_internet import check_internet
from utils.wayback import get_wayback_request, get_wayback_location, choose_capture, build_wayback_url

TEST_DOMAINS = [
    # Banner im Hauptdokument (CSS-Treffer)
    "https://otto.de", "https://mediamarkt.de", "https://obi.de",
    # Sourcepoint-Banner im Iframe
    "https://spiegel.de", "https://zeit.de", "https://bild.de", "https://heise.de", "https://theguardian.com", "https://bbc.com",
    # weitere deutsche Nachrichten- und Shopseiten
    "https://t-online.de", "https://web.de", "https://tagesschau.de", "https://kicker.de", "https://chip.de", "https://focus.de",
    "https://welt.de", "https://computerbase.de", "https://idealo.de", "https://check24.de", "https://kleinanzeigen.de", "https://thalia.de",
    # Kontrollseiten ohne Banner und ohne Tracker (Erwartung: Consent False, kaum Events)
    "https://example.com", "https://wikipedia.org", "https://duckduckgo.com",
    # bekannter Sonderfall: Bot-Fehlerseite (testet die Fehlerbehandlung)
    "https://ebay.de",
    # Weiterleitung auf eine andere Domain (testet die Berechnung von main_site)
    "https://youtu.be",
] 


def read_sites(path : Path, max_rank : int) -> list[str]:
    # Rank Stufen 1000, 5000 (Nicht in Config, da 1000 Sinnvoll) CRUX Liste in Stufen
    with open(path, encoding="utf-8") as in_file:
        return [row["origin"] for row in csv.DictReader(in_file) if int(row["rank"]) <= max_rank]


async def crawl (config : CrawlConfig, sites : list[str]):
    async with BrowserController(headless=config.headless, browser_type=config.BrowserType, allow_3p=config.allow_3p) as bc:
    
        # Hilfsfunktion für as.wait_for
        async def single_crawl(test_domain, site_id):
            context = None
            try:
                context = await bc.new_context(test_domain)
                page = await bc.new_page(context)
                injector = Injector()
                await injector.integrade_url_to_js(test_domain, page)
                await injector.integrade_monkeypatch(page)
                # JS-Block getrennt vom CDP-Block (CDP in bc)
                if config.js_cookie_block:
                    await injector.integrade_js_cookie_block(test_domain, page)
                response = await page.goto(test_domain, timeout=config.load_timeout * 1000)
                # Zeit lassen für laden
                await asyncio.sleep(config.loading_time)
                # snap stats
                stats_before_consent = await bc.collect_stats(context, test_domain, list(injector.events))
                # Statuscode Bot Fehler 
                stats_before_consent["status"] = response.status if response else None
                # Screenshot vor Consent zum Pruefen von Hand, Dateiname in den Namen
                stats_before_consent["screenshot"] = await core.logging.write_screenshot(page, config)
                # Ohne Consent nur ein Messpunkt
                stats_after_consent = None
                if config.consent:
                    # Für vgl mit danach cookies bei TCF
                    consent_entries_before = await core.consent.consent_entries_before(page)
                    consent_ok = await core.consent.try_accept(page, config.consent_tries, config.consent_polling)
                    # Verweildauer nach Consent
                    await asyncio.sleep(config.visit_time_after_consent)
                    stats_after_consent = await bc.collect_stats(context, test_domain, list(injector.events))
                    # Screenshot banner 
                    stats_after_consent["consent_ok"] = consent_ok
                    # Tcf Status nciht ganz genau
                    stats_after_consent["consent_check"] = await core.consent.consent_check(page, consent_entries_before)
                    stats_after_consent["screenshot"] = await core.logging.write_screenshot(page, config)
                core.logging.write_website(site_id, test_domain, config, injector.events, stats_before_consent, stats_after_consent, check_internet())
                print(f"{test_domain}: FP vor Consent={stats_before_consent['n_fp_calls']}")

            finally:
                if context is not None:
                        await context.close()
        
                
        # config schreiben, mitzähle nfür abbruch
        core.logging.write_config(config)
        # Resume: nur erfolgreiche Websites mit Internet ueberspringen, ids weiterzaehlen
        done = core.logging.done_crawls(config)
        site_id = core.logging.resume_crawl(config)
        for test_domain in sites:
            if (test_domain, None) in done:
                continue
            try:
                await asyncio.wait_for(single_crawl(test_domain, site_id), timeout=config.site_timeout)
            # Fehler + Timeout in die Ergebnisse, um gezielt nochmal zu crawlen
            except Exception as e:
                print(f"Fehler bei {test_domain}: {e!r}")
                core.logging.write_error(site_id, test_domain, config, repr(e), check_internet())
            site_id += 1


#Pipeline zu aufruf
async def visit_snapshot(hbc, config, site, capture, row_id):
    context = None
    try:
        wayback_url = build_wayback_url(capture)
        context = await hbc.new_context(wayback_url)
        page = await context.new_page()
        response = await page.goto(wayback_url, timeout=config.wayback_load_timeout * 1000) # Wayback  langsam
        # Bei 429 Fehler
        if response is None or response.status >= 400:
            raise RuntimeError(f"HTTP {response.status if response else 'keine Antwort'}")
        await asyncio.sleep(config.loading_time)
        stats = await hbc.collect_historical_stats(context, wayback_url)
        stats |= {"stichtag": capture["stichtag"], "timestamp": capture["timestamp"]}
        # Screenshot zum Prüfen von Hand 
        stats["screenshot"] = await core.logging.write_screenshot(page, config)
        # Kein Consent im Archiv -> nur stats_vor_consent
        core.logging.write_website(row_id, site, config, [], stats, None, check_internet())
    finally:
        if context is not None:
            await context.close()


async def crawl_historical(config : CrawlConfig, sites : list[str]):
    # Stichtage fest aus der Config (letzter = Brueckenpunkt), damit Resume an anderem Tag gleich bleibt
    target_dates = list(config.target_dates)
    today = datetime.now().strftime("%Y%m%d")
    core.logging.write_config(config)
    # Resume: nur erfolgreiche (Website, Stichtag) mit Internet überspringen, ids weiterzaehlen
    done = core.logging.done_crawls(config)
    row_id = core.logging.resume_crawl(config)
    async with HistoricalBrowserController(headless=config.headless, browser_type=config.BrowserType, allow_3p=config.allow_3p) as hbc:
        for site in sites:
            # Alle Stichtage erledigt -> ohne CDX
            if all((site, target_date) in done for target_date in target_dates):
                continue
            # CDX ab einem Jahr vor dem ersten Stichtag (JJJJMMTT - 10000)
            snapshots = get_wayback_location(get_wayback_request(site, int(target_dates[0]) - 10000, int(today)))
            # CDX nicht erreichbar -> Fehlermeldung, um Website nochmal zu crawlen
            if snapshots is None:
                core.logging.write_error(row_id, site, config, "CDX nicht erreichbar", check_internet())
                row_id += 1
                continue
            captures = choose_capture(snapshots, target_dates, config.max_days_gap)
            # Stichtage ohne Snapshot als erledigt mitschreiben, sonst fragt Resume CDX jedes Mal neu
            found = {capture["stichtag"] for capture in captures}
            for target_date in target_dates:
                if target_date not in found and (site, target_date) not in done:
                    core.logging.write_no_snapshot(row_id, site, config, target_date, check_internet())
                    row_id += 1
            for capture in captures:
                # Diesen Stichtag schon erfolgreich -> nur fehlende/fehlgeschlagene nachholen
                if (site, capture["stichtag"]) in done:
                    continue
                try:
                    await asyncio.wait_for(visit_snapshot(hbc, config, site, capture, row_id), timeout=config.site_timeout)
                except Exception as e:
                    core.logging.write_error(row_id, site, config, repr(e), check_internet(), capture["stichtag"])
                row_id += 1
                await asyncio.sleep(config.wayback_pause) # Wayback schonen


if __name__ == "__main__":
    webpages = Path("crux_negation_selectors/crux_de_202608.csv")
    sites = read_sites(webpages, max_rank=1000)

    # FF1 Live-Punkt: vor und nach Consent gemessen, nichts blocken
    live_config = CrawlConfig(
        path_to_output=Path("results/ff1_live.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff1",
        allow_3p= True,
        consent= True,
        headless= False,
        loading_time= 10,
        visit_time_after_consent= 10,
        site_timeout= 90,
        js_cookie_block= False,
    )
    # FF1 Snapshots: gleiche Messung, Stichtage + heute
    hist_config = CrawlConfig(
        path_to_output=Path("results/ff1_hist.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff1",
        allow_3p= True,
        consent= False,
        headless= False,
        loading_time= 10,
        site_timeout= 120,
        wayback_pause= 6,
        # Letzter = Brueckenpunkt: Tag des Live-Crawls eintragen
        target_dates= ("20160101", "20200101", "20240101", "20261008")
    )

    asyncio.run(crawl(live_config, sites))
    asyncio.run(crawl_historical(hist_config, sites))