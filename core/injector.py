from playwright.async_api import Page
from os import path

# Datenübergabe, TODO fertigstellen
class DetectedFingerprint:
    
    def __init__(self, type : str, method : str, url : str ) -> None:
        self.type = type
        self.method = method
        self.url = url
        

# https://playwright.dev/python/docs/api/class-browsercontext
class Injector:
    def __init__(self) -> None:
        self.events : list[DetectedFingerprint] = []
    
    async def integrade_monkeypatch(self, page : Page) -> None:
        # Zählfunktion verfügbar machen
        await page.expose_binding("register_fp", _append_event)
        # Skript einlesen und in Website einfügen
        with open("monkeypatch.js", "r", encoding="utf-8") as mp_script:
            mp_script = mp_script.read()
        await page.add_init_script(mp_script)