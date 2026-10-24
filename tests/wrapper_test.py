# Eigener Test zu den Grenzen der Messung: Die Wrapper sind fuer eine Website erkennbar.
# Ein Skript der Website fragt mit Function.prototype.toString den Quelltext ueberwachter Funktionen ab,
# einmal ohne und einmal mit Crawler (register_fp, _location_url, core/monkeypatch.js wie im Crawl).
# Ohne Crawler: nur Hinweis auf eingebauten Browser-Code ([native code]). Mit Crawler: Quelltext des Wrappers.
# Aufruf im Crawler-Ordner:  uv run python tests/wrapper_test.py
import asyncio, textwrap
from pathlib import Path
from playwright.async_api import async_playwright, Browser

MONKEYPATCH = Path(__file__).resolve().parent.parent / "core" / "monkeypatch.js"

# Je eine ueberwachte Funktion pro Art von Wrapper in monkeypatch.js, Quelltext abgefragt wie von einer Website
JS = """() => {
  const getter = (proto, property) => Object.getOwnPropertyDescriptor(proto, property).get;
  const functions = {
    "HTMLCanvasElement.toDataURL": HTMLCanvasElement.prototype.toDataURL,
    "CanvasRenderingContext2D.getImageData": CanvasRenderingContext2D.prototype.getImageData,
    "Storage.getItem": Storage.prototype.getItem,
    "WebGLRenderingContext.getParameter": WebGLRenderingContext.prototype.getParameter,
    "AudioBuffer.getChannelData": AudioBuffer.prototype.getChannelData,
    "OfflineAudioContext (Konstruktor)": OfflineAudioContext,
    "Intl.DateTimeFormat.resolvedOptions": Intl.DateTimeFormat.prototype.resolvedOptions,
    "Navigator.userAgent (Getter)": getter(Navigator.prototype, "userAgent"),
  };
  return Object.entries(functions).map(([name, f]) => [name, Function.prototype.toString.call(f)]);
}"""

# Quelltext je Funktion, ohne oder mit Crawler
async def sources(browser: Browser, crawler: bool) -> list[tuple[str, str]]:
    context = await browser.new_context()
    page = await context.new_page()
    if crawler:
        # Wie Injector.integrade_url_to_js + integrade_monkeypatch
        await page.add_init_script('window._location_url = "a.test";\n')
        await page.expose_binding("register_fp", lambda source, *args: None)
        await page.add_init_script(MONKEYPATCH.read_text(encoding="utf-8"))
    # Leere Seite von a.test, Playwright beantwortet die Anfrage selbst (kein Server)
    await page.route("**/*", lambda route: route.fulfill(content_type="text/html", body="<html><body></body></html>"))
    await page.goto("http://a.test/")
    result = [(name, source) for name, source in await page.evaluate(JS)]
    await context.close()
    return result

# Quelltext fuer die Ausgabe: Folgezeilen ohne die Einrueckung aus monkeypatch.js, unter der ersten Zeile
def show(source: str) -> str:
    first, _, rest = source.partition("\n")
    return first + ("\n" + textwrap.indent(textwrap.dedent(rest), " " * 16) if rest else "")

async def main() -> None:
    async with async_playwright() as p:
        # Headful wie im Crawl (main.py)
        browser = await p.chromium.launch(headless=False)
        without_crawler = await sources(browser, crawler=False)
        with_crawler = await sources(browser, crawler=True)
        version = browser.version
        await browser.close()
    print(f"\nWrapper-Test mit Chromium {version}")
    print("Quelltext, den eine Website mit Function.prototype.toString erhaelt (Einrueckung fuer die Ausgabe angepasst)\n")
    for (name, original), (_, wrapper) in zip(without_crawler, with_crawler):
        print(name)
        print(f"  ohne Crawler: {show(original)}")
        print(f"  mit Crawler:  {show(wrapper)}\n")
    native = lambda results: sum("[native code]" in source for _, source in results)
    print(f"Mit Hinweis auf eingebauten Browser-Code ([native code]): ohne Crawler {native(without_crawler)} von {len(without_crawler)}, "
          f"mit Crawler {native(with_crawler)} von {len(with_crawler)}")

if __name__ == "__main__":
    asyncio.run(main())
