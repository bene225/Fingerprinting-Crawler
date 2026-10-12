import asyncio
import time
from core.browser_controller import BrowserController, request_stats, fp_stats
import utils.origin_domain
import utils.wayback
from playwright.async_api import  Playwright, Browser, BrowserContext, Route, Request, async_playwright


# Hoechstens rate Anfragen pro Sekunde an Wayback, egal wie viele Seiten gleichzeitig laden (eine Seite allein schickt Spitzen von >100/s)
class _Pacer:
    def __init__(self, rate : float) -> None:
        self._max_rate = rate
        self._set_rate(rate)
        self._next = 0.0

    def _set_rate(self, rate : float) -> None:
        self.rate = rate
        self._interval = 1 / rate

    async def wait(self) -> None:
        now = time.monotonic()
        slot = max(now, self._next)
        self._next = slot + self._interval
        if slot > now:
            await asyncio.sleep(slot - now)

    # Nach einer Drosselung durch Wayback: Rate um 30 % senken, nicht unter 1 pro Sekunde. Rueckgabe: neue Rate
    def slower(self) -> float:
        self._set_rate(max(min(1.0, self._max_rate), self.rate * 0.7))
        return self.rate

    # Nach einer Stunde ohne Drosselung: wieder schneller, hoechstens bis zur Startrate
    def faster(self) -> float:
        self._set_rate(min(self._max_rate, self.rate / 0.7))
        return self.rate


class HistoricalBrowserController (BrowserController):
    def __init__(self, headless : bool, browser_type : str, allow_3p : bool, archive_rate : float = 6.0, archive_light : bool = True) -> None:
        super().__init__(headless, browser_type, allow_3p)
        # Gemeinsam fuer alle Seiten (Contexts)
        self._pacer = _Pacer(archive_rate)
        self._archive_light = archive_light

    # Anfragen pro Sekunde an Wayback: nach einer Drosselung weniger, nach einer sperrfreien Stunde wieder mehr (bis zur Startrate)
    @property
    def rate(self) -> float:
        return self._pacer.rate

    def slower(self) -> float:
        return self._pacer.slower()

    def faster(self) -> float:
        return self._pacer.faster()

    # Nach dem Laden warten, bis keine Anfrage mehr offen ist und `quiet` Sekunden lang keine neuen FP-Aufrufe kamen. Mindestens `minimum`, hoechstens `maximum` Sekunden.
    # Wayback liefert langsam (Weiterleitungen je Skript, Mengenbegrenzung): bei einem festen Zeitpunkt wuerden spaet startende Skripte (Tag-Manager-Ketten) abgeschnitten
    async def wait_until_quiet(self, context : BrowserContext, events : list, minimum : float, maximum : float, quiet : float = 5.0) -> dict:
        start = last_change = time.monotonic()
        last_count = len(events)
        while True:
            await asyncio.sleep(0.5)
            now = time.monotonic()
            if len(events) != last_count or getattr(context, "pending_requests", None):
                last_count = len(events)
                last_change = now
            waited = now - start
            if waited >= maximum:
                return {"wait_seconds": round(waited), "wait_capped": True}
            if waited >= minimum and now - last_change >= quiet:
                return {"wait_seconds": round(waited), "wait_capped": False}

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
        # Aufnahmezeitpunkt jeder ausgelieferten Skript-Kopie (Original-URL -> Zeitstempel), um alte von neuen Kopien zu trennen
        script_captures : dict[str, str] = {}
        context.script_captures = script_captures # type: ignore
        context.on("request", lambda request: _append_script_capture(request, script_captures))
        # Von Wayback gedrosselte Antworten (429) zaehlen: Skripte fehlen dann still, die Messung waere untererfasst
        throttled : list[str] = []
        context.archive_429 = throttled # type: ignore
        context.on("response", lambda response: throttled.append(response.url) if response.status == 429 else None)
        # Verbindungsfehler zu Wayback (abgelehnt, abgebrochen, Zeitueberschreitung): auch dann fehlen Skripte still. Eigene Abbrueche zaehlen nicht
        conn_errors : list[str] = []
        context.archive_conn_errors = conn_errors # type: ignore
        context.on("requestfailed", lambda request: _append_conn_error(request, conn_errors))
        # Offene Anfragen (gestartet, noch nicht fertig oder fehlgeschlagen): fuer wait_until_quiet
        pending : set = set()
        context.pending_requests = pending # type: ignore
        context.on("request", lambda request: pending.add(request))
        context.on("requestfinished", lambda request: pending.discard(request))
        context.on("requestfailed", lambda request: pending.discard(request))
        # Serverfehler (5xx) von Wayback, nur zur Auswertung
        server_errors : list[str] = []
        context.archive_5xx = server_errors # type: ignore
        context.on("response", lambda response: server_errors.append(response.url) if response.status >= 500 else None)
        return context

    # Geblockte Live Req mitschreiben
    async def _log_live_req(self, context : BrowserContext) -> None:
        blocked_live_requests : list[str] = []
        # Liste an Context 
        context.blocked_live_requests = blocked_live_requests # type: ignore
        await context.route("**/*", lambda route, request: _allow_only_archive(route, request, blocked_live_requests, self._pacer, self._archive_light))

    # Kennzahlen dict. Aufruf vor context.close(). url = Original- oder Wayback-URL der Website
    async def collect_historical_stats(self, context : BrowserContext, url : str, events : list) -> dict:
        # Bei Wayback-URL erst Praefix abschneiden, sonst alles 3P wg anfang wb
        main_site = utils.origin_domain.origin_domain(utils.wayback.original_url(url) or url)
        # Seitentitel, um Fehlerseiten des Archivs zu erkennen
        title = await context.pages[0].title() if context.pages else ""

        # 3P-Einbindungen: gemeinsame Funktion mit live (BrowserController), damit identisch berechnet
        request_fields = request_stats(getattr(context, "all_requests", []), main_site)
        # FP-Aufrufe aus dem Monkeypatch, gleiche Funktion wie live (Cookies bewusst nicht: im Archiv nicht aussagekraeftig)
        fp_fields = fp_stats(events)
        # Alter der ausgelieferten 3P-Skript-Kopien gegen das Snapshot-Datum
        gap_fields = script_gap_stats(getattr(context, "script_captures", {}), url, main_site)

        return {
            "hist_crawl": True,
            "title": title,
            **request_fields,
            **fp_fields,
            **gap_fields,
            "n_archive_429": len(getattr(context, "archive_429", [])), # Von Wayback gedrosselte Antworten
            "n_archive_conn_errors": len(getattr(context, "archive_conn_errors", [])), # Verbindung zu Wayback abgelehnt/abgebrochen
            "n_archive_5xx": len(getattr(context, "archive_5xx", [])), # Serverfehler von Wayback (nur Auswertung)
            "n_blocked_live_requests": len(getattr(context, "blocked_live_requests", [])), # Nicht umgeschriebenes
            # Escape-Domains getrennt, um ihren Anteil zu zeigen (sind oben mitgezaehlt)
            "blocked_live_domains": sorted({utils.origin_domain.origin_domain(url) for url in getattr(context, "blocked_live_requests", [])} - {""}),
        }

# Aufnahmedatum der 3P-Skript-Kopien gegen das Snapshot-Datum (das Archiv liefert sonst die zeitlich naechste Kopie, auch aus einem anderen Jahr)
# script_captures = Original-URL -> Zeitstempel, snapshot_url = Archiv-Adresse des Snapshots
def script_gap_stats(script_captures : dict, snapshot_url : str, main_site : str) -> dict:
    snapshot_timestamp = utils.wayback.capture_timestamp(snapshot_url)
    # Pro Domain die Kopie mit der groessten Abweichung: (Zeitstempel, Tage mit Vorzeichen)
    worst_copy : dict[str, tuple[str, int]] = {}
    if snapshot_timestamp:
        for script_url, copy_timestamp in script_captures.items():
            domain = utils.origin_domain.origin_domain(script_url)
            if not domain or domain == main_site:
                continue
            gap = utils.wayback.capture_gap_days(copy_timestamp, snapshot_timestamp)
            if domain not in worst_copy or abs(gap) > abs(worst_copy[domain][1]):
                worst_copy[domain] = (copy_timestamp, gap)
    return {
        "script_capture_dates": {domain: copy[0][:8] for domain, copy in sorted(worst_copy.items())}, # JJJJMMTT der Kopie
        "script_gap_days": {domain: copy[1] for domain, copy in sorted(worst_copy.items())}, # + neuer, - aelter als Snapshot
        "n_script_domains_gap_over_365": sum(1 for copy in worst_copy.values() if abs(copy[1]) > 365),
        "max_script_gap_days": max((abs(copy[1]) for copy in worst_copy.values()), default=0),
    }


# Kein live web
# archive.org (auch web-static., wayback-api.) durchlassen, alles andere abbrechen
# light: Bilder, Schriften, Videos gar nicht erst laden. Die Anfrage zaehlt trotzdem in den Kennzahlen (das request-Event kommt vor dem Abbruch), Skripte laden normal
async def _allow_only_archive(route : Route, request : Request, blocked_live_requests : list, pacer : _Pacer, light : bool) -> None:
    requested_site = utils.origin_domain.origin_domain(request.url)
    try:
        if requested_site != "archive.org":
            blocked_live_requests.append(request.url)
            await route.abort()
        elif light and request.resource_type in ("image", "font", "media"):
            await route.abort()
        else:
            await pacer.wait()
            await route.continue_()
    except Exception:
        pass # Seite oder Context schon geschlossen

# Lamba für 
# Archivierte 3p einbindungen mitzählen
# Keine Archiv-URL = Escape ins Live-Web: wird geblockt, Domain zählt
# archive.org niciht
# Aufnahmezeitpunkt der Skript-Kopie steht in der Archiv-Adresse. Bei Weiterleitung auf die naechste Kopie kommt eine
# Anfrage mit neuem Zeitstempel, die letzte gilt
def _append_script_capture(request : Request, script_captures : dict) -> None:
    if request.resource_type != "script":
        return
    url = utils.wayback.original_url(request.url)
    timestamp = utils.wayback.capture_timestamp(request.url)
    if url and timestamp:
        script_captures[url] = timestamp


def _append_archived(request : Request, all_requests : list) -> None:
    url = utils.wayback.original_url(request.url)
    domain = utils.origin_domain.origin_domain(url or request.url)
    if domain != "archive.org":
        all_requests.append((domain, request.resource_type))


# Fehlertexte von Chromium bei Verbindungsproblemen. Eigene Abbrueche (route.abort: Bilder, Live-Web) melden net::ERR_FAILED und zaehlen nicht
CONNECTION_FAILURES = ("ERR_CONNECTION", "ERR_TIMED_OUT", "ERR_EMPTY_RESPONSE", "ERR_NETWORK", "ERR_SOCKET", "ERR_SSL", "ERR_PROXY", "ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED")


def _append_conn_error(request : Request, conn_errors : list) -> None:
    failure = request.failure or ""
    if "archive.org" in request.url and any(sign in failure for sign in CONNECTION_FAILURES):
        conn_errors.append(failure)
