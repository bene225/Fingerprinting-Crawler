# Eigener Test zu den Grenzen der Messung: Ein Init-Skript von Playwright laeuft nicht in einem Web Worker.
# Dasselbe Skript fp.js fragt die Zeitzone ab (Intl.DateTimeFormat().resolvedOptions(), vom Crawler ueberwacht),
# einmal in der Seite und einmal in je einem Dedicated, Shared und Service Worker.
# Crawler eingebunden wie im Crawl (register_fp, _location_url, core/monkeypatch.js). Dazu ein Init-Skript nur fuer
# den Test: Es setzt eine Markierung und liefe auch in einem Worker fehlerfrei (globalThis statt window).
# Aufruf im Crawler-Ordner:  uv run python tests/worker_test.py
import asyncio, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from playwright.async_api import async_playwright

MONKEYPATCH = Path(__file__).resolve().parent.parent / "core" / "monkeypatch.js"
# Lokaler Server auf 127.0.0.1: gilt als sicherer Kontext, sonst gibt es keinen Service Worker
PORT = 8444

PAGES = {
    # Laeuft in der Seite und in den Workern
    "/fp.js": ("application/javascript", """
function measure() {
  return {
    init_script: globalThis.init_script_ran === true,
    wrapper: !Function.prototype.toString.call(Intl.DateTimeFormat.prototype.resolvedOptions).includes("[native code]"),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  };
}
// Im Worker: Ergebnis per Nachricht an die Seite, beim Shared Worker ueber dessen Port
if (typeof window === "undefined") {
  onmessage = (e) => (e.source || self).postMessage(measure());
  onconnect = (e) => e.ports[0].postMessage(measure());
}"""),
    # Seite: startet fp.js im gewaehlten Kontext und liefert das Ergebnis
    "/": ("text/html", """<html><body><script src="/fp.js"></script><script>
async function measure_in(kind) {
  if (kind === "Seite") return measure();
  if (kind === "Dedicated Worker") {
    const worker = new Worker("/fp.js");
    return new Promise((resolve) => { worker.onmessage = (e) => resolve(e.data); worker.postMessage("start"); });
  }
  if (kind === "Shared Worker") {
    const worker = new SharedWorker("/fp.js");
    return new Promise((resolve) => { worker.port.onmessage = (e) => resolve(e.data); });
  }
  await navigator.serviceWorker.register("/fp.js");
  const registration = await navigator.serviceWorker.ready;
  return new Promise((resolve) => { navigator.serviceWorker.onmessage = (e) => resolve(e.data); registration.active.postMessage("start"); });
}
</script></body></html>"""),
}
CONTEXTS = ["Seite", "Dedicated Worker", "Shared Worker", "Service Worker"]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        content_type, body = PAGES.get(self.path, ("text/plain", ""))
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode())
    def log_message(self, format, *args):
        pass

def yes_no(value: bool) -> str:
    return "ja" if value else "nein"

# Tabelle mit ausgerichteten Spalten, erste Zeile = Kopf
def print_table(title: str, table: list[tuple[str, ...]]) -> None:
    widths = [max(len(row[i]) for row in table) for i in range(len(table[0]))]
    print(f"\n{title}\n")
    for i, row in enumerate(table):
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))
        if i == 0:
            print("  ".join("-" * width for width in widths))

async def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Aufrufe, die register_fp an Python meldet (wie Injector.events)
    events = []
    table = [("Kontext", "Init-Skript gelaufen", "Wrapper aktiv", "Zeitzone", "Erfasste Aufrufe")]
    async with async_playwright() as p:
        # Headful wie im Crawl (main.py)
        browser = await p.chromium.launch(headless=False)
        page = await (await browser.new_context()).new_page()
        await page.add_init_script("globalThis.init_script_ran = true;")
        # Wie Injector.integrade_url_to_js + integrade_monkeypatch
        await page.add_init_script('window._location_url = "127.0.0.1";\n')
        await page.expose_binding("register_fp", lambda source, *args: events.append(args))
        await page.add_init_script(MONKEYPATCH.read_text(encoding="utf-8"))
        await page.goto(f"http://127.0.0.1:{PORT}/")
        for kind in CONTEXTS:
            before = len(events)
            result = await page.evaluate("kind => measure_in(kind)", kind)
            # register_fp meldet asynchron an Python
            await page.wait_for_timeout(500)
            table.append((kind, yes_no(result["init_script"]), yes_no(result["wrapper"]), result["timezone"], str(len(events) - before)))
        version = browser.version
        await browser.close()
    server.shutdown()
    print_table(f"Init-Skript im Web Worker mit Chromium {version}", table)
    print("\nJe Kontext genau ein Aufruf von resolvedOptions. Erfasst = von register_fp an Python gemeldet")

if __name__ == "__main__":
    asyncio.run(main())
