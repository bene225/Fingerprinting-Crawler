from collections import Counter
from playwright.async_api import  Playwright, Browser, BrowserContext, Route, Request, async_playwright
from utils.origin_domain import origin_domain

# Vorbereitung für Pydantic 


class BrowserController:
    
    # Übergeben von Config
    def __init__(self, headless: bool , browser_type : str, allow_3p : bool ) -> None:
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
        # Loggin von "request", alle an context anhängen 
        all_requests : list[tuple[str, str]] = []
        context.all_requests = all_requests # type: ignore
        context.on("request", lambda request: all_requests.append((origin_domain(request.url), request.resource_type)))
        return context
    
    async def clear_3p(self, context : BrowserContext) -> None:
        domains = getattr(context, "thirdp_domains", set())
        for domain in domains:
            await context.clear_cookies(domain=domain)

    # Kennzahlen dict. Aufruf vor context.close() 
    async def collect_stats(self, context : BrowserContext, url : str, events : list) -> dict:
        main_site = origin_domain(url)
        # Seitentitel, (für Fehler)
        title = await context.pages[0].title() if context.pages else ""

        # Nur 3P, leere Domains verwerfen (req jeder einzeln. dann noch jeder einmalig, also wer)[Einbindungen]
        requests_3p = [(domain, res_type) for domain, res_type in getattr(context, "all_requests", []) if domain and domain != main_site]
        domains_3p = sorted({domain for domain, _ in requests_3p})
        # Nur 3P-Skripte für Tracker Radar, vgl mit hist
        script_domains_3p = sorted({domain for domain, res_type in requests_3p if res_type == "script"})

        # Nimm nur 3p Scripts, davon die Domain (wer hat wirklich fingerprinting betrieben) [echte Aufrufe]
        fp_sources = sorted({origin_domain(event.script_url) for event in events if event.script_url})
        # FP-Aufrufe nach Herkunft: third_party aus monkeypatch.js (True/False, "Keine py_url" = unbekannt)
        fp_events_1p = [event for event in events if event.third_party is False]
        fp_events_3p = [event for event in events if event.third_party is True]

        # Cookies: httpOnly = per HTTP gesetzt, Rest = per HTTP oder JS
        cookies = await context.cookies()
        # Cookies teilen in Anbieter
        cookie_sites = [(origin_domain(c.get("domain", "").lstrip(".")), c) for c in cookies]
        cookies_1p = [c for site, c in cookie_sites if site == main_site]
        cookies_3p = [(site, c) for site, c in cookie_sites if site not in ("", main_site)]
        # Partitioniert (CHIPS)
        cookie_sources_3p = sorted({site for site, c in cookies_3p if not c.get("partitionKey")})
        cookie_sources_partitioned = sorted({site for site, c in cookies_3p if c.get("partitionKey")})

        return {
            "hist_crawl": False,
            "title": title,
            "n_3p_requests": len(requests_3p),
            "requests_per_type": dict(Counter(res_type for _, res_type in requests_3p)), # z.B. {"script": 12, "image": 30}
            "n_3p_domains": len(domains_3p),
            "domains_3p": domains_3p,
            "n_script_domains_3p": len(script_domains_3p),
            "script_domains_3p": script_domains_3p,
            "n_fp_sources": len(fp_sources),
            "fp_sources": fp_sources,
            "n_fp_calls": len(events),
            "fp_calls_per_api": dict(Counter(event.api for event in events)), # z.B. {"canvas": 12, "WebGL": 30}
            "fp_calls_per_method": dict(Counter(f"{event.api}.{event.method}" for event in events)), # z.B. {"canvas.toDataURL": 4}
            "n_fp_calls_1p": len(fp_events_1p),
            "n_fp_calls_3p": len(fp_events_3p),
            "n_fp_calls_unbekannt": len(events) - len(fp_events_1p) - len(fp_events_3p),
            "fp_calls_per_api_1p": dict(Counter(event.api for event in fp_events_1p)),
            "fp_calls_per_api_3p": dict(Counter(event.api for event in fp_events_3p)),
            "n_cookies": len(cookies),
            "n_cookies_1p": len(cookies_1p),
            "n_cookies_3p": len(cookies_3p),
            "n_cookies_http_sicher": sum(1 for c in cookies if c.get("httpOnly")),
            "n_cookies_http_oder_js": sum(1 for c in cookies if not c.get("httpOnly")),
            "n_cookie_sources_3p": len(cookie_sources_3p),
            "cookie_sources_3p": cookie_sources_3p,
            "cookie_sources_partitioned": cookie_sources_partitioned,
        }

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