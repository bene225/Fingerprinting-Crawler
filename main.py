import asyncio

from core.browser_controller import BrowserController
from config import CrawlConfig
from core.injector import Injector
import core.injector
import core.consent

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

async def crawl ():
    async with BrowserController(headless=CrawlConfig.headless, browser_type=CrawlConfig.BrowserType, allow_3p=CrawlConfig.allow_3p) as bc:
    
        # Hilfsfunktion für as.wait_for
        async def single_crawl(test_domain):
                context = None
                try:
                    context = await bc.new_context(test_domain)
                    page = await context.new_page()
                    injector = Injector()
                    await injector.integrade_url_to_js(test_domain, page)
                    await injector.integrade_monkeypatch(page)
                    if bc._allow_3p == False:
                        await injector.integrade_js_cookie_block(test_domain, page)
                    await page.goto(test_domain)
                    n_tracker_vor_consent = len(injector.events)                        
                    # TODO Variable consent steuerbar
                    await core.consent.try_accept(page)
                    n_tracker_nach_consent = len(injector.events)  
                    if bc._allow_3p == False:
                        await bc.clear_3p(context)
                    await asyncio.sleep(10)
                    print(injector.events)
        
                except Exception as e:
                    print("Fehler bei Durchlauf")
                    print(e)
        
                finally:
                    if context is not None:
                            await context.close()
        
        
        
        
        for test_domain in TEST_DOMAINS:
            try:
                await asyncio.wait_for(single_crawl(test_domain), timeout=20)
            except TimeoutError:
                print(f"Timeout bei: {test_domain}")
    
    
    
            
            


async def testcrawl():
    async with BrowserController(headless = False, allow_3p = False) as bc:
        context = await bc.new_context("https://www.google.de")
        page = await context.new_page()
        visti_page = await page.goto("https://www.google.de")
        await bc.clear_3p(context)
        await asyncio.sleep(3) 
        #print(await page.content())
        if visti_page:
            print (await visti_page.request.all_headers())
            print (await visti_page.all_headers())  
        await context.close()
        
        
        
if __name__ == "__main__":
    asyncio.run(crawl())