import asyncio
from core.browser_controller import BrowserController

async def testcrawl():
    async with BrowserController(headless = False, allow_3p = False) as bc:
        context = await bc.new_context("https://www.google.de")
        print(await context.cookies())
        page = await context.new_page()
        visti_page = await page.goto("https://www.google.de")
        await asyncio.sleep(3) 
        #print(await page.content())
        if visti_page:
            print("-------------------------")
            print (await visti_page.request.all_headers())
            print (await visti_page.all_headers())  
            print("-----------------------------")
            print(await context.cookies())
        await context.close()
        
        
        
if __name__ == "__main__":
    asyncio.run(testcrawl())