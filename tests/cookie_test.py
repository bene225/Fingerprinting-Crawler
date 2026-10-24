# Eigener Test zu Abschnitt "Erfassung und Blockade von Cookies" (Anhang anh:Cookie-Test).
# Prueft, welche Cookies die drei Bedingungen der Cookie-Blockade sperren.
# Zwei Test-Websites laufen lokal: a.test (besuchte Website) und b.test (Drittanbieter).
# Aufruf im Crawler-Ordner:  uv run python tests/cookies_test.py [chrome]
#   ohne Argument: Chromium von Playwright, mit "chrome": installiertes Google Chrome
# Braucht openssl fuer ein selbst signiertes Zertifikat (SameSite=None verlangt HTTPS).
import asyncio, os, ssl, subprocess, sys, tempfile, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from playwright.async_api import async_playwright

JS_COOKIE_BLOCK = Path(__file__).resolve().parent.parent / "core" / "js_cookie_block.js"
PORT = 8443
B = f"https://b.test:{PORT}"

PAGES = {
    ("a.test", "/"): ("text/html", [], f"""<html><body>
<script>document.cookie="fp_js=1; path=/";</script>
<script src="{B}/tp.js"></script>
<img src="{B}/pixel">
<iframe src="{B}/frame"></iframe></body></html>"""),
    # Skript des Drittanbieters, laeuft im Kontext der besuchten Website
    ("b.test", "/tp.js"): ("application/javascript", [],
        'document.cookie="tp_script_in_1p=1; path=/";'
        'if (window.cookieStore) cookieStore.set("tp_cookiestore_in_1p", "1");'),
    # Antwort des Drittanbieters mit Cookies im HTTP-Header (normal und partitioniert)
    ("b.test", "/pixel"): ("image/gif", ["tp_http=1; SameSite=None; Secure; Path=/",
                                         "tp_http_chips=1; SameSite=None; Secure; Path=/; Partitioned"], ""),
    # Iframe des Drittanbieters setzt Cookie per JavaScript und testet localStorage
    ("b.test", "/frame"): ("text/html", [],
        '<script>document.cookie="tp_js_in_iframe=1; SameSite=None; Secure; path=/";'
        'let r; try { localStorage.setItem("x", "1"); r = "erlaubt" } catch (e) { r = "gesperrt" }'
        'console.log("IFRAME_LOCALSTORAGE " + r)</script>'),
}

# Spalten der Ausgabe
CONDITIONS = {1: "ohne CDP", 2: "CDP", 3: "CDP + JS"}
# Zeilen der Ausgabe: erwartete Cookies mit Herkunft
COOKIES = {
    "fp_js": "1P-Skript, document.cookie",
    "tp_script_in_1p": "3P-Skript in 1P-Seite, document.cookie",
    "tp_cookiestore_in_1p": "3P-Skript in 1P-Seite, cookieStore",
    "tp_http": "3P-HTTP-Header",
    "tp_http_chips": "3P-HTTP-Header, Partitioned",
    "tp_js_in_iframe": "3P-Iframe, document.cookie",
}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers["Host"].split(":")[0]
        content_type, set_cookies, body = PAGES.get((host, self.path), ("text/plain", [], ""))
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        for cookie in set_cookies:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body.encode())
    def log_message(self, format, *args):
        pass

def start_server(tmp: str) -> None:
    cert, key = os.path.join(tmp, "c.pem"), os.path.join(tmp, "k.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
                    "-days", "1", "-subj", "/CN=a.test", "-addext", "subjectAltName=DNS:a.test,DNS:b.test"],
                   check=True, capture_output=True)
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

# Ein Durchlauf pro Bedingung: Browserversion und {Cookie-Name: Ergebnis}
async def run(condition: int, channel: str | None) -> tuple[str, dict[str, str]]:
    results = {"localStorage": "keine Meldung"}
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel=channel, args=[f"--host-resolver-rules=MAP *.test 127.0.0.1"])
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        page.on("console", lambda m: results.update(localStorage=m.text.split()[-1]) if "IFRAME_LOCALSTORAGE" in m.text else None)
        if condition >= 2:
            # Wie BrowserController.new_page. Aeltere Versionen verlangen alle drei Parameter
            cdp = await context.new_cdp_session(page)
            await cdp.send("Network.enable")
            try:
                await cdp.send("Network.setCookieControls", {"enableThirdPartyCookieRestriction": True})
            except Exception:
                await cdp.send("Network.setCookieControls", {"enableThirdPartyCookieRestriction": True,
                               "disableThirdPartyCookieMetadata": False, "disableThirdPartyCookieHeuristics": False})
        if condition >= 3:
            # Wie Injector.integrade_url_to_js + integrade_js_cookie_block
            await page.add_init_script('window._location_url = "a.test";\n')
            await page.add_init_script(JS_COOKIE_BLOCK.read_text(encoding="utf-8"))
        await page.goto(f"https://a.test:{PORT}/")
        await page.wait_for_timeout(2000)
        for cookie in await context.cookies():
            results[cookie.get("name", "")] = "gesetzt*" if cookie.get("partitionKey") else "gesetzt"
        version = browser.version
        await browser.close()
    return version, results

# Tabelle: Zeile = Cookie, Spalte = Bedingung. Fehlt ein Cookie, wurde er blockiert
def print_table(browser_name: str, results: dict[int, dict[str, str]]) -> None:
    unexpected = sorted({name for result in results.values() for name in result} - COOKIES.keys() - {"localStorage"})
    rows = [*COOKIES.items(), *((name, "unerwartet") for name in unexpected), ("localStorage", "3P-Iframe, localStorage")]
    table = [("Cookie", "Herkunft", *CONDITIONS.values())]
    table += [(name, origin, *(results[condition].get(name, "blockiert") for condition in CONDITIONS)) for name, origin in rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(table[0]))]
    print(f"\nCookie-Test mit {browser_name}\n")
    for i, row in enumerate(table):
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))
        if i == 0:
            print("  ".join("-" * width for width in widths))
    print("\n* partitioniert (CHIPS, partitionKey gesetzt)")

if __name__ == "__main__":
    channel = sys.argv[1] if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as tmp:
        start_server(tmp)
        runs = {condition: asyncio.run(run(condition, channel)) for condition in CONDITIONS}
    version = runs[1][0]
    print_table(f"{'Google Chrome' if channel == 'chrome' else 'Chromium'} {version}",
                {condition: result for condition, (_, result) in runs.items()})
