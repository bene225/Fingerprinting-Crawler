import asyncio

from core.browser_controller import BrowserController
from config import CrawlConfig
from core.injector import Injector
import core.consent
import core.logging
from pathlib import Path

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
] #KI

async def crawl (config : CrawlConfig):
    async with BrowserController(headless=config.headless, browser_type=config.BrowserType, allow_3p=config.allow_3p) as bc:
    
        # Hilfsfunktion für as.wait_for
        async def single_crawl(test_domain, site_id):
            context = None
            try:
                context = await bc.new_context(test_domain)
                page = await context.new_page()
                injector = Injector()
                await injector.integrade_url_to_js(test_domain, page)
                await injector.integrade_monkeypatch(page)
                if config.allow_3p == False:
                    await injector.integrade_js_cookie_block(test_domain, page)
                await page.goto(test_domain)
                # Zeit lassen für laden
                await asyncio.sleep(config.loading_time)
                # snap stats
                stats_before_consent = await bc.collect_stats(context, test_domain, list(injector.events))
                if config.consent:
                    await core.consent.try_accept(page)
                if config.allow_3p == False:
                    await bc.clear_3p(context)
                await asyncio.sleep(config.loading_time)
                stats_after_consent = await bc.collect_stats(context, test_domain, list(injector.events))
                core.logging.write_website(site_id, test_domain, config, injector.events, stats_before_consent, stats_after_consent)
                print(f"{test_domain}: FP vor={stats_before_consent['n_fp_calls']} nach={stats_after_consent['n_fp_calls']}")
    
            except Exception as e:
                print("Fehler bei Durchlauf")
                print(e)
    
            finally:
                if context is not None:
                        await context.close()
        
                
        # config schreiben, mitzähle nfür abbruch
        core.logging.write_config(config)
        start_id = core.logging.resume_crawl(config)
        for site_id, test_domain in enumerate(TEST_DOMAINS[start_id:], start=start_id):
            try:
                await asyncio.wait_for(single_crawl(test_domain, site_id), timeout=config.site_timeout)
            except TimeoutError:
                print(f"Timeout bei: {test_domain}")
    
    
    
            
            



        
        
if __name__ == "__main__":
    
    # Einstellungen für den Crawler
    config = CrawlConfig(
        path_to_output=Path("results/output.jsonl"), # Noch machen 
        path_to_webpages=Path("input"), #Noch machen
        #crawl_name=, # Noch machen, alle 3 Punkte hier mit DB
        BrowserType= "chromium",
        allow_3p= True,
        consent= True,
        headless= False,
        concurrent_sessions= 2, # Noch machen
        loading_time= 10,
        site_timeout= 90
    )
    
    asyncio.run(crawl(config))