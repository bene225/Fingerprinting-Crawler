import argparse
import asyncio
import csv
import time
from typing import Any

from core.browser_controller import BrowserController
from core.historical import crawl_historical
from config import CrawlConfig
from core.injector import Injector
import core.consent
import core.logging
from pathlib import Path
from core.logging import short_error
from utils.check_internet import check_internet
from utils.check_internet import wait_for_internet
from utils.crawl_utils import progress_line
from utils.crawl_utils import landing_fields
from utils.crawl_utils import run_with_restart
from utils.tranco_worker import read_sites_tranco


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
                stats_before_consent |= landing_fields(page.url, test_domain)
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
                    stats_after_consent |= landing_fields(page.url, test_domain)
                    stats_after_consent["consent_ok"] = consent_ok
                    # Tcf Status nciht ganz genau
                    stats_after_consent["consent_check"] = await core.consent.consent_check(page, consent_entries_before)
                    stats_after_consent["screenshot"] = await core.logging.write_screenshot(page, config)
                core.logging.write_website(site_id, test_domain, config, injector.events, stats_before_consent, stats_after_consent, check_internet())
                print(f"{test_domain}: Status {stats_before_consent['status']}, FP vor Consent={stats_before_consent['n_fp_calls']}")

            finally:
                if context is not None:
                        await context.close()
        
                
        # config schreiben, mitzähle nfür abbruch
        core.logging.write_config(config)
        # Resume: nur erfolgreiche Websites mit Internet ueberspringen, ids weiterzaehlen
        done = core.logging.done_crawls(config)
        site_id = core.logging.resume_crawl(config)
        start = time.time()
        processed = 0 # in diesem Lauf bearbeitete Websites (Restzeit-Schaetzung)
        for position, test_domain in enumerate(sites, 1):
            if (test_domain, None) in done:
                continue
            await wait_for_internet()
            try:
                await asyncio.wait_for(single_crawl(test_domain, site_id), timeout=config.site_timeout)
            # Fehler + Timeout in die Ergebnisse, um gezielt nochmal zu crawlen
            except Exception as e:
                print(f"Fehler bei {test_domain}: {short_error(e)}")
                core.logging.write_error(site_id, test_domain, config, repr(e), check_internet())
                # Browser abgestuerzt: neu starten (run_with_restart) statt alle folgenden Seiten als Fehler zu schreiben
                if not bc.is_alive():
                    raise RuntimeError("Browser abgestuerzt")
            site_id += 1
            processed += 1
            print(progress_line(position, len(sites), start, processed))



if __name__ == "__main__":
    # Genau ein Lauf pro Terminal: "uv run python main.py --live" bzw. "--hist" (zwei Terminals = beide gleichzeitig)
    parser = argparse.ArgumentParser(description="Crawl starten")
    run = parser.add_mutually_exclusive_group(required=True)
    run.add_argument("--live", action="store_true", help="FF1 Live-Crawl (vor und nach Consent)")
    run.add_argument("--hist", action="store_true", help="FF1 Archiv-Crawl (Wayback)")
    args = parser.parse_args()

    # Tranco-Liste: gleich viele Websites aus jedem logarithmischen Rangbereich (rank_bands in der Config). Gleiche Werte fuer Live und Archiv
    # batch_size spaeter erhoehen: es kommen nur die weiteren Websites dazu, fertige werden beim Fortsetzen uebersprungen
    webpages = Path("utils/tranco_647LX.csv")
    batch : dict[str, Any] = dict(batch_size= 500, batch_seed= 1)

    # FF1 Live-Punkt: vor und nach Consent gemessen, nichts blocken
    live_config = CrawlConfig(
        path_to_output=Path("results/ff1_live.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff1",
        allow_3p= True,
        consent= True,
        consent_tries= 4, # 2 s: das Banner ist nach der Ladezeit (10 s) schon da
        headless= False,
        loading_time= 10,
        visit_time_after_consent= 10,
        site_timeout= 90,
        js_cookie_block= False,
        **batch
    )
    # FF1 Snapshots: gleiche Messung (Monkeypatch, Consent), Stichtage alle 2 Jahre + Brueckenpunkt
    hist_config = CrawlConfig(
        path_to_output=Path("results/ff1_hist.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff1",
        allow_3p= True,
        consent= True,
        consent_tries= 4,
        headless= False,
        loading_time= 10,
        visit_time_after_consent= 10,
        site_timeout= 240, # Wayback laedt langsamer als live: HTML bis 90 s + Warten auf Skripte bis wayback_max_wait (zweimal) + Screenshots
        wayback_load_timeout= 90,
        wayback_max_wait= 45, # Hoechstens so lange nach dem Laden auf spaet startende Skripte warten (endet frueher, wenn nichts mehr kommt)
        wayback_pause= 2, # Pause nach jedem Snapshot. Die Rate begrenzt archive_rate, mehr Pause bringt kaum Schonung
        archive_rate= 2.5, # Anfragen pro Sekunde an Wayback (alle gleichzeitigen Seiten zusammen). Sinkt nach jeder Drosselung um 30 %
        archive_light= True, # Bilder, Schriften, Videos im Archiv nicht laden (Anfrage zaehlt trotzdem mit). False = alles laden
        parallel_snapshots= 3,
        max_days_gap= 120,
        # 1. Januar alle 2 Jahre. Letzter = Brueckenpunkt: Tag des Live-Crawls eintragen
        target_dates= ("20160101", "20180101", "20200101", "20220101", "20240101", "20261009"),
        **batch
    )

    sites = read_sites_tranco(live_config)
    if args.live:
        run_with_restart(crawl, live_config, sites)
    else:
        run_with_restart(crawl_historical, hist_config, sites)
