import argparse
import asyncio
import csv
import time
from typing import Any

from core.browser_controller import BrowserController
from core.historical_browser_controller import HistoricalBrowserController
from config import CrawlConfig
from core.injector import Injector
import core.consent
import core.logging
from pathlib import Path
from core.logging import short_error
from utils.check_internet import check_internet
from utils.check_internet import wait_for_internet
from utils.crawl_utils import progress_line
from utils.origin_domain import origin_domain
from utils.tranco_worker import read_sites_tranco
from utils.wayback import find_captures, build_wayback_url, archive_reachable, original_url


# Fehlertexte, bei denen Wayback bremst oder Verbindungen ablehnt
BLOCK_SIGNS = ("Wayback drosselt", "HTTP 429", "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED", "ERR_CONNECTION_TIMED_OUT", "ERR_EMPTY_RESPONSE")


# Wohin hat die Seite wirklich geladen? Bei Weiterleitung auf eine andere Domain (z.B. uebernommene Firma) gelten deren eigene Skripte als 3P -> zum Filtern
def landing_fields(page_url : str, requested_url : str) -> dict:
    final_url = original_url(page_url) or page_url # Wayback-Praefix entfernen
    return {"final_url": final_url, "cross_domain_redirect": origin_domain(final_url) != origin_domain(requested_url)}


# Wayback hat Teile abgelehnt (429, Verbindung abgelehnt): Skripte fehlen still, die Messung waere zu niedrig -> Fehler, wird wiederholt
# Wenn ein Skript mit 429 -> Fehler
def check_complete(stats : dict) -> None:
    if stats["n_archive_429"] or stats["n_archive_conn_errors"]:
        raise RuntimeError(f"Wayback drosselt ({stats['n_archive_429']} x HTTP 429, {stats['n_archive_conn_errors']} x Verbindung abgelehnt/abgebrochen)")


# Kein Internet (z.B. WLAN weg): warten, sonst landen alle folgenden Seiten als Fehler im Ergebnis
# Bei Absturz (Browser tot, unerwarteter Fehler) neu starten. Fertige Seiten werden uebersprungen, der Crawl macht dort weiter.
# passes: nach einem Durchlauf nochmal ueber die Liste, damit Fehlerzeilen (z.B. aus einer Drosselung) noch in derselben Nacht wiederholt werden
def run_with_restart(crawl_function, config : CrawlConfig, sites : list[str], attempts : int = 20, wait : int = 60, passes : int = 3):
    finished = 0
    failures = 0
    while finished < passes and failures < attempts:
        try:
            asyncio.run(crawl_function(config, sites))
            finished += 1
        except Exception as e:
            failures += 1
            print(f"Crawl abgestuerzt (Versuch {failures} von {attempts}): {short_error(e)}. Neustart in {wait} s")
            time.sleep(wait)


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


#Pipeline zu aufruf
async def visit_snapshot(hbc, config, site, capture, row_id):
    context = None
    try:
        wayback_url = build_wayback_url(capture)
        context = await hbc.new_context(wayback_url)
        page = await context.new_page()
        # FP-Monkeypatch wie im Live-Crawl. 1P = Original-Website (nicht web.archive.org), Wayback-Modus schneidet den Praefix aus den Stacks
        injector = Injector()
        await injector.integrade_url_to_js(capture["original"], page)
        await injector.integrade_wayback_mode(page)
        await injector.integrade_monkeypatch(page)
        response = await page.goto(wayback_url, wait_until="domcontentloaded", timeout=config.wayback_load_timeout * 1000) # Wayback  langsam
        # Bei 429 Fehler
        if response is None or response.status >= 400:
            raise RuntimeError(f"HTTP {response.status if response else 'keine Antwort'}")
        # Statt fester Zeit: warten, bis das Archiv fertig geliefert hat und keine FP-Aufrufe mehr kommen (mindestens loading_time wie live, hoechstens wayback_max_wait)
        waited = await hbc.wait_until_quiet(context, injector.events, minimum=config.loading_time, maximum=config.wayback_max_wait)
        stats_before_consent = await hbc.collect_historical_stats(context, wayback_url, list(injector.events))
        stats_before_consent |= {"stichtag": capture["stichtag"], "timestamp": capture["timestamp"], "status": response.status} | waited | landing_fields(page.url, capture["original"])
        # Unvollstaendig geladen (Wayback hat Teile abgelehnt): als Fehler, wird wiederholt
        check_complete(stats_before_consent)
        # Screenshot zum Prüfen von Hand
        stats_before_consent["screenshot"] = await core.logging.write_screenshot(page, config)
        # Ohne Consent nur ein Messpunkt
        stats_after_consent = None
        if config.consent:
            # Wie im Live-Crawl: Banner bedienen, Bestaetigung pruefen, nach der Verweildauer nochmal messen
            consent_entries_before = await core.consent.consent_entries_before(page)
            consent_ok = await core.consent.try_accept(page, config.consent_tries, config.consent_polling)
            # Nur nach einem Klick kann sich etwas aendern: dann warten, sonst gleich messen
            if consent_ok:
                await hbc.wait_until_quiet(context, injector.events, minimum=config.visit_time_after_consent, maximum=config.wayback_max_wait)
            stats_after_consent = await hbc.collect_historical_stats(context, wayback_url, list(injector.events))
            check_complete(stats_after_consent)
            stats_after_consent |= landing_fields(page.url, capture["original"])
            stats_after_consent["consent_ok"] = consent_ok
            stats_after_consent["consent_check"] = await core.consent.consent_check(page, consent_entries_before)
            stats_after_consent["screenshot"] = await core.logging.write_screenshot(page, config)
        core.logging.write_website(row_id, site, config, injector.events, stats_before_consent, stats_after_consent, check_internet())
        print(f"{site} {capture['stichtag']}: Status {stats_before_consent['status']}, FP vor Consent={stats_before_consent['n_fp_calls']}")
    finally:
        if context is not None:
            await context.close()


async def crawl_historical(config : CrawlConfig, sites : list[str]):
    # Stichtage fest aus der Config (letzter = Brueckenpunkt), damit Resume an anderem Tag gleich bleibt
    target_dates = list(config.target_dates)
    core.logging.write_config(config)
    # Resume: nur erfolgreiche (Website, Stichtag) mit Internet überspringen, ids weiterzaehlen
    done = core.logging.done_crawls(config)
    row_id = core.logging.resume_crawl(config)
    start = time.time()
    processed = 0 # in diesem Lauf bearbeitete Websites (Restzeit-Schaetzung)

    # Snapshots einer Website gleichzeitig, hoechstens parallel_snapshots (Archiv schonen)
    slots = asyncio.Semaphore(config.parallel_snapshots)
    open_slots = config.parallel_snapshots
    retired = [] # Aufgaben, die je einen Platz dauerhaft belegen (Referenz halten)

    # Wayback bremst (429) oder lehnt Verbindungen ab: nichts mehr anfragen, sonst droht eine laengere IP-Sperre.
    # Pause, dann kleine Testabfrage; klappt sie nicht, wird die Pause verdoppelt (bis 30 min).
    # Bei jeder Sperre ein Snapshot weniger gleichzeitig (mindestens 1), nach einer Stunde ohne Sperre wieder einer mehr
    blocked = False
    recovery = asyncio.Lock() # nur einer testet, die anderen warten dahinter
    base_pause = 120 # Sekunden, wird laenger, wenn Sperren kurz hintereinander kommen
    last_block = 0.0
    last_recovery = 0.0

    def slow_down(reason : str):
        nonlocal blocked, base_pause, open_slots, last_block
        if not blocked:
            base_pause = min(base_pause * 2, 1800) if time.time() - last_recovery < 900 else 120
            last_block = time.time()
            if open_slots > 1:
                open_slots -= 1
                retired.append(asyncio.get_running_loop().create_task(slots.acquire()))
            print(f"Wayback bremst oder ist nicht erreichbar ({reason}). Ab jetzt {open_slots} Snapshot(s) gleichzeitig, {hbc.slower():.1f} Anfragen/s")
        blocked = True

    async def wait_if_paused():
        nonlocal blocked, last_recovery
        if not blocked:
            return
        async with recovery:
            pause = base_pause
            while blocked:
                print(f"Pause {pause // 60} min, danach Testabfrage an Wayback")
                await asyncio.sleep(pause)
                if await asyncio.to_thread(archive_reachable):
                    blocked = False
                    last_recovery = time.time()
                    print("Wayback antwortet wieder, es geht weiter")
                else:
                    pause = min(pause * 2, 1800)

    async with HistoricalBrowserController(headless=config.headless, browser_type=config.BrowserType, allow_3p=config.allow_3p, archive_rate=config.archive_rate, archive_light=config.archive_light) as hbc:

        async def visit_one(site, capture, capture_row_id):
            async with slots:
                await wait_if_paused()
                try:
                    await asyncio.wait_for(visit_snapshot(hbc, config, site, capture, capture_row_id), timeout=config.site_timeout)
                except Exception as e:
                    print(f"Fehler bei {site} {capture['stichtag']}: {short_error(e)}")
                    core.logging.write_error(capture_row_id, site, config, repr(e), check_internet(), capture["stichtag"])
                    # 429, Verbindung abgelehnt oder abgebrochen = Wayback bremst
                    if any(sign in repr(e) for sign in BLOCK_SIGNS):
                        slow_down(short_error(e))
                    # Browser abgestuerzt: neu starten (run_with_restart) statt alle Snapshots als Fehler zu schreiben
                    if not hbc.is_alive():
                        raise RuntimeError("Browser abgestuerzt")
                await asyncio.sleep(config.wayback_pause) # Wayback schonen

        for position, site in enumerate(sites, 1):
            # Frueher verworfen (laedt live nicht) -> nicht nochmal pruefen
            if (site, None) in done:
                continue
            # Nur fehlende/fehlgeschlagene Stichtage, alle erledigt -> ohne Abfrage
            missing_dates = [target_date for target_date in target_dates if (site, target_date) not in done]
            if not missing_dates:
                continue
            # Eine Stunde ohne Sperre: wieder einen Platz und mehr Anfragen pro Sekunde (bis zum Startwert)
            if (open_slots < config.parallel_snapshots or hbc.rate < config.archive_rate) and time.time() - last_block > 3600:
                if open_slots < config.parallel_snapshots:
                    slots.release()
                    open_slots += 1
                hbc.faster()
                last_block = time.time()
                print(f"Eine Stunde ohne Sperre: wieder {open_slots} Snapshots gleichzeitig, {hbc.rate:.1f} Anfragen/s")
            await wait_if_paused()
            await wait_for_internet()
            processed += 1
            # Vorab: laedt die Website live? Sonst kein Archiv-Crawl (Infrastruktur-Domain, tot, Bot-Sperre)
            if not await hbc.site_loads(site, config.load_check_timeout):
                core.logging.write_skipped(row_id, site, config, "laedt live nicht", check_internet())
                row_id += 1
                print(f"{progress_line(position, len(sites), start, processed)} | {site}: laedt live nicht, uebersprungen")
                continue
            captures = find_captures(site, missing_dates, config.max_days_gap)
            # Wayback nicht erreichbar -> Fehlermeldung, um Website nochmal zu crawlen
            if captures is None:
                core.logging.write_error(row_id, site, config, "Wayback nicht erreichbar", check_internet())
                row_id += 1
                print(f"{progress_line(position, len(sites), start, processed)} | {site}: Wayback nicht erreichbar")
                slow_down("Abfrage der Kopien fehlgeschlagen")
                continue
            # Stichtage ohne Snapshot als erledigt mitschreiben, sonst fragt Resume jedes Mal neu
            found = {capture["stichtag"] for capture in captures}
            for target_date in missing_dates:
                if target_date not in found:
                    core.logging.write_no_snapshot(row_id, site, config, target_date, check_internet())
                    row_id += 1
            # Alle Snapshots dieser Website parallel (begrenzt durch slots), jeder mit eigener Zeilen-Nummer
            await asyncio.gather(*(visit_one(site, capture, row_id + i) for i, capture in enumerate(captures)))
            row_id += len(captures)
            print(f"{progress_line(position, len(sites), start, processed)} | {site}: {len(captures)} von {len(missing_dates)} Snapshots")


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
