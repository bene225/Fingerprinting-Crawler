import asyncio
from playwright.async_api import async_playwright, Page
import random
import json
import re


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
    
    
    # TCF Strings für Ablehnen
    tcf_reject_known = tcf_terms_data["knownRejectSelectors"]
    tcf_reject_generic = tcf_terms_data["genericRejectSelectors"]
    tcf_reject_css = tcf_reject_generic + tcf_reject_known
    
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


async def try_accept(page : Page, tries : int = 20, polling : float = 0.5) -> bool:

    await page.wait_for_load_state("load")
    # CSS-Akzeptoren für normales Banner
    await asyncio.sleep((random.randint(100, 300) + 150) / 1000)  # Sicherheit dass Button da und menschlichkeit

    # Polling
    for times_tried in range (tries):
        
        # Wenn Consent Banner in Frame    
        for frame in page.frames:
            # kann verschwinden
            if frame.is_detached():
                continue
            for selector in tcf_accept_css:
                found_selectors = frame.locator(selector)
                try:
                    # Verringern von click timeout Zeit (Suchen über CSS dann schneller)
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
        await asyncio.sleep(polling)

    return False


async def try_reject(page : Page, tries : int = 20, polling : float = 0.5) -> bool:
    await page.wait_for_load_state("load")
    # CSS-Rejektoren
    await asyncio.sleep((random.randint(1000, 3000) + 1500) / 1000)

     # Polling
    for times_tried in range (tries):
        
        # Wenn Consent Banner in Frame    
        for frame in page.frames:
            if frame.is_detached():
                continue
            for selector in tcf_reject_css:
                found_selectors = frame.locator(selector)
                try:
                    count_selectors = await found_selectors.count()
                    for i in range(count_selectors):
                        click_selector = found_selectors.nth(i)
                        if not await click_selector.is_visible():
                            continue
                        await click_selector.click(timeout=2000)
                        return True
                except Exception:
                    continue
                    
        # Text Regeln
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
                            for tcf_text_reject in tcf_reject_chance_flat:
                                if tcf_text_reject.lower().strip() in text_button.lower().strip(): #Gerade noch kein Wert drin    == bei zu viele falses pos
                                        if not await button.is_visible():
                                            continue
                                        await button.click(timeout=2000)
                                        return True
                        except Exception:
                            continue
        await asyncio.sleep(polling)

    return False

# TODO Testen auf Context
# TODO Tetsen au Erfolg


# Bestätigung nicht perfekt 
# Namen, unter denen Consent-Tools speichern (TCF euconsent-v2, OneTrust, Cookiebot, Usercentrics, Sourcepoint, Didomi, Borlabs, Klaro)
CONSENT_KEYS = re.compile(r"consent|optanon|cookiebot|usercentrics|uc_settings|didomi|borlabs|klaro|cmp", re.IGNORECASE)

# Nur bei TCF-Tools vorhanden, sonst None. Nach Interaktion: "useractioncomplete"
TCF_STATUS_JS = """() => new Promise(resolve => {
    if (typeof window.__tcfapi !== "function") return resolve(null);
    const timer = setTimeout(() => resolve(null), 2000);
    window.__tcfapi("addEventListener", 2, (data, success) => {
        clearTimeout(timer);
        if (success && data && data.listenerId !== undefined) window.__tcfapi("removeEventListener", 2, () => {}, data.listenerId);
        resolve(success && data ? data.eventStatus : null);
    });
})"""
# Wenn tCF Tool da, dann Antwort auslesen

# Bild aller Consent-Einträge vor klick
async def consent_entries_before(page : Page) -> dict:
    try:
        cookies = {cookie.get("name", ""): cookie.get("value", "") for cookie in await page.context.cookies()}
        storage = await page.evaluate("() => { try { return {...localStorage}; } catch (e) { return {}; } }")
    except Exception:
        # Prüfung ist nur Hilfe
        return {}
    return {name: value for name, value in {**cookies, **storage}.items() if CONSENT_KEYS.search(name)}


# Nach dem Klick: Andere Einträge
async def consent_check(page : Page, entries_before : dict) -> dict:
    entries_after = await consent_entries_before(page)
    changed = sorted(name for name, value in entries_after.items() if entries_before.get(name) != value)
    try:
        tcf_status = await page.evaluate(TCF_STATUS_JS)
    except Exception:
        tcf_status = None
    return {"tcf_status": tcf_status, "consent_storage_changed": changed}