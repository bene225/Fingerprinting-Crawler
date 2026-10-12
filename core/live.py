import core.consent
import core.logging
from config import CrawlConfig
from core.browser_controller import BrowserController
from core.injector import Injector
from core.logging import short_error
from utils.check_internet import check_internet, wait_for_internet
from utils.crawl_utils import landing_fields, progress_line


import asyncio
import itertools
import time
from dataclasses import replace


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


# FF2 Cookie-Block: Modus -> (allow_3p, js_cookie_block). Jede Website in allen Modi gemessen, je Modus eigene Ergebnisdatei
BLOCK_MODES = {"alles_erlaubt": (True, False), "nur_cdp": (False, False), "alles_geblockt": (False, True)}
# Alle 6 Reihenfolgen reihum: jeder Modus gleich oft an erster/zweiter/dritter Stelle, Reihenfolge-Effekte (Wiederbesuch, Bot-Erkennung) verteilen sich gleichmaessig
MODE_ORDERS = list(itertools.permutations(BLOCK_MODES))


# Je Modus eigene Config: Block-Einstellungen, crawl_name (Screenshot-Ordner) und Ergebnisdatei, z.B. results/ff2.jsonl -> results/ff2_nur_cdp.jsonl
def block_mode_configs(config : CrawlConfig) -> dict[str, CrawlConfig]:
    output = config.path_to_output
    return {mode: replace(config, allow_3p=allow_3p, js_cookie_block=js_cookie_block, crawl_name=f"{config.crawl_name}_{mode}",
                          path_to_output=output.with_name(f"{output.stem}_{mode}{output.suffix}"))
            for mode, (allow_3p, js_cookie_block) in BLOCK_MODES.items()}


# Eine Website in einem Modus messen: gleiche Schritte wie single_crawl in crawl (FF1), CDP-Block je Seite aus der Config
async def measure_site(bc : BrowserController, config : CrawlConfig, test_domain : str, site_id : int):
    context = None
    try:
        context = await bc.new_context(test_domain)
        page = await bc.new_page(context, allow_3p=config.allow_3p)
        injector = Injector()
        await injector.integrade_url_to_js(test_domain, page)
        await injector.integrade_monkeypatch(page)
        # JS-Block getrennt vom CDP-Block (CDP in new_page)
        if config.js_cookie_block:
            await injector.integrade_js_cookie_block(test_domain, page)
        response = await page.goto(test_domain, timeout=config.load_timeout * 1000)
        await asyncio.sleep(config.loading_time)
        stats_before_consent = await bc.collect_stats(context, test_domain, list(injector.events))
        stats_before_consent["status"] = response.status if response else None
        stats_before_consent |= landing_fields(page.url, test_domain)
        stats_before_consent["screenshot"] = await core.logging.write_screenshot(page, config)
        stats_after_consent = None
        if config.consent:
            consent_entries_before = await core.consent.consent_entries_before(page)
            consent_ok = await core.consent.try_accept(page, config.consent_tries, config.consent_polling)
            await asyncio.sleep(config.visit_time_after_consent)
            stats_after_consent = await bc.collect_stats(context, test_domain, list(injector.events))
            stats_after_consent |= landing_fields(page.url, test_domain)
            stats_after_consent["consent_ok"] = consent_ok
            stats_after_consent["consent_check"] = await core.consent.consent_check(page, consent_entries_before)
            stats_after_consent["screenshot"] = await core.logging.write_screenshot(page, config)
        core.logging.write_website(site_id, test_domain, config, injector.events, stats_before_consent, stats_after_consent, check_internet())
        print(f"{test_domain} [{config.crawl_name}]: Status {stats_before_consent['status']}, FP vor Consent={stats_before_consent['n_fp_calls']}, 3P-Cookies nach Consent={(stats_after_consent or stats_before_consent)['n_cookies_3p']}")
    finally:
        if context is not None:
            await context.close()


# FF2: jede Website in allen Block-Modi direkt nacheinander (gleicher Zeitpunkt), Reihenfolge der Modi reihum aus MODE_ORDERS
# Fortsetzen, Fehlerzeilen und Neustart wie in crawl, aber je Modus mit eigener Datei
async def crawl_block(config : CrawlConfig, sites : list[str]):
    mode_configs = block_mode_configs(config)
    # Ergebnisordner anlegen (write_config schreibt vor dem ersten Screenshot)
    config.path_to_output.parent.mkdir(parents=True, exist_ok=True)
    # Ein Browser fuer alle Modi: CDP-Block wird je Seite gesetzt, der Wert im Controller gilt dann nicht
    async with BrowserController(headless=config.headless, browser_type=config.BrowserType, allow_3p=True) as bc:
        done = {}
        next_id = {}
        for mode, mode_config in mode_configs.items():
            core.logging.write_config(mode_config)
            done[mode] = core.logging.done_crawls(mode_config)
            next_id[mode] = core.logging.resume_crawl(mode_config)
        start = time.time()
        processed = 0
        for position, test_domain in enumerate(sites, 1):
            # Reihenfolge haengt an der Position in der Liste: beim Fortsetzen gleich
            order = [mode for mode in MODE_ORDERS[(position - 1) % len(MODE_ORDERS)] if (test_domain, None) not in done[mode]]
            if not order:
                continue
            for mode in order:
                mode_config = mode_configs[mode]
                await wait_for_internet()
                try:
                    await asyncio.wait_for(measure_site(bc, mode_config, test_domain, next_id[mode]), timeout=mode_config.site_timeout)
                except Exception as e:
                    print(f"Fehler bei {test_domain} [{mode}]: {short_error(e)}")
                    core.logging.write_error(next_id[mode], test_domain, mode_config, repr(e), check_internet())
                    if not bc.is_alive():
                        raise RuntimeError("Browser abgestuerzt")
                next_id[mode] += 1
            processed += 1
            print(progress_line(position, len(sites), start, processed))