import asyncio
from playwright.async_api import async_playwright, Page
import random

# Wortliste von Maximilian Wittig übernommen
# https://playwright.dev/docs/locators#locate-by-text


async def try_accept(page : Page) -> bool:
    try:
        await page.get_by_text(Füllen).click()