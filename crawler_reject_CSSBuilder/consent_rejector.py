"""
consent_rejector.py – findet und klickt den "Ablehnen"-Button von Cookie-Bannern.

Zwei Verwendungen:
  1) Als Discovery-Crawler über die CrUX-Top-Liste Deutschland (oder --source tranco):
        uv run consent_rejector.py --top 2000 --concurrency 4 --retries 1 --screenshots
     -> results/results.csv            (eine Zeile pro Domain, Spalte "outcome":
                                        rejected | no_banner | blocked | unreachable | click_failed | error;
                                        bei Fehlern zeigen "stage" + "error_type", wo er entstanden ist)
     -> results/discovered_selectors.json  (Domain -> CSS-Selektor des Reject-Buttons)
  2) Als Bibliothek in deinem Crawler (z. B. banner_handler.py):
        from consent_rejector import RuleSet, reject_consent
        rules = RuleSet.load("reject_rules.json")
        result = await reject_consent(page, rules)

Strategie (in dieser Reihenfolge, erste erfolgreiche gewinnt):
  Stufe 1 "rule":    ~900 Regeln aus DuckDuckGo autoconsent (CMP- und seitenspezifisch)
  Stufe 2 "generic": generische CSS-Selektoren (id/class/data-* enthält reject/decline/…)
  Stufe 3 "text":    Text-Matching mit mehrsprachiger Wortliste, erzeugt einen CSS-Selektor

Abhängigkeiten: playwright  (uv add playwright && uv run playwright install chromium)
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import re
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Browser, Frame, Page, async_playwright

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"

# ---------------------------------------------------------------------------
# Stufe 2 + 3: Konfiguration. Hier kannst du die Wortlisten aus dem Uni-Repo
# (cookie-drift) einsetzen.
# ---------------------------------------------------------------------------
GENERIC_REJECT_SELECTORS = [
    "#didomi-notice-disagree-button",
    "[data-testid='uc-deny-all-button']",
    ".fc-cta-do-not-consent",                 # Google Funding Choices
    "#onetrust-reject-all-handler",
    "#CybotCookiebotDialogBodyButtonDecline",
    ".sp_choice_type_13",
    "button[id*='reject' i]", "button[class*='reject' i]",
    "button[id*='decline' i]", "button[class*='decline' i]",
    "button[id*='deny' i]", "button[class*='deny' i]",
    "button[id*='ablehnen' i]", "button[class*='ablehnen' i]",
    "[role='button'][id*='reject' i]", "a[id*='reject' i]",
    "[data-action*='reject' i]", "[data-action*='deny' i]",
    "[data-testid*='reject' i]", "[data-testid*='decline' i]",
    "button[aria-label*='reject' i]", "button[aria-label*='ablehnen' i]",
]

# Normalisiert (klein, Whitespace zusammengefasst). Reihenfolge = Priorität.
REJECT_WORDS = [
    # DE
    "alle ablehnen", "ablehnen", "alles ablehnen", "nur notwendige", "nur erforderliche",
    "nur notwendige cookies", "nur essenzielle cookies", "nicht einwilligen",
    "optionale cookies ablehnen", "weiter ohne einwilligung", "ohne zustimmung fortfahren",
    # EN
    "reject all", "reject", "decline all", "decline", "deny all", "deny",
    "reject all cookies", "reject cookies", "reject non-essential", "necessary only",
    "only necessary", "essential only", "use necessary cookies only", "do not consent",
    "i do not accept", "continue without accepting", "refuse all",
    # FR / ES / IT / NL / PL / PT
    "tout refuser", "refuser", "continuer sans accepter",
    "rechazar todo", "rechazar", "rifiuta tutto", "rifiuta",
    "alles weigeren", "weigeren", "odrzuć wszystkie", "odrzuć", "rejeitar tudo", "rejeitar",
]

# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------
@dataclass
class RejectResult:
    status: str = "no_banner_detected"   # rejected | no_banner_detected | click_failed | error
    method: str = ""                     # rule | generic | text
    rule_name: str = ""
    selector: str = ""                   # der geklickte CSS-Selektor ("a -> b" bei mehreren Klicks)
    frame_url: str = ""                  # leer = Hauptframe
    banner_gone: bool | None = None      # Banner nach dem Klick verschwunden?
    error: str = ""
    stage: str = ""                      # bei Fehlern: in welcher Stufe (z. B. "reject:rule")


@dataclass
class RuleSet:
    rules: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "RuleSet":
        data = json.loads(Path(path).read_text())
        rules = data["rules"]
        for r in rules:  # Regex einmal vorkompilieren
            pat = r.get("runContext", {}).get("urlPattern")
            r["_re"] = re.compile(pat) if pat else None
        return cls(rules)


# ---------------------------------------------------------------------------
# Stufe 1: Interpreter für die autoconsent-Regelsprache
# ---------------------------------------------------------------------------
class RuleEngine:
    """
    Führt Regel-Schritte (dicts) auf einem Playwright-Frame aus.
    Semantik wie in autoconsent/lib/cmps/base.ts, plus: eine Liste als Schritt
    = Sequenz (alle müssen klappen).
    """

    def __init__(self, frame: Frame, max_wait_ms: int = 4000, eval_default: bool = False):
        self.frame = frame
        # JS-Snippets ("eval") führen wir nicht aus. In detectCmp/detectPopup werten
        # wir sie als "wahr" (optimistisch weiterprüfen), im optOut als "falsch".
        self.eval_default = eval_default
        self.max_wait_ms = max_wait_ms   # autoconsent wartet bis 10 s – für Crawls zu lang
        self.clicked: list[str] = []     # Protokoll der geklickten Selektoren

    # --- Selektoren -------------------------------------------------------
    @staticmethod
    def to_pw(sel: str) -> str | None:
        """autoconsent-Selektor -> Playwright-Selektor (None = nicht unterstützt)."""
        if sel.startswith("xpath/"):
            return "xpath=" + sel[len("xpath/"):]
        if sel.startswith(("aria/", "text/", "pierce/")):
            return None
        return sel

    def locator(self, sel, text: str | None = None):
        # Liste = Kette (meist Shadow-DOM-Host -> Element darin). Playwright-CSS
        # durchdringt offene Shadow-Roots automatisch, daher reicht .locator().locator().
        parts = sel if isinstance(sel, list) else [sel]
        loc = None
        for p in parts:
            pw = self.to_pw(p)
            if pw is None:
                return None
            loc = self.frame.locator(pw) if loc is None else loc.locator(pw)
        if text:
            loc = loc.filter(has_text=text.strip())
        return loc

    @staticmethod
    def sel_str(sel) -> str:
        return " >> ".join(sel) if isinstance(sel, list) else sel

    # --- Primitive --------------------------------------------------------
    async def exists(self, sel) -> bool:
        loc = self.locator(sel)
        try:
            return loc is not None and await loc.count() > 0
        except Exception:
            return False

    async def visible(self, sel, check: str = "all") -> bool:
        loc = self.locator(sel)
        if loc is None:
            return False
        try:
            n = await loc.count()
            vis = [await loc.nth(i).is_visible() for i in range(min(n, 20))]
        except Exception:
            return False
        if check == "none":
            return not any(vis)
        if check == "any":
            return any(vis)
        return bool(vis) and all(vis)

    async def poll(self, fn, timeout_ms: int) -> bool:
        deadline = time.monotonic() + min(timeout_ms, self.max_wait_ms) / 1000
        while True:
            if await fn():
                return True
            if time.monotonic() > deadline:
                return False
            await asyncio.sleep(0.2)

    async def click(self, sel, all_: bool = False, text: str | None = None) -> bool:
        loc = self.locator(sel, text)
        if loc is None:
            return False
        try:
            n = await loc.count()
        except Exception:
            return False
        if n == 0:
            return False
        targets = range(n) if all_ else range(1)
        for i in targets:
            el = loc.nth(i)
            try:
                # echter (trusted) Klick bevorzugt …
                await el.click(timeout=1500)
            except Exception:
                try:
                    # … sonst JS-Klick wie autoconsent (funktioniert auch verdeckt)
                    await el.evaluate("e => e.click()")
                except Exception:
                    continue
        self.clicked.append(self.sel_str(sel))
        return True

    # --- Schritt-Auswertung ----------------------------------------------
    async def step(self, s) -> bool:
        if isinstance(s, list):                     # Erweiterung: Sequenz
            return await self.sequence(s)

        results: list[bool] = []
        if "exists" in s:
            results.append(await self.exists(s["exists"]))
        if "visible" in s:
            results.append(await self.visible(s["visible"], s.get("check", "all")))
        if "waitFor" in s:
            results.append(await self.poll(lambda: self.exists(s["waitFor"]), s.get("timeout", 10000)))
        if "waitForVisible" in s:
            results.append(await self.poll(
                lambda: self.visible(s["waitForVisible"], s.get("check", "any")), s.get("timeout", 10000)))
        if "click" in s:
            results.append(await self.click(s["click"], s.get("all", False), s.get("text")))
        if "waitForThenClick" in s:
            sel = s["waitForThenClick"]
            ok = await self.poll(lambda: self.exists(sel), s.get("timeout", 10000))
            results.append(ok and await self.click(sel, s.get("all", False), s.get("text")))
        if "wait" in s:
            await asyncio.sleep(min(s["wait"], self.max_wait_ms) / 1000)
            results.append(True)
        if any(k in s for k in ("hide", "stylesheet", "removeClass", "setStyle", "addStyle")):
            results.append(True)                    # rein kosmetisch -> ignorieren
        if "eval" in s:
            results.append(self.eval_default)
        if "cookieContains" in s:
            results.append(False)
        if "if" in s:
            if await self.step(s["if"]):
                results.append(await self.sequence(s.get("then", [])))
            elif "else" in s:
                results.append(await self.sequence(s["else"]))
            else:
                results.append(True)
        if "any" in s:
            ok = False
            for sub in s["any"]:
                if await self.step(sub):
                    ok = True
                    break
            results.append(ok)

        if not results:
            return False
        res = all(results)
        return (not res) if s.get("negated") else res

    async def sequence(self, steps) -> bool:
        for s in steps:
            ok = await self.step(s)
            if not ok and not (isinstance(s, dict) and s.get("optional")):
                return False
        return True


def rule_matches_context(rule: dict, frame: Frame, is_main: bool, page_url: str) -> bool:
    rc = rule.get("runContext", {})
    if is_main and not rc.get("main", True):
        return False
    if not is_main and not rc.get("frame", False):
        return False
    rx = rule.get("_re")
    if rx is None:
        return True
    return bool(rx.search(page_url if is_main else frame.url))


async def quick_exists(frame: Frame, selectors: list[str]) -> list[bool]:
    """Viele einfache CSS-Selektoren in EINEM evaluate-Aufruf prüfen (Performance)."""
    return await frame.evaluate(
        """sels => sels.map(s => { try { return !!document.querySelector(s) } catch(e) { return false } })""",
        selectors,
    )


async def try_rules(page: Page, rules: RuleSet, max_wait_ms: int) -> RejectResult | None:
    frames = [(page.main_frame, True)] + [(f, False) for f in page.frames if f != page.main_frame]
    for frame, is_main in frames:
        candidates = [r for r in rules.rules if rule_matches_context(r, frame, is_main, page.url)]
        if not candidates:
            continue

        # Vorfilter: erster detectCmp-Schritt ist meist ein einfaches "exists" -> gebündelt prüfen
        simple_idx, simple_sels = [], []
        for i, r in enumerate(candidates):
            first = (r.get("detectCmp") or [{}])[0]
            sel = first.get("exists") if isinstance(first, dict) else None
            if isinstance(sel, str) and not sel.startswith(("xpath/", "aria/", "text/", "pierce/")):
                simple_idx.append(i)
                simple_sels.append(sel)
        try:
            hits = await quick_exists(frame, simple_sels) if simple_sels else []
        except Exception:
            continue  # Frame wurde währenddessen entfernt o. Ä.
        drop = {i for i, hit in zip(simple_idx, hits) if not hit}
        candidates = [r for i, r in enumerate(candidates) if i not in drop]

        for rule in candidates:
            # detectCmp und detectPopup: alle Schritte müssen zutreffen
            det = RuleEngine(frame, max_wait_ms, eval_default=True)
            if not await det.sequence(rule.get("detectCmp", [])):
                continue
            if not await det.sequence(rule.get("detectPopup", [])):
                continue
            eng = RuleEngine(frame, max_wait_ms)
            ok = await eng.sequence(rule["optOut"])
            res = RejectResult(
                status="rejected" if ok and eng.clicked else "click_failed",
                method="rule", rule_name=rule["name"],
                selector=" -> ".join(eng.clicked),
                frame_url="" if is_main else frame.url,
            )
            if ok:
                await asyncio.sleep(1.0)
                check = RuleEngine(frame, 1000, eval_default=True)
                try:
                    res.banner_gone = not await check.sequence(rule.get("detectPopup", []))
                except Exception:
                    res.banner_gone = True   # Frame weg = Banner weg
                return res
            # optOut fehlgeschlagen -> nächste Regel / nächste Stufe probieren
    return None


# ---------------------------------------------------------------------------
# Stufe 2: generische Selektoren
# ---------------------------------------------------------------------------
async def try_generic(page: Page) -> RejectResult | None:
    for frame in page.frames:
        for sel in GENERIC_REJECT_SELECTORS:
            try:
                loc = frame.locator(sel).first
                if await loc.count() and await loc.is_visible():
                    await loc.click(timeout=2000)
                    await asyncio.sleep(1.0)
                    gone = True
                    try:
                        gone = not await loc.is_visible()
                    except Exception:
                        pass
                    return RejectResult("rejected", "generic", "", sel,
                                        "" if frame == page.main_frame else frame.url, gone)
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# Stufe 3: Text-Matching (+ Erzeugung eines stabilen CSS-Selektors)
# ---------------------------------------------------------------------------
FIND_BY_TEXT_JS = r"""
(words) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const CLICKABLE = 'button, a, [role=button], input[type=button], input[type=submit], [tabindex]';

  // alle klickbaren Elemente sammeln, inkl. offener Shadow-Roots
  const collect = (root, out) => {
    root.querySelectorAll(CLICKABLE).forEach(e => out.push(e));
    root.querySelectorAll('*').forEach(e => { if (e.shadowRoot) collect(e.shadowRoot, out); });
    return out;
  };
  const isVisible = e => {
    const r = e.getBoundingClientRect(), st = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const unstable = s => /\d{4,}|[a-f0-9]{8,}/i.test(s);   // generierte IDs/Klassen meiden

  const cssPath = (el) => {
    const root = el.getRootNode();
    const uniq = s => { try { return root.querySelectorAll(s).length === 1 } catch (e) { return false } };
    if (el.id && !unstable(el.id) && uniq('#' + CSS.escape(el.id))) return '#' + CSS.escape(el.id);
    for (const a of ['data-testid', 'data-test', 'data-qa', 'data-cy', 'data-action', 'name', 'aria-label']) {
      const v = el.getAttribute(a);
      if (v && !unstable(v)) {
        const s = `${el.tagName.toLowerCase()}[${a}="${CSS.escape(v)}"]`;
        if (uniq(s)) return s;
      }
    }
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 7) {
      if (cur !== el && cur.id && !unstable(cur.id)) { parts.unshift('#' + CSS.escape(cur.id)); break; }
      let p = cur.tagName.toLowerCase();
      const cls = [...cur.classList].filter(c => !unstable(c)).slice(0, 2);
      if (cls.length) p += '.' + cls.map(c => CSS.escape(c)).join('.');
      const par = cur.parentElement;
      if (par) {
        const same = [...par.children].filter(c => c.tagName === cur.tagName);
        if (same.length > 1) p += `:nth-of-type(${same.indexOf(cur) + 1})`;
      }
      parts.unshift(p);
      if (uniq(parts.join(' > '))) break;
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  };

  // Kontext-Check: Button muss in einem Element stehen, das nach Cookie-Banner klingt.
  // Verhindert z. B. Treffer auf "Reject this pull request" auf GitHub.
  const CONTEXT = /cookie|consent|einwillig|zustimm|datenschutz|privacy|privatsphäre|partner|tracking|gdpr|dsgvo|rgpd|consentement|personal data|personenbezogen/i;
  const inBannerContext = el => {
    let cur = el;
    for (let d = 0; d < 8 && cur; d++) {
      const txt = (cur.innerText || '').slice(0, 3000);
      if (CONTEXT.test(txt) || CONTEXT.test(cur.id || '') || CONTEXT.test(String(cur.className || ''))) return true;
      cur = cur.parentElement || (cur.getRootNode && cur.getRootNode().host) || null;
    }
    return false;
  };

  const W = words.map(norm);
  let best = null;
  for (const el of collect(document, [])) {
    const t = norm(el.innerText || el.value || el.getAttribute('aria-label'));
    if (!t || t.length > 60 || !isVisible(el)) continue;
    for (let i = 0; i < W.length; i++) {
      // Score: exakt > beginnt mit > enthält; frühere Wörter = höhere Priorität.
      // Einzelwörter ("ablehnen", "reject") nur als exakter Treffer.
      const multi = W[i].includes(' ');
      let score = null;
      if (t === W[i]) score = 0;
      else if (multi && t.startsWith(W[i] + ' ')) score = 1000;
      else if (multi && t.includes(W[i])) score = 2000;
      if (score === null) continue;
      if (!inBannerContext(el)) break;
      score += i;
      if (!best || score < best.score) best = { el, score, text: t };
      break;
    }
  }
  if (!best) return null;
  document.querySelectorAll('[data-cr-target]').forEach(e => e.removeAttribute('data-cr-target'));
  best.el.setAttribute('data-cr-target', '1');   // Markierung für den echten Playwright-Klick
  return { selector: cssPath(best.el), text: best.text };
}
"""


async def try_text(page: Page) -> RejectResult | None:
    for frame in page.frames:
        try:
            hit = await frame.evaluate(FIND_BY_TEXT_JS, REJECT_WORDS)
        except Exception:
            continue
        if not hit:
            continue
        loc = frame.locator("[data-cr-target='1']").first
        try:
            await loc.click(timeout=2000)
        except Exception:
            try:
                await loc.evaluate("e => e.click()")
            except Exception as e:
                return RejectResult("click_failed", "text", "", hit["selector"],
                                    "" if frame == page.main_frame else frame.url, None, str(e)[:200],
                                    stage="reject:text")
        await asyncio.sleep(1.0)
        try:
            gone = not await loc.is_visible()
        except Exception:
            gone = True
        return RejectResult("rejected", "text", f'text="{hit["text"]}"', hit["selector"],
                            "" if frame == page.main_frame else frame.url, gone)
    return None


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------
async def reject_consent(page: Page, rules: RuleSet, max_wait_ms: int = 4000) -> RejectResult:
    """Versucht Stufe 1 -> 2 -> 3 und gibt das Ergebnis zurück."""
    stage = "rule"
    try:
        last = None
        for stage, run in (("rule", lambda: try_rules(page, rules, max_wait_ms)),
                           ("generic", lambda: try_generic(page)),
                           ("text", lambda: try_text(page))):
            res = await run()
            if res and res.status == "rejected":
                return res
            last = res or last
        return last or RejectResult()
    except Exception as e:
        return RejectResult(status="error", stage=f"reject:{stage}",
                            error=f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}")


# ---------------------------------------------------------------------------
# Crawler über die Tranco-Liste
# ---------------------------------------------------------------------------
def load_tranco(top: int, cache: Path) -> list[tuple[int, str]]:
    if not cache.exists():
        print(f"Lade Tranco-Liste von {TRANCO_URL} …")
        with urllib.request.urlopen(TRANCO_URL, timeout=60) as r:
            with zipfile.ZipFile(io.BytesIO(r.read())) as z:
                cache.write_bytes(z.read(z.namelist()[0]))
    rows = []
    with cache.open() as f:
        for rank, domain in csv.reader(f):
            rows.append((int(rank), domain.strip()))
            if len(rows) >= top:
                break
    return rows


CRUX_REPO = "https://raw.githubusercontent.com/zakird/crux-top-lists/main/data"
CRUX_API = "https://api.github.com/repos/zakird/crux-top-lists/contents/data/country"


def load_crux(country: str, month: str | None, top: int, seed: int, cache_dir: Path) -> list[tuple[int, str, int]]:
    """
    CrUX-Top-Liste (Ruth et al., IMC 2022) eines Landes laden.
    Rückgabe: [(lfd. Nr., Origin, CrUX-Rangstufe)].

    CrUX kennt nur Rangstufen (1k, 5k, 10k, …); innerhalb einer Stufe ist die Reihenfolge
    zufällig. Deshalb: Stufen von oben vollständig übernehmen, die letzte angebrochene Stufe
    mit festem Seed zufällig ziehen (reproduzierbar).
    Pro registrierbarer Domain (eTLD+1) wird nur ein Origin behalten, bevorzugt die
    Hauptseite (example.de / www.example.de) statt Subdomains wie dl.example.de.
    """
    import gzip
    import random
    import tldextract

    if month is None:   # neueste Monatsdatei im Repo ermitteln
        with urllib.request.urlopen(f"{CRUX_API}/{country}", timeout=60) as r:
            names = [e["name"] for e in json.load(r) if re.fullmatch(r"\d{6}\.csv\.gz", e["name"])]
        month = max(names)[:6]
    cache = cache_dir / f"crux_{country}_{month}.csv"
    if not cache.exists():
        url = f"{CRUX_REPO}/country/{country}/{month}.csv.gz"
        print(f"Lade CrUX-Liste von {url} …")
        with urllib.request.urlopen(url, timeout=120) as r:
            cache.write_bytes(gzip.decompress(r.read()))
    print(f"CrUX {country.upper()} {month}, Seed {seed}")

    buckets: dict[int, list[str]] = {}
    with cache.open() as f:
        for row in csv.DictReader(f):
            buckets.setdefault(int(row["rank"]), []).append(row["origin"])

    def site_key(origin: str) -> str:
        return tldextract.extract(origin).top_domain_under_public_suffix or urlparse(origin).hostname or origin

    def preference(origin: str) -> tuple:
        host = urlparse(origin).hostname or ""
        reg = site_key(origin)
        return (host not in (reg, f"www.{reg}"), not origin.startswith("https://"), origin)

    rng = random.Random(seed)
    seen: set[str] = set()
    picked: list[tuple[str, int]] = []
    for bucket in sorted(buckets):
        per_site: dict[str, str] = {}
        for origin in sorted(buckets[bucket], key=preference):
            key = site_key(origin)
            if key not in seen and key not in per_site:
                per_site[key] = origin
        seen.update(per_site)
        origins = sorted(per_site.values())
        need = top - len(picked)
        if len(origins) > need:
            origins = sorted(rng.sample(origins, need))
        picked += [(o, bucket) for o in origins]
        if len(picked) >= top:
            break
    return [(i + 1, o, b) for i, (o, b) in enumerate(picked)]


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def classify_error(msg: str) -> str:
    """Fehlertext -> kurze Kategorie für die Auswertung."""
    if m := re.search(r"net::(ERR_[A-Z0-9_]+)", msg):
        return m.group(1)
    if "interrupted by another navigation" in msg:
        return "NAV_INTERRUPTED"
    if "Timeout" in msg:
        return "TIMEOUT"
    if re.search(r"closed|detached", msg, re.I):
        return "PAGE_CLOSED"
    return "OTHER"


async def dns_resolves(host: str) -> bool:
    try:
        await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, 443), timeout=5)
        return True
    except Exception:
        return False


async def navigate(page: Page, domain: str, timeout_s: int) -> tuple[bool, int | None, str]:
    """Lädt erst https://domain, dann https://www.domain. Rückgabe: (geladen, HTTP-Status, Fehlertexte)."""
    urls = [domain] if domain.startswith("http") else [f"https://{domain}", f"https://www.{domain}"]
    errors = []
    for url in urls:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            return True, resp.status if resp else None, ""
        except Exception as e:
            msg = str(e).splitlines()[0][:150]
            if "interrupted by another navigation" in msg:
                # JS-/Meta-Weiterleitung: die Zielseite lädt trotzdem weiter -> abwarten
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=timeout_s * 1000)
                    if not page.url.startswith("about:"):
                        return True, None, ""
                except Exception as e2:
                    msg += " / " + str(e2).splitlines()[0][:100]
            errors.append(f"{url}: {msg}")
    return False, None, " | ".join(errors)


# Sperrseiten nur ERKENNEN (nicht umgehen), damit sie in der Auswertung nicht als "kein Banner" zählen
BLOCK_PATTERNS = [
    ("akamai", re.compile(r"errors\.edgesuite\.net|you don't have permission to access", re.I)),
    ("cloudflare", re.compile(r"just a moment\.\.\.|nur einen moment|attention required! \| cloudflare|"
                              r"checking your browser", re.I)),
    ("captcha", re.compile(r"captcha|are you a robot|verify you are human|bist du ein mensch|"
                           r"dass sie ein mensch sind", re.I)),
    ("generic", re.compile(r"access denied|request blocked|403 forbidden|zugriff verweigert|^\s*unknown error\s*$",
                           re.I | re.M)),
]


async def detect_block(page: Page, http_status: int | None) -> tuple[str, str]:
    """Rückgabe: (Sperrgrund oder "", Seitentitel)."""
    try:
        title = (await page.title()).strip()
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        return "", ""
    # Sperrseiten sind kurz; auf langen Seiten wäre z. B. "captcha" eher normaler Inhalt
    if len(text) < 3000:
        probe = title + "\n" + text[:2000]
        for name, rx in BLOCK_PATTERNS:
            if rx.search(probe):
                return name, title
    if http_status in (401, 403, 429):
        return f"http_{http_status}", title
    return "", title


async def screenshot(page: Page, path: Path) -> None:
    try:
        await page.screenshot(path=str(path), timeout=10000)
    except Exception as e:   # ein fehlender Screenshot soll das Ergebnis nicht verfälschen
        print(f"  Screenshot fehlgeschlagen ({path.name}): {str(e).splitlines()[0][:100]}")


def fail(row: dict, outcome: str, stage: str, error: str) -> dict:
    row.update(outcome=outcome, stage=stage, error_type=classify_error(error), error=error, status="error")
    return row


async def visit(browser: Browser, rank: int, domain: str, rules: RuleSet, args, attempt: int = 1) -> dict:
    t0 = time.monotonic()
    row = {"rank": rank, "domain": domain, "final_url": "", "http_status": "", "page_title": "",
           "outcome": "", "stage": "", "error_type": "", "block_reason": ""}
    stage = "dns"   # wird mitgeführt, damit bei Exceptions klar ist, wo sie entstanden
    ctx = None
    try:
        # Gesamt-Timeout pro Seite: verhindert, dass eine hängende Seite den ganzen Lauf blockiert
        async with asyncio.timeout(args.site_timeout):
            host = (urlparse(domain).hostname or domain) if domain.startswith("http") else domain
            if not args.skip_dns_check and not (await dns_resolves(host) or await dns_resolves(f"www.{host}")):
                row.update(outcome="unreachable", stage="dns", error_type="DNS_NOT_RESOLVED",
                           error=f"{host} und www.{host} lösen nicht auf", status="error")
                return row

            stage = "navigation"
            # Neuer Context pro Seite = sauberer Zustand (keine Cookies aus vorherigen Besuchen)
            ctx = await browser.new_context(locale="de-DE", viewport={"width": 1366, "height": 900})
            page = await ctx.new_page()
            loaded, http_status, nav_error = await navigate(page, domain, args.timeout)
            if not loaded:
                return fail(row, "unreachable", "navigation", nav_error)
            row["http_status"] = http_status or ""

            stage = "settle"
            await asyncio.sleep(args.settle)          # Banner werden oft verzögert nachgeladen
            row["final_url"] = page.url

            stage = "block_check"
            block_reason, title = await detect_block(page, http_status)
            row["block_reason"], row["page_title"] = block_reason, title[:100]

            if args.screenshots:
                await screenshot(page, args.out / "shots" / f"{rank:04d}_{safe(domain)}_a{attempt}_before.png")

            stage = "reject"
            res = await reject_consent(page, rules)
            if res.status == "no_banner_detected":   # zweiter Versuch für langsame CMPs
                await asyncio.sleep(args.settle)
                res = await reject_consent(page, rules)

            if args.screenshots:
                await screenshot(page, args.out / "shots" / f"{rank:04d}_{safe(domain)}_a{attempt}_after.png")
            row.update(asdict(res))
            if res.status == "error":
                row["outcome"], row["error_type"] = "error", classify_error(res.error)
            elif res.status == "no_banner_detected":
                # Sperrseite hat keinen Banner -> nicht als "Seite ohne Banner" zählen
                row["outcome"] = "blocked" if block_reason else "no_banner"
            else:
                row["outcome"] = res.status           # rejected | click_failed
    except TimeoutError:
        fail(row, "error", stage, f"SITE_TIMEOUT: Seite nach {args.site_timeout} s abgebrochen")
        row["error_type"] = "SITE_TIMEOUT"
    except Exception as e:
        msg = str(e).splitlines()[0][:200] if str(e) else ""
        fail(row, "error", stage, f"{type(e).__name__}: {msg}")
    finally:
        row["seconds"] = round(time.monotonic() - t0, 1)
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass
    return row


# Niedriger = aussagekräftiger. Bei Wiederholungen wird das beste Ergebnis behalten.
OUTCOME_PRIORITY = {"rejected": 0, "click_failed": 1, "no_banner": 2, "blocked": 3, "error": 4, "unreachable": 5}


def needs_retry(row: dict) -> bool:
    if row["outcome"] == "rejected":
        return False
    # DNS-Fehler ändern sich durch Wiederholen nicht
    return not (row["outcome"] == "unreachable" and row["stage"] == "dns")


def write_outputs(out: Path, final: dict[int, dict]) -> None:
    results = [final[r] for r in sorted(final)]
    cols = ["rank", "domain", "crux_bucket", "final_url", "http_status", "page_title", "outcome", "first_outcome",
            "attempts", "stage", "error_type", "block_reason", "status", "method", "rule_name", "selector",
            "frame_url", "banner_gone", "error", "seconds"]
    with (out / "results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    discovered = {r["domain"]: {k: r.get(k) for k in ("selector", "frame_url", "method", "rule_name", "banner_gone")}
                  for r in results if r.get("status") == "rejected"}
    (out / "discovered_selectors.json").write_text(json.dumps(discovered, indent=2, ensure_ascii=False))


async def main(args) -> None:
    args.out.mkdir(parents=True, exist_ok=True)
    if args.screenshots:
        (args.out / "shots").mkdir(exist_ok=True)

    if args.domains:
        sites = [(i + 1, d.strip(), "") for i, d in enumerate(Path(args.domains).read_text().split()) if d.strip()]
    elif args.source == "crux":
        sites = load_crux(args.country, args.crux_month, args.top, args.seed, args.out)
    else:
        sites = [(r, d, "") for r, d in load_tranco(args.top, args.out / "tranco.csv")]
    bucket_of = {d: b for _, d, b in sites}
    rules = RuleSet.load(args.rules)
    print(f"{len(sites)} Domains, {len(rules.rules)} Regeln, Parallelität {args.concurrency}, "
          f"Wiederholungen {args.retries}")

    sem = asyncio.Semaphore(args.concurrency)   # begrenzt gleichzeitige Seiten
    final: dict[int, dict] = {}                 # rank -> bestes Ergebnis über alle Versuche

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed)

        async def worker(rank, domain, attempt, total, done):
            async with sem:
                row = await visit(browser, rank, domain, rules, args, attempt)
            row["crux_bucket"], row["attempts"] = bucket_of.get(domain, ""), attempt
            prev = final.get(rank)
            row["first_outcome"] = prev["first_outcome"] if prev else row["outcome"]
            # Bei Wiederholung das aussagekräftigere Ergebnis behalten (z. B. no_banner statt Timeout)
            if prev is None or OUTCOME_PRIORITY[row["outcome"]] < OUTCOME_PRIORITY[prev["outcome"]]:
                final[rank] = row
            else:
                prev["attempts"] = attempt
            done.append(rank)
            detail = (f"{row['stage']}/{row['error_type']}" if row["outcome"] in ("error", "unreachable")
                      else row.get("block_reason") or row.get("selector", "")[:70])
            print(f"[{len(done):>4}/{total}] {'' if attempt == 1 else f'(Versuch {attempt}) '}"
                  f"{domain:<30} {row['outcome']:<12} {row.get('method', ''):<8} {detail}")
            if len(done) % 100 == 0:           # Zwischenstand sichern, falls der Lauf abbricht
                write_outputs(args.out, final)

        todo = [(r, d) for r, d, _ in sites]
        for attempt in range(1, args.retries + 2):
            if attempt > 1:
                todo = [(r, d) for r, d, _ in sites if needs_retry(final[r])]
                if not todo:
                    break
                print(f"\n--- Wiederholung {attempt - 1}: {len(todo)} Domains, Pause {args.retry_delay} s ---")
                await asyncio.sleep(args.retry_delay)
            done: list[int] = []
            await asyncio.gather(*(worker(r, d, attempt, len(todo), done) for r, d in todo))
            write_outputs(args.out, final)
        await browser.close()

    results = [final[r] for r in sorted(final)]
    from collections import Counter
    print("\nErgebnis:", dict(Counter(r["outcome"] for r in results)))
    print("Methode:", dict(Counter(r.get("method") for r in results if r["outcome"] == "rejected")))
    print("Gesperrt:", dict(Counter(r["block_reason"] for r in results if r["outcome"] == "blocked")))
    print("Fehlerquelle:", dict(Counter(f"{r['stage']}/{r['error_type']}" for r in results
                                        if r["outcome"] in ("error", "unreachable")).most_common()))
    print("Durch Wiederholung geändert:", dict(Counter(f"{r['first_outcome']} -> {r['outcome']}" for r in results
                                                       if r["first_outcome"] != r["outcome"])))
    print(f"-> {args.out/'results.csv'}  und  {args.out/'discovered_selectors.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Cookie-Banner ablehnen & Reject-Selektoren sammeln")
    ap.add_argument("--source", choices=["crux", "tranco"], default="crux", help="Top-Liste")
    ap.add_argument("--top", type=int, default=2000, help="Anzahl Domains aus der Top-Liste")
    ap.add_argument("--country", default="de", help="CrUX-Land (ISO-Code, z. B. de)")
    ap.add_argument("--crux-month", help="CrUX-Monat JJJJMM (Standard: neuester)")
    ap.add_argument("--seed", type=int, default=42, help="Seed für die Zufallsauswahl in der CrUX-Rangstufe")
    ap.add_argument("--retries", type=int, default=1, help="Wiederholungsrunden für nicht abgelehnte Domains")
    ap.add_argument("--retry-delay", type=float, default=60, help="Pause vor jeder Wiederholungsrunde in s")
    ap.add_argument("--domains", help="Alternativ: Textdatei mit einer Domain pro Zeile")
    ap.add_argument("--rules", default=str(Path(__file__).with_name("reject_rules.json")))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=30, help="Navigations-Timeout in s")
    ap.add_argument("--site-timeout", type=float, default=120, help="Maximale Gesamtzeit pro Seite in s")
    ap.add_argument("--settle", type=float, default=3.0, help="Wartezeit nach dem Laden in s")
    ap.add_argument("--headed", action="store_true", help="Browser sichtbar starten")
    ap.add_argument("--screenshots", action="store_true", help="Vorher/Nachher-Screenshots")
    ap.add_argument("--skip-dns-check", action="store_true", help="DNS-Vorprüfung auslassen")
    ap.add_argument("--out", type=Path, default=Path("results"))
    asyncio.run(main(ap.parse_args()))
