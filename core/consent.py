import asyncio
from playwright.async_api import async_playwright, Page
import random
import json

# Wortliste von Maximilian Wittig übernommen
# https://playwright.dev/docs/locators#locate-by-text

# Alle TCF Strings einlesen (CSS)
with open("utils/tcf_terms.json", "r", encoding="utf-8") as tcf_file:
    tcf_terms_data = json.load(tcf_file)
    tcf_accept_known = tcf_terms_data["knownSelectors"]
    tcf_accept_generic = tcf_terms_data["genericSelectors"]
    tcf_accept_css = tcf_accept_generic + tcf_accept_known
    
    # Rate-Wörter aus Wortliste exportieren und Json plätten (akzeptieren)(Sprache)
    tcf_accept_chance_flat = []
    tcf_accept_chance = tcf_terms_data["posTerms"]
    for tcf_accept_language in tcf_accept_chance:
        tcf_accept_chance_flat.extend(tcf_accept_chance[tcf_accept_language])
    
     # TODO Wortlsite für Reject finden
     
    # TODO richtige Wörter für Ablehung 
    # Rate-Wörter aus Wortliste exportieren und Json plätten (ablehnen)
    tcf_reject_chance_flat = []
    tcf_reject_chance = tcf_terms_data["negTerms"]
    for language in tcf_reject_chance:
        tcf_reject_chance_flat.extend(tcf_reject_chance[language]["rejection"])
    print(tcf_reject_chance_flat)






"""
async def try_accept(page : Page) -> bool:
    await page.wait_for_load_state("load")
    # CSS-Akzeptoren
    for accept_css in tcf_accept_css:
        try:
            await page.click(accept_css, timeout=300)
            return True
        except:
            continue
    
    # Sprache-Akzeptoren
    for accept_word in tcf_accept_chance_flat:
        try:
            await page.get_by_role("button", name=accept_word).click(timeout=300)
            return True
        except:
            continue
    # kein Wort passt
    return False


async def try_reject(page : Page) -> bool:
    await page.wait_for_load_state("load")
    # CSS-Rejektoren
    
    # TODO TODO TODO auf Ablehnung CSS umbauen
    
    for accept_css in tcf_accept_css:
        try:
            await page.click(accept_css, timeout=300)
            return True
        except:
            continue
    
    # Sprache-Rejektoren
    for accept_word in tcf_accept_chance_flat:
        try:
            await page.get_by_role("button", name=accept_word).click(timeout=300)
            return True
        except:
            continue
        # kein Wort passt
    return False
    """