# Eigener Test zu den Grenzen der Zuordnung: Chromium speichert im Stacktrace standardmaessig nur die letzten zehn Funktionen.
# Folge fuer core/monkeypatch.js: Fehlt das fremde Skript im Stacktrace, zaehlt sein Aufruf als First-Party.
# Zwei Test-Websites: a.test (besuchte Website) und b.test (Drittanbieter), Playwright beantwortet die Anfragen selbst.
# b.test ruft canvas.toDataURL ueber n Funktionen von a.test auf oder startet Code, dessen Stacktrace keine Adresse hat.
# Kontrolle: dieselben Aufrufe mit hoeherer Grenze (Error.stackTraceLimit = 50).
# Aufruf im Crawler-Ordner:  uv run python tests/stacktrace_test.py
import asyncio
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Browser, Route

MONKEYPATCH = Path(__file__).resolve().parent.parent / "core" / "monkeypatch.js"
CONTROL_LIMIT = 50

PAGES = {
    ("a.test", "/"): ("text/html", """<html><body>
<script src="/website.js"></script>
<script src="http://b.test/tracker.js"></script></body></html>"""),
    # Skript der Website: n verschachtelte Funktionen, die innerste liest ein Canvas aus
    ("a.test", "/website.js"): ("application/javascript", """
function website(n) { return n > 1 ? website(n - 1) : document.createElement("canvas").toDataURL(); }
// Gleiche Kette, die innerste Funktion gibt den Stacktrace zurueck
function website_stack(n) { return n > 1 ? website_stack(n - 1) : new Error().stack; }"""),
    # Skript des Drittanbieters
    ("b.test", "/tracker.js"): ("application/javascript", """
// Ruft die Funktionen der Website auf
function tracker(n) { website(n); }
// Code als Text an setTimeout: laeuft spaeter, Stacktrace ohne Adresse
function tracker_timer_text() { setTimeout('document.createElement("canvas").toDataURL()', 0); }
// Fuegt ein Inline-Skript ein, dessen Funktion spaeter per Timer laeuft: Stacktrace ohne Adresse
function tracker_inline_script() {
  const script = document.createElement("script");
  script.textContent = 'setTimeout(function fp() { document.createElement("canvas").toDataURL(); }, 0);';
  document.head.appendChild(script);
}"""),
}

# Aufrufketten: Beschriftung -> Aufruf im Browser, jeweils genau ein Aufruf von canvas.toDataURL
CASES = {f"b.test -> {n} Funktion{'en' if n > 1 else ''} von a.test -> toDataURL": f"tracker({n})" for n in range(1, 11)}
CASES["b.test -> Code als Text an setTimeout -> toDataURL"] = "tracker_timer_text()"
CASES["b.test -> eingefuegtes Inline-Skript, Timer -> toDataURL"] = "tracker_inline_script()"

# Playwright beantwortet die Anfragen an a.test und b.test selbst (kein Server)
async def serve(route: Route) -> None:
    url = urlparse(route.request.url)
    content_type, body = PAGES.get((url.hostname, url.path), ("text/plain", ""))
    await route.fulfill(content_type=content_type, body=body)

# Zuordnung, wie sie der Crawler speichert. Ereignis von register_fp: api, method, url, third_party, script_url
def attribution(new_events: list[tuple]) -> str:
    if len(new_events) != 1:
        return f"{len(new_events)} Aufrufe erfasst"
    _, _, _, third_party, script_url = new_events[0]
    return f"Third-Party ({script_url})" if third_party is True else "First-Party"

# Tabelle mit ausgerichteten Spalten, erste Zeile = Kopf
def print_table(title: str, table: list[tuple[str, ...]]) -> None:
    widths = [max(len(row[i]) for row in table) for i in range(len(table[0]))]
    print(f"\n{title}\n")
    for i, row in enumerate(table):
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))
        if i == 0:
            print("  ".join("-" * width for width in widths))

# Ein Durchlauf: Grenze, Funktionen im Stacktrace nach 50 verschachtelten Aufrufen, Zuordnung je Aufrufkette
async def run(browser: Browser, limit: int | None) -> tuple[int, int, list[str]]:
    events = []
    context = await browser.new_context()
    await context.route("**/*", serve)
    page = await context.new_page()
    # Wie Injector.integrade_url_to_js + integrade_monkeypatch
    await page.add_init_script('window._location_url = "a.test";\n')
    await page.expose_binding("register_fp", lambda source, *args: events.append(args))
    await page.add_init_script(MONKEYPATCH.read_text(encoding="utf-8"))
    if limit:
        await page.add_init_script(f"Error.stackTraceLimit = {limit};")
    await page.goto("http://a.test/")
    stack_limit = await page.evaluate("Error.stackTraceLimit")
    frames = await page.evaluate("website_stack(50).split('\\n').filter((line) => line.trim().startsWith('at ')).length")
    attributions = []
    for code in CASES.values():
        before = len(events)
        await page.evaluate(code)
        # register_fp meldet asynchron an Python, die Timer laufen erst nach evaluate
        await page.wait_for_timeout(500)
        attributions.append(attribution(events[before:]))
    await context.close()
    return stack_limit, frames, attributions

async def main() -> None:
    async with async_playwright() as p:
        # Headful wie im Crawl (main.py)
        browser = await p.chromium.launch(headless=False)
        limit, frames, standard = await run(browser, None)
        control_limit, control_frames, control = await run(browser, CONTROL_LIMIT)
        version = browser.version
        await browser.close()
    print(f"\nStacktrace-Test mit Chromium {version}\n")
    print(f"Error.stackTraceLimit: {limit} (Kontrolle: {control_limit})")
    print(f"Funktionen im Stacktrace nach 50 verschachtelten Aufrufen: {frames} (Kontrolle: {control_frames})")
    table = [("Aufrufkette", f"Grenze {limit} (Standard)", f"Grenze {control_limit} (Kontrolle)"), *zip(CASES, standard, control)]
    print_table("Zuordnung durch den Crawler, besuchte Website a.test", table)
    print("\nDie ersten zwei Plaetze im Stacktrace belegen register_fp und der Wrapper (Init-Skript, ohne Adresse)")

if __name__ == "__main__":
    asyncio.run(main())
