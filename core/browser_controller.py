from playwright.async_api import  Playwright, Browser, BrowserContext, Route, Request, async_playwright
from typing import Literal
from utils.origin_domain import origin_domain

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
            main_site = origin_domain(url)
            thirdp_domains : set[str] = set()
            # Set an Context binden KI Idee
            context.thirdp_domains = thirdp_domains # type: ignore
            # route->3p->dann wieder alles was darf an route. lambda KI
            await context.route("**/*", lambda route, request: _detect_thirdparty_cookies(route, request, main_site, thirdp_domains))
        return context
    
    async def clear_3p(self, context : BrowserContext) -> None:
        domains = getattr(context, "thirdp_domains", set())
        for domain in domains:
            await context.clear_cookies(domain=domain)

async def _detect_thirdparty_cookies(route : Route, request : Request, main_site : str, thirdp_domains : set) -> None:
    requested_site = origin_domain(request.url)
    if (main_site != requested_site):
        thirdp_domains.add(requested_site)
    await route.continue_()


        
# main_site = first_party, requested_site = einzelner request
"""async def _block_thirdparty_cookies(route : Route, request : Request, main_site : str):
    requested_site = origin_domain(request.url)
    first_party = requested_site == main_site
    # 1P erkennen und durchlassen
    if first_party:
        await route.continue_()
        return
    
    #COOKIES LESEN BLOCKIEREN
    # RO -> Kopie erstellen mit dict sonst nur referenz
    request_headers = dict(request.headers)
    # entferne Cookies-Auslesen von 3P 
    request_headers.pop("cookie", None)
    # TODO Wird Cookies im Header immer klein geschrieben ???
    
    # COOKIES SCHREIBEN BLOCKIEREN
    # Antwort vom Server abfangen vor Browser, C löschen TODO hier evtl Restrikton, weil die Header trotzdem ankommen
    response = await route.fetch(headers=request_headers)
    response_header = dict(response.headers)
    response_header.pop("set-cookie", None)
    await route.fulfill(response=response, headers=response_header)
    """