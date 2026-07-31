from playwright.async_api import  Playwright, Browser, BrowserContext, async_playwright
from typing import Literal

# Vorbereitung für Pydantic 
BrowserType = Literal["chromium", "firefox"]

class BrowserController:
    
    # Übergeben von Config
    def __init__(self, headless: bool = True, browser_type : BrowserType = "chromium", allow_3p : bool = True) -> None:
        # _ : Variablen werden von Config verwaltet (da ändern). Ab hier dann nicht ändern.
        self._headless = headless
        self._browser_type = browser_type
        self._allow_3p = allow_3p
        
        # Playwright Start braucht Zeit await. Nicht im Kontruktor erlaubt. => Überagbe von Playwright und Browser nicht sofort
        self._playwright : Playwright | None = None
        self._browser : Browser | None = None
    
    #Hier wird Browser gestartet    
    async def __aenter__(self) -> BrowserController: # -> BC wird erst hier fertig 
        self._playwright = await async_playwright().start()
        self._browser = await getattr(self._playwright,self._browser_type).launch(headless = self._headless)
        return self
    
    # Ressourcenverwaltung, schließt den Browser wieder (with)
    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright : 
            await self._playwright.stop()
            
    # new context hier immer aufrufen für isolierten Test 
    async def new_context(self, url : str) -> BrowserContext:
        # 
        if self._browser is None:
            raise RuntimeError("Async with zuerst aufrufen")
        context = await self._browser.new_context()
        # 3P-Cookies bei Bedarf ab Browser Start blockieren
        if self._allow_3p == False:
            
            
        return context



def _cookie_origin_domain(url_uncut : str) -> str:
    
return