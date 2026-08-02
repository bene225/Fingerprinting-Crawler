from playwright.async_api import  Playwright, Browser, BrowserContext, Route, Request, async_playwright
from typing import Literal
import tldextract

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
        # Gewählter Browser aus BrowserType
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
        # Bei Bedarf nur 1P
        if self._allow_3p == False:
            
            
        return context


# Bsp: blog.bmw.de => bmw.de
# Erkennung des Hosts 
def _origin_domain(url_uncut : str) -> str:
    url_parts = tldextract.extract(url_uncut)
    hostname = url_parts.registered_domain
    return hostname

async def _block_thirdparty_cookies(route : Route, request : Request, main_site : str):
    requested_site = _origin_domain(request.url)
    
    # 1P erkennen und durchlassen
    if requested_site == main_site:
        await route.continue_()
        return
    
    # RO -> Kopie erstellen
    headers = request.headers
    # entferne Cookies-Auslesen von 3P 
    # TODO setzen auch verhindern
    headers.pop("cookie", None)
    await route.continue_(headers = headers)
    
    