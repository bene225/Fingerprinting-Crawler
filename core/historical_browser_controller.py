from collections import Counter
from core.browser_controller import BrowserController
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

     
    async def _log_live_req(self, context : BrowserContext) -> None:
        blocked_live_requests : list[str] = []
        # Liste an Context 
        context.blocked_live_requests = blocked_live_requests # type: ignore
        await context.route("**/*", lambda route, request: _allow_only_archive(route, request, blocked_live_requests))

    # Kennzahlen dict. Aufruf vor context.close(). url = Original- oder Wayback-URL der Website
    async def collect_historical_stats(self, context : BrowserContext, url : str) -> dict:
        # Bei Wayback-URL erst Praefix abschneiden, sonst waere main_site archive.org und alles 3P
        main_site = utils.origin_domain.origin_domain(utils.wayback.original_url(url) or url)
        # Seitentitel, um Fehlerseiten des Archivs zu erkennen
        title = await context.pages[0].title() if context.pages else ""

        # Nur 3P, leere Domains verwerfen (req jeder einzeln. dann noch jeder einmalig, also wer)
        requests_3p = [(domain, res_type) for domain, res_type in getattr(context, "all_requests", []) if domain and domain != main_site]
        domains_3p = sorted({domain for domain, _ in requests_3p})
        # Nur 3P-Skripte (Eingabe fuer Tracker Radar), sonst zaehlen Tracking-Pixel einer FP-Domain mit
        script_domains_3p = sorted({domain for domain, res_type in requests_3p if res_type == "script"})

        return {
            "title": title,
            "n_3p_requests": len(requests_3p),
            "requests_per_type": dict(Counter(res_type for _, res_type in requests_3p)), # z.B. {"script": 12, "image": 30}
            "n_3p_domains": len(domains_3p),
            "domains_3p": domains_3p,
            "n_script_domains_3p": len(script_domains_3p),
            "script_domains_3p": script_domains_3p,
            "n_blocked_live_requests": len(getattr(context, "blocked_live_requests", [])), # Qualitaet des Snapshots
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

# Archivierte 3p einbindungen mitzählen
# None = Toolbar, wombat.js; archive.org = Toolbar
def _append_archived(request : Request, all_requests : list) -> None:
    url = utils.wayback.original_url(request.url)
    if url is None:
        return
    domain = utils.origin_domain.origin_domain(url)
    if domain != "archive.org":
        all_requests.append((domain, request.resource_type))