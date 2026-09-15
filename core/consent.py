import asyncio
from playwright.async_api import async_playwright, Page
import random
import json

# Wortliste von Maximilian Wittig übernommen
# https://playwright.dev/docs/locators#locate-by-text

# Alle TCF Strings einlesen
with open("utils/tcf_terms.json", "r", encoding="utf-8") as tcf_file:
    tcf_terms_data = json.load(tcf_file)
    tcf_accept_known = tcf_terms_data["knownSelectors"]
    tcf_accept_generic = tcf_terms_data["genericSelectors"]
    
    # Rate-Wörter aus Wortliste exportieren und Json plätten
    tcf_accept_chance_flat = []
    tcf_accept_chance = tcf_terms_data["posTerms"]
    for tcf_accept_language in tcf_accept_chance:
        tcf_accept_chance_flat.extend(tcf_accept_chance[tcf_accept_language])
    
    tcf_accept_all = tcf_accept_known + tcf_accept_generic + tcf_accept_chance_flat

async def try_accept(page : Page) -> bool:
    try:
        
        await page.get_by_text(Füllen).click()