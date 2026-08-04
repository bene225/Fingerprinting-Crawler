import asyncio
from core.browser_controller import BrowserController

async def testcrawl():
    async with BrowserController(headless = False, allow_3p = True) as bc:
        context = await bc.new_context("https://www.google.de")
        page = await context.new_page()
        await page.goto("https://www.google.de")
        await asyncio.sleep(3) 
        print(await page.content())
        
        await context.close()
        
        
        
if __name__ == "__main__":
    asyncio.run(testcrawl())