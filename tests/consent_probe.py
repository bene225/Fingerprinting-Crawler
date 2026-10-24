import asyncio
import html
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # consent.py liest utils/tcf_terms.json relativ zum Projektverzeichnis

# --------------------------------------------------------------- Bausteine der Testseiten
CLICK = "top.postMessage('clicked','*')"
LISTENER = ("<script>window.__clicked=false;"
            "addEventListener('message',e=>{if(e.data==='clicked')window.__clicked=true})</script>")


def button(text: str, cls: str = "", ident: str = "") -> str:
    return f'<button class="{cls}" id="{ident}" onclick="{CLICK}">{text}</button>'


def iframe(inner_html: str) -> str:
    return f'<iframe srcdoc="{html.escape(inner_html, quote=True)}" width="400" height="120"></iframe>'


def late_iframe(inner_html: str, delay_ms: int) -> str:
    return ("<script>setTimeout(()=>{const f=document.createElement('iframe');"
            f"f.srcdoc={json.dumps(inner_html)};document.body.appendChild(f)}},{delay_ms})</script>")


SHADOW = ("<div id=host></div><script>const s=document.getElementById('host').attachShadow({mode:'open'});"
          f"s.innerHTML={json.dumps(button('Alle akzeptieren'))};</script>")

# (Name, Body-HTML, erwartete Rueckgabe, Beschreibung)
CASES = [
    ("hauptdokument_css",   button("Alles klar", ident="onetrust-accept-btn-handler"), True,
     "Banner im Hauptdokument, Treffer ueber CSS-Selektor"),
    ("hauptdokument_wort",  button("Alle akzeptieren"), True,
     "Banner im Hauptdokument, Treffer ueber Wortliste"),
    ("shadow_dom",          SHADOW, True,
     "Button in offenem Shadow-DOM (Wortliste)"),
    ("iframe_css",          iframe(button("Zustimmen", cls="sp_choice_type_11")), True,
     "Sourcepoint-Stil im Iframe, CSS-Selektor"),
    ("iframe_wort",         iframe(button("Alle akzeptieren")), True,
     "Banner im Iframe, Wortliste"),
    ("verschachtelt",       iframe(iframe(button("Alle akzeptieren"))), True,
     "Iframe in Iframe"),
    ("iframe_spaet_5s",     late_iframe(button("Alle akzeptieren"), 5000), True,
     "OPTIONAL: Iframe taucht erst nach 5 s auf (Warten/Wiederholen)"),
    ("nicht_akzeptieren",   button("Nicht akzeptieren"), False,
     "Button mit Negation darf NICHT geklickt werden"),
    ("nur_notwendige",      button("Nur notwendige akzeptieren"), False,
     "Teil-Zustimmung ('nur ...') darf bei Akzeptieren-Alle NICHT geklickt werden"),
    ("kein_banner",         "<p>Hallo Welt</p>", False,
     "Kein Banner: False und kein Absturz"),
    ("fremder_button_iframe", iframe(button("Jetzt kaufen")), False,
     "Unpassender Button im Iframe darf NICHT geklickt werden"),
]

# --------------------------------------------------------------------------- offline
async def run_offline(func_name: str) -> int:
    func = getattr(importlib.import_module("core.consent"), func_name)
    fails = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for name, body, expected, desc in CASES:
            page = await browser.new_page()
            try:
                await page.set_content(LISTENER + body)
                try:
                    result = await func(page)
                    error = ""
                except Exception as e:  # ein Absturz ist selbst ein Testergebnis
                    result, error = None, f"{type(e).__name__}: {str(e)[:70]}"
                await asyncio.sleep(0.3)
                clicked = await page.evaluate("window.__clicked === true")
                ok = (result == expected) and (clicked == expected) and not error
                fails += 0 if ok else 1
                print(f"[{'OK  ' if ok else 'FEHL'}] {name:24s} Rueckgabe={result!s:5s} geklickt={clicked!s:5s} "
                      f"erwartet={expected!s:5s} | {desc} {error}", flush=True)
            finally:
                await page.close()
        await browser.close()
    print(f"\n{len(CASES) - fails}/{len(CASES)} Testfaelle bestanden")
    return fails


# ------------------------------------------------------------------------------ live
SITES = ["bbc.com", "spiegel.de", "zeit.de", "bild.de", "heise.de", "theguardian.com",
         "otto.de", "mediamarkt.de", "obi.de", "t-online.de", "web.de", "ebay.de"]
CMP_HINT = re.compile(r"consent|cmp|sp_message|privacy|sourcepoint|didomi|onetrust|usercentrics|cookiebot", re.I)


def cmp_frames(page) -> list[str]:
    return [f.url[:60] for f in page.frames if not f.is_detached() and CMP_HINT.search(f.url)]


async def run_live(func_name: str) -> None:
    func = getattr(importlib.import_module("core.consent"), func_name)
    out = Path(tempfile.mkdtemp(prefix="consent_probe_"))
    sem = asyncio.Semaphore(4)
    results: dict[str, object] = {}

    async def one(browser, site):
        async with sem:
            ctx = await browser.new_context(locale="de-DE", viewport={"width": 1300, "height": 800})
            page = await ctx.new_page()
            try:
                await page.goto(f"https://www.{site}/", wait_until="load", timeout=25000)
                await asyncio.sleep(4)
                before = cmp_frames(page)
                result = await func(page)
                await asyncio.sleep(2)
                after = cmp_frames(page)
                await page.screenshot(path=str(out / f"{site}.png"))
                results[site] = result
                print(f"{site:18s} Rueckgabe={result!s:5s} CMP-Frames vorher={len(before)} nachher={len(after)}", flush=True)
            except Exception as e:
                results[site] = None
                print(f"{site:18s} FEHLER {type(e).__name__}: {str(e)[:60]}", flush=True)
            finally:
                await ctx.close()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        await asyncio.gather(*(asyncio.wait_for(one(browser, s), 150) for s in SITES), return_exceptions=True)
        await browser.close()
    print(f"\nTrue auf {sum(1 for v in results.values() if v is True)} von {len(SITES)} Seiten")
    print(f"Screenshots (nachher): {out}")
    print("Hinweis: 'CMP-Frames nachher' sinkt nicht zwingend - manche Banner werden nur versteckt. "
          "Der Screenshot entscheidet.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "offline"
    func_name = sys.argv[2] if len(sys.argv) > 2 else "try_accept"
    if mode == "offline":
        sys.exit(1 if asyncio.run(run_offline(func_name)) else 0)
    asyncio.run(run_live(func_name))
