# FF3 Consent: keine Aktion / zustimmen / ablehnen. Huelle um measure_site (FF2), nichts Bestehendes geaendert:
# waehrend measure_site laeuft, ersetzt sie nur try_accept (-> Aktion) und consent_check (-> zusaetzlich TCF-Pruefung)
import core.consent
import core.logging
from config import CrawlConfig
from core.browser_controller import BrowserController
from core.live import measure_site
from core.logging import short_error
from playwright.async_api import Locator
from utils.check_internet import check_internet, wait_for_internet
from utils.crawl_utils import progress_line

import asyncio
import itertools
import re
import time
from dataclasses import replace
from urllib.parse import unquote


CONSENT_MODES = {"keine_aktion": "none", "zustimmen": "accept", "ablehnen": "reject"}
# Nicht messen: so viele FP-Aufrufe, dass der Treiber haengt/stirbt (ohne Buendelung). In der Arbeit als ausgeschlossen nennen
SKIP_SITES = {"https://economictimes.com"}
# Alle 6 Reihenfolgen reihum wie FF2
CONSENT_ORDERS = list(itertools.permutations(CONSENT_MODES))

# Klick-Protokoll: welcher Button wurde wirklich geklickt?
# - haengt einen Zuhoerer ans Fenster, der bei jedem Klick als Erster aufgerufen wird (true = vor der Seite, auch wenn das Banner danach verschwindet)
# - isTrusted: nur echte Klicks (= Playwright aus try_accept/try_reject), Klicks per Skript der Seite zaehlen nicht
# - composedPath: Kette vom angeklickten Element nach aussen (auch durch Shadow DOM) -> erstes Element, das ein Button/Link ist
# - schickt Text, id und Domain des Frames an Python: report_consent_click legt consent_step mit page.expose_binding an
#   (gleiche Technik wie register_fp im Monkeypatch) -> landet in der Liste clicks -> consent_click in den Daten
CLICK_LOG_JS = """() => window.addEventListener("click", (event) => {
    if (!event.isTrusted) return;
    const path = event.composedPath();
    const button = path.find(node => node instanceof Element && node.matches("button, a, input, [role=button]")) || path[0];
    window.report_consent_click({text: (button.innerText || button.value || "").replace(/\\s+/g, " ").trim().slice(0, 120),
                                 id: button.id || "", frame: location.hostname});
}, true)"""

# TCF-Abfrage: was hat die CMP gespeichert?
# - jede TCF-CMP stellt window.__tcfapi bereit, fehlt die Funktion -> keine TCF-Seite -> null
# - offizielle Abfrage (TCF v2): addEventListener liefert sofort den aktuellen Stand, danach wieder abmelden. Antwortet die CMP nicht in 2 s -> null
# - status: cmpuishown = Banner offen, nichts entschieden / useractioncomplete = gerade entschieden / tcloaded = Entscheidung aus dem Speicher
# - n_purposes: wie viele der 11 TCF-Zwecke (z.B. Geraeteinfos speichern, personalisierte Werbung, Messung) eine Einwilligung haben
#   n_vendors: wie viele Werbefirmen. Gezaehlt werden nur Einwilligungen, "berechtigtes Interesse" fuehrt TCF getrennt
TCF_DECISION_JS = """() => new Promise(resolve => {
    if (typeof window.__tcfapi !== "function") return resolve(null);
    const timer = setTimeout(() => resolve(null), 2000);
    window.__tcfapi("addEventListener", 2, (data, success) => {
        clearTimeout(timer);
        if (success && data && data.listenerId !== undefined) window.__tcfapi("removeEventListener", 2, () => {}, data.listenerId);
        if (!success || !data) return resolve(null);
        const granted = consents => Object.values(consents || {}).filter(Boolean).length;
        resolve({status: data.eventStatus || null, cmp_id: data.cmpId ?? null,
                 n_purposes: granted(data.purpose && data.purpose.consents), n_vendors: granted(data.vendor && data.vendor.consents)});
    });
})"""


# Was hat die CMP nach dem Klick gespeichert? "accept", "reject" oder None (keine Entscheidung / nicht lesbar)
# 1. TCF (Standard der Werbebranche, v.a. EU-Nachrichtenseiten): nur wenn wirklich entschieden wurde
#    (useractioncomplete = gerade geklickt, tcloaded = nach Neuladen aus dem Speicher). Mind. ein Zweck erlaubt = accept, keiner = reject
# 2. Ohne TCF die zwei haeufigsten CMPs ueber ihre Cookies:
#    OneTrust: OptanonConsent "groups=C0001:1,C0002:0,..." (C0001 = notwendig, immer an). Das Cookie gibt es schon VOR der Entscheidung
#    (alles 0) -> nur zaehlen, wenn OptanonAlertBoxClosed gesetzt ist (= Banner wurde bedient)
#    Cookiebot: CookieConsent "...marketing:true/false..." (entsteht erst mit der Entscheidung)
def decision(tcf : dict | None, entries : dict) -> str | None:
    if tcf and tcf["status"] in ("useractioncomplete", "tcloaded"):
        return "accept" if tcf["n_purposes"] > 0 else "reject"
    optional = [value for group, value in re.findall(r"(C\d{4}):([01])", unquote(str(entries.get("OptanonConsent", "")))) if group != "C0001"]
    if optional and "OptanonAlertBoxClosed" in entries:
        return "accept" if "1" in optional else "reject"
    marketing = re.search(r"marketing:(true|false)", unquote(str(entries.get("CookieConsent", ""))))
    return ("accept" if marketing.group(1) == "true" else "reject") if marketing else None


# Welche Stufe von try_accept/try_reject hat geklickt? Reihenfolge dort: 1. allgemeine CSS-Selektoren, 2. Selektoren bekannter CMPs,
# 3. Button-Text (get_by_role("button") -> Selektor "internal:role=button")
def consent_stage(selector : str) -> str:
    if selector in core.consent.tcf_accept_generic or selector in core.consent.tcf_reject_generic:
        return "1_css_allgemein"
    if selector in core.consent.tcf_accept_known or selector in core.consent.tcf_reject_known:
        return "2_css_cmp"
    return "3_text"


# Huelle: measure_site (FF2) misst wie immer vor und nach Consent und ruft dazwischen core.consent.try_accept und danach
# core.consent.consent_check auf. Fuer die Dauer dieses einen Aufrufs zeigen diese zwei Namen auf consent_step und check unten,
# danach (finally, auch bei Fehler) wieder auf die Originale. Geht, weil measure_site sie ueber das Modul aufruft und Seiten nacheinander laufen
async def measure_consent(bc : BrowserController, config : CrawlConfig, test_domain : str, site_id : int):
    original_accept, original_check = core.consent.try_accept, core.consent.consent_check
    clicks : list[dict] = []
    step = {} # was der Consent-Schritt herausfindet, landet mit in consent_check

    # Statt try_accept: 1. Klick-Protokoll in alle Frames (Banner ist nach loading_time schon da)
    # 2. je Modus try_accept (Original) / try_reject / nichts  3. Rest des Zeitfensters warten, damit "nach Consent"
    # in allen drei Modi gleich spaet gemessen wird (sonst waere keine_aktion frueher dran als die Bannersuche)
    async def consent_step(page, tries, polling):
        start = time.monotonic()
        await page.expose_binding("report_consent_click", lambda _, click: clicks.append(click))
        for frame in page.frames:
            try:
                await frame.evaluate(CLICK_LOG_JS)
            except Exception:
                pass
        clicked = None
        selector = None
        if config.consent_action != "none":
            # Stufe mitloggen: solange try_accept/try_reject laeuft, merkt sich jeder Playwright-Klick seinen Selektor
            # (nth(i) haengt " >> nth=i" an -> abschneiden). Danach wieder der normale Klick
            original_click = Locator.click
            async def logged_click(self, *args, **kwargs):
                nonlocal selector
                selector = getattr(getattr(self, "_impl_obj", None), "_selector", "").rsplit(" >> nth=", 1)[0]
                return await original_click(self, *args, **kwargs)
            Locator.click = logged_click # type: ignore nur fuer die Dauer der Suche
            try:
                clicker = original_accept if config.consent_action == "accept" else core.consent.try_reject
                clicked = await clicker(page, tries, polling)
            except Exception:
                clicked = False
            finally:
                Locator.click = original_click # type: ignore
        step["consent_seconds"] = round(time.monotonic() - start, 1)
        step["consent_selector"] = selector if clicked else None
        step["consent_stage"] = consent_stage(selector) if clicked and selector else None
        await asyncio.sleep(max(0, (config.consent_window or 0) - step["consent_seconds"]))
        return clicked

    # Statt consent_check, nach der Verweildauer: das Original (tcf_status, consent_storage_changed wie FF1/FF2) plus
    # tcf (gespeicherte Entscheidung), consent_click (geklickter Button), consent_cookies (geaenderte Werte), consent_decision, consent_verified
    async def check(page, entries_before):
        result = await original_check(page, entries_before)
        try:
            tcf = await page.evaluate(TCF_DECISION_JS)
        except Exception:
            tcf = None
        entries_after = await core.consent.consent_entries_before(page)
        result["consent_cookies"] = {name: str(value)[:300] for name, value in entries_after.items() if entries_before.get(name) != value}
        result |= {"consent_action": config.consent_action, "consent_click": clicks[0] if clicks else None, "tcf": tcf, **step}
        result["consent_decision"] = decision(tcf, entries_after)
        # Passt die Entscheidung zur Aktion?
        # keine_aktion: es darf nichts entschieden sein (sonst entscheidet die Seite selbst -> Website auffaellig)
        # nicht geklickt: nichts zu pruefen -> None
        # geklickt, TCF-Seite, aber keine Entscheidung: falscher Button (z.B. "Optionen verwalten") -> False
        # geklickt, weder TCF noch OneTrust/Cookiebot: nicht pruefbar -> None (dann ueber consent_click/consent_stage)
        if config.consent_action == "none":
            result["consent_verified"] = result["consent_decision"] is None
        elif step["consent_stage"] is None:
            result["consent_verified"] = None
        elif result["consent_decision"] is None:
            result["consent_verified"] = False if tcf else None
        else:
            result["consent_verified"] = result["consent_decision"] == config.consent_action
        return result

    core.consent.try_accept, core.consent.consent_check = consent_step, check
    try:
        await measure_site(bc, config, test_domain, site_id)
    finally:
        core.consent.try_accept, core.consent.consent_check = original_accept, original_check


# FF3-Ablauf wie crawl_block (FF2): je Modus eigene Datei ff3_<modus>.jsonl. Fehler -> Fehlerzeile und weiter, Browser tot -> Neustart und weiter
async def crawl_consent(config : CrawlConfig, sites : list[str]):
    output = config.path_to_output
    mode_configs = {mode: replace(config, consent_action=action, crawl_name=f"{config.crawl_name}_{mode}",
                                  path_to_output=output.with_name(f"{output.stem}_{mode}{output.suffix}"))
                    for mode, action in CONSENT_MODES.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    async with BrowserController(headless=config.headless, browser_type=config.BrowserType, allow_3p=config.allow_3p) as bc:
        done = {}
        next_id = {}
        for mode, mode_config in mode_configs.items():
            core.logging.write_config(mode_config)
            done[mode] = core.logging.done_crawls(mode_config)
            next_id[mode] = core.logging.resume_crawl(mode_config)
        start = time.time()
        processed = 0
        for position, test_domain in enumerate(sites, 1):
            if test_domain in SKIP_SITES:
                continue
            order = [mode for mode in CONSENT_ORDERS[(position - 1) % len(CONSENT_ORDERS)] if (test_domain, None) not in done[mode]]
            if not order:
                continue
            for mode in order:
                mode_config = mode_configs[mode]
                await wait_for_internet()
                try:
                    await asyncio.wait_for(measure_consent(bc, mode_config, test_domain, next_id[mode]), timeout=mode_config.site_timeout)
                except Exception as e:
                    print(f"Fehler bei {test_domain} [{mode}]: {short_error(e)}")
                    core.logging.write_error(next_id[mode], test_domain, mode_config, repr(e), check_internet())
                    # Toter Treiber: is_connected() bleibt True -> echter Test mit neuem Context, sonst nur noch Fehlerzeilen (FF2)
                    try:
                        await asyncio.wait_for((await bc.new_context("")).close(), timeout=30)
                    except Exception:
                        print("Browser abgestuerzt -> Neustart, weiter mit der naechsten Seite")
                        try:
                            await bc.__aexit__(None, None, None)
                        except Exception:
                            pass
                        await bc.__aenter__()
                next_id[mode] += 1
            processed += 1
            print(progress_line(position, len(sites), start, processed))
