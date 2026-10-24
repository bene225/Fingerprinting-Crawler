import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        for headless in (True, False):
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()
            print(headless, await page.evaluate("navigator.userAgent"))
            await browser.close()

asyncio.run(main())