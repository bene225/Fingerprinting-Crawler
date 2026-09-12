from playwright.async_api import Page
from os import path
from dataclasses import dataclass
import json
from core.browser_controller import origin_domain

# Datenübergabe, TODO fertigstellen
@dataclass
class DetectedFingerprint:
    api : str
    method : str
    url : str
    third_party : bool | str # TODO: evtl nacharbeiten hier
        

# https://playwright.dev/python/docs/api/class-browsercontext
class Injector:
    def __init__(self) -> None:
        self.events : list[DetectedFingerprint] = []
    
    async def integrade_monkeypatch(self, page : Page) -> None:
        # app_ev durch Browser aufrufbar machen 
        await page.expose_binding("register_fp", self._append_event)
        # Skript einlesen und in Website einfügen
        with open("core/monkeypatch.js", "r", encoding="utf-8") as mp_script:
            mp_script = mp_script.read()
        await page.add_init_script(mp_script)
        
    async def integrade_js_cookie_block(self, url_uncut : str, page : Page) -> None:
        escaped_url = first_party_url_to_js(url_uncut)
        with open("core/js_cookie_block.js", encoding="utf-8") as js_cookie_block_file:
            js_cookie_block_script = js_cookie_block_file.read()
            await page.add_init_script(f"window._location_url = {escaped_url};\n" + js_cookie_block_script)
    
    # Aufruf auf Website duch mp wenn Fp erkannt, dann zählen
    # location href aus der mp.js
    async def _append_event(self, _, api, method, location_href, third_party) -> None:
        self.events.append(DetectedFingerprint(api=api, method=method,url=location_href, third_party=third_party))
        
def first_party_url_to_js(url_uncut :str) -> str:
    cutted_url = origin_domain(url_uncut=url_uncut)
    escaped_url = json.dumps(cutted_url)
    return escaped_url