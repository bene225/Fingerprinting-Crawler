import asyncio
from playwright.async_api import async_playwright

JS = """() => ({
  ua: navigator.userAgent,
  webdriver: navigator.webdriver,
  language: navigator.language,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  viewport: window.innerWidth + 'x' + window.innerHeight
})"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://example.com")
        print(await page.evaluate(JS))
        await browser.close()

asyncio.run(main())