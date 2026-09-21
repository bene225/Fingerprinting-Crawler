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
    
     # TODO Wortlsite für Reject finden (CONSENT O MATIC evtl)
     
    # TODO richtige Wörter für Ablehung 
    # Rate-Wörter aus Wortliste exportieren und Json plätten (ablehnen)
    tcf_reject_chance_flat = []
    tcf_reject_chance = tcf_terms_data["negTerms"]
    for language in tcf_reject_chance:
        tcf_reject_chance_flat.extend(tcf_reject_chance[language]["rejection"])

    # block Liste für Wort-Akzeptoren
    tcf_accept_block = []
    for neg_category in tcf_terms_data["negTerms"].values():
        tcf_accept_block += neg_category["negation"] + neg_category["restriction"] + neg_category["rejection"] + neg_category["necessity"]
    tcf_accept_block_set = {word.lower() for word in tcf_accept_block}


async def try_accept(page : Page) -> bool:

    
    await page.wait_for_load_state("load")
    # CSS-Akzeptoren für normales Banner
    await asyncio.sleep((random.randint(100, 300) + 150) / 1000)  # Sicherheit dass Button da und menschlichkeit
    
    # Polling
    for times_tried in range (20):
        
        # Wenn Consent Banner in Frame    
        for frame in page.frames:
            if frame.is_detached():
                continue
            for selector in tcf_accept_css:
                found_selectors = frame.locator(selector)
                try:
                    # Verringern von click timeout Zeit
                    count_selectors = await found_selectors.count()
                    for i in range (count_selectors):
                        click_selector = found_selectors.nth(i)
                        if not await click_selector.is_visible():
                            continue
                        await click_selector.click(timeout=2000)
                        return True
                except Exception:
                    continue
                
                
        # Alle buttons holen (Sprach-Akzeptoren)
        for frame in page.frames:
                    if frame.is_detached():
                        continue
                    buttons = await frame.get_by_role("button").all()
                    for button in buttons:
                        try:
                            text_button = await button.text_content(timeout=2000)
                            if not text_button: 
                                continue
                            
                            text_button_word = text_button.lower().strip()
                            text_button_word = set(text_button_word.split())
                            if tcf_accept_block_set & text_button_word:
                                continue    
                            for tcf_text_accept in tcf_accept_chance_flat:
                                if tcf_text_accept.lower().strip() in text_button.lower().strip(): #Gerade noch kein Wert drin    == bei zu viele falses pos
                                        if not await button.is_visible():
                                            continue
                                        await button.click(timeout=2000)
                                        return True
                        except Exception:
                            continue
        await asyncio.sleep(0.5)                       
    
    return False


"""async def try_reject(page : Page) -> bool:
        await page.wait_for_load_state("load")
        # CSS-Rejektoren
        await asyncio.sleep((random.randint(1000, 3000) + 1500) / 1000)  # Sicherheit dass Button da und menschlichkeit
        for reject_css in tcf_reject_css: # TODO richtige Liste einfügen
            try:
                await page.click(reject_css, timeout=300)
                return True
            except Exception:
                continue
        
        # Alle buttons holen (Sprach-Akzeptoren)
        buttons = await page.get_by_role("button").all()
        for button in buttons:
            text_button = await button.text_content()
            if not text_button: continue
            for tcf_text_reject in tcf_reject_chance_flat:
                if tcf_text_reject.lower().strip() in text_button.lower().strip(): #Gerade noch kein Wert drin    == bei zu viele falses pos
                    try:
                        await button.click()
                        return True
                    except Exception:
                        continue
        return False

   """         




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