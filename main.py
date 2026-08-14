import asyncio
from core.browser_controller import BrowserController
import core.injector 

async def testcrawl():
    async with BrowserController(headless = False, allow_3p = False) as bc:
        context = await bc.new_context("https://browserleaks.com/canvas")
        page = await context.new_page()
        page.on("console", lambda msg: print(f"Browser-Konsole [{msg.type}]: {msg.text}")) #ki
        page.on("pageerror", lambda err: print(f"JS-Absturz: {err.message}")) #ki
        # MP starten
        page_injection = core.injector.Injector()
        await page_injection.integrade_monkeypatch(page=page)
        visti_page = await page.goto("https://browserleaks.com/canvas")
        await asyncio.sleep(30) 
        #print(await page.content())
        if visti_page:
            print (await visti_page.request.all_headers())
            print (await visti_page.all_headers()) 
            print("-----") 
            for event in page_injection.events:
                print (event)
        await context.close()
        
        
        
if __name__ == "__main__":
    asyncio.run(testcrawl())