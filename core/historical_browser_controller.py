from core.browser_controller import BrowserController, request_stats
import utils.origin_domain
import utils.wayback
from playwright.async_api import  Playwright, Browser, BrowserContext, Route, Request, async_playwright

class HistoricalBrowserController (BrowserController):
    # new context hier immer aufrufen für isolierten Test 
    async def new_context(self, url : str) -> BrowserContext:
        if self._browser is None:
            raise RuntimeError("Async with zuerst aufrufen")
        context = await self._browser.new_context()
        await self._log_live_req(context)

        # Alle archivierten Requests (Original-Domain, Art) mitschreiben, für collect_stats. 
        all_requests : list[tuple[str, str]] = []
        context.all_requests = all_requests # type: ignore
        context.on("request", lambda request: _append_archived(request, all_requests))
        return context

    # Geblockte Live Req mitschreiben
    async def _log_live_req(self, context : BrowserContext) -> None:
        blocked_live_requests : list[str] = []
        # Liste an Context 
        context.blocked_live_requests = blocked_live_requests # type: ignore
        await context.route("**/*", lambda route, request: _allow_only_archive(route, request, blocked_live_requests))

    # Kennzahlen dict. Aufruf vor context.close(). url = Original- oder Wayback-URL der Website
    async def collect_historical_stats(self, context : BrowserContext, url : str) -> dict:
        # Bei Wayback-URL erst Praefix abschneiden, sonst alles 3P wg anfang wb
        main_site = utils.origin_domain.origin_domain(utils.wayback.original_url(url) or url)
        # Seitentitel, um Fehlerseiten des Archivs zu erkennen
        title = await context.pages[0].title() if context.pages else ""

        # 3P-Einbindungen: gemeinsame Funktion mit live (BrowserController), damit identisch berechnet
        request_fields = request_stats(getattr(context, "all_requests", []), main_site)

        return {
            "hist_crawl": True,
            "title": title,
            **request_fields,
            "n_blocked_live_requests": len(getattr(context, "blocked_live_requests", [])), # Nicht umgeschriebenes
            # Escape-Domains getrennt, um ihren Anteil zu zeigen (sind oben mitgezaehlt)
            "blocked_live_domains": sorted({utils.origin_domain.origin_domain(url) for url in getattr(context, "blocked_live_requests", [])} - {""}),
        }

# Kein live web
# archive.org (auch web-static., wayback-api.) durchlassen, alles andere abbrechen 
async def _allow_only_archive(route : Route, request : Request, blocked_live_requests : list) -> None:
    requested_site = utils.origin_domain.origin_domain(request.url)
    if requested_site == "archive.org":
        await route.continue_()
    else:
        blocked_live_requests.append(request.url)
        await route.abort()

# Lamba für 
# Archivierte 3p einbindungen mitzählen
# Keine Archiv-URL = Escape ins Live-Web: wird geblockt, Domain zählt
# archive.org niciht
def _append_archived(request : Request, all_requests : list) -> None:
    url = utils.wayback.original_url(request.url)
    domain = utils.origin_domain.origin_domain(url or request.url)
    if domain != "archive.org":
        all_requests.append((domain, request.resource_type))