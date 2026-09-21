import asyncio
from core.browser_controller import BrowserController
from config import CrawlConfig

TEST_DOMAINS = [
    # Banner im Hauptdokument (CSS-Treffer)
    "otto.de", "mediamarkt.de", "obi.de",
    # Sourcepoint-Banner im Iframe
    "spiegel.de", "zeit.de", "bild.de", "heise.de", "theguardian.com", "bbc.com",
    # weitere deutsche Nachrichten- und Shopseiten
    "t-online.de", "web.de", "tagesschau.de", "kicker.de", "chip.de", "focus.de",
    "welt.de", "computerbase.de", "idealo.de", "check24.de", "kleinanzeigen.de", "thalia.de",
    # Kontrollseiten ohne Banner und ohne Tracker (Erwartung: Consent False, kaum Events)
    "example.com", "wikipedia.org", "duckduckgo.com",
    # bekannter Sonderfall: Bot-Fehlerseite (testet die Fehlerbehandlung)
    "ebay.de",
    # Weiterleitung auf eine andere Domain (testet die Berechnung von main_site)
    "youtu.be",
] #KI

async def crawl ():
    async with BrowserController(headless=CrawlConfig.headless, browser_type=CrawlConfig.BrowserType, allow_3p=CrawlConfig.allow_3p):
        


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
    asyncio.run(testcrawl())