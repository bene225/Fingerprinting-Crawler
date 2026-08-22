from playwright.async_api import Page
from os import path

# Datenübergabe, TODO fertigstellen
class DetectedFingerprint:
    
    def __init__(self, api : str, method : str, url : str ) -> None:
        self.type = api
        self.method = method
        self.url = url
        # Dataclass nutzen

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
    
    # Aufruf auf Website duch mp wenn Fp erkannt, dann zählen
    # location href aus der mp.js
    async def _append_event(self, _, api, method, location_href) -> None:
        self.events.append(DetectedFingerprint(api=api, method=method,url=location_href))
        