"""route.fetch enfernt Cookke header nicht. Test 2 Mal Website aufrufen und Cookie Speicher verlgiechen
    uv run python tests/cookie_block_probe.py
"""

import asyncio
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import Request, Route, async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.origin_domain import origin_domain

URL = "http://127.0.0.1:8770/"
# 1p Domain
MAIN_SITE = "meine-seite.de"
# 3P Domain
URL_3P = "http://127.0.0.1:8770/seite"


class SetCookieServer(BaseHTTPRequestHandler):
    # Terminal freihalten
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        if self.path == "/seite":
            self.end_headers()
            self.wfile.write(b'<html><iframe src="http://localhost:8770/"></iframe></html>')
            return
        # fremden cookie im iframe setzen
        self.send_header("Set-Cookie", "tracker_id=abc123; Path=/; SameSite=None; Secure")
        self.end_headers()
        self.wfile.write(b"<html>ok</html>")


# Kopie aus core/browser_controller.py
async def _block_thirdparty_cookies(route : Route, request : Request, main_site : str):
    requested_site = origin_domain(request.url)
    first_party = requested_site == main_site
    if first_party:
        await route.continue_()
        return
    request_headers = dict(request.headers)
    request_headers.pop("cookie", None)
    response = await route.fetch(headers=request_headers)
    response_header = dict(response.headers)
    response_header.pop("set-cookie", None)
    await route.fulfill(response=response, headers=response_header)


async def visit(browser, url : str, block : bool = False, cdp : bool = False) -> list[str]:
    context = await browser.new_context()
    if block:
        await context.route("**/*", lambda route, request: _block_thirdparty_cookies(route, request, MAIN_SITE))
    page = await context.new_page()
    if cdp:
        # Chromium cookie block an
        session = await context.new_cdp_session(page)
        await session.send("Network.enable")
        await session.send("Network.setCookieControls", {"enableThirdPartyCookieRestriction": True})
    await page.goto(url)
    cookies = [c["name"] for c in await context.cookies()]
    await context.close()
    return cookies


async def main():
    # Threading: Chrome oeffnet Verbindungen auf Vorrat, die einen einfachen HTTPServer blockieren
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8770), SetCookieServer).serve_forever, daemon=True).start()
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # Test 1: Set-Cookie-Header per route.fetch entfernen
        cookies_an = await visit(browser, URL)
        cookies_aus = await visit(browser, URL, block=True)
        print(f"Ohne Block:           {cookies_an}")
        print(f"Mit Header-Entfernen: {cookies_aus}")

        # Test 2: Browser-Flag beim Start
        browser_flag = await p.chromium.launch(args=["--test-third-party-cookie-phaseout"])
        print(f"\n3P ohne Block:        {await visit(browser, URL_3P)}")
        print(f"3P mit Flag:          {await visit(browser_flag, URL_3P)}")
        await browser_flag.close()

        # Test 3: DevTools-Protokoll (CDP), Entwickler-Schnittstelle von Chromium
        print(f"3P mit CDP:           {await visit(browser, URL_3P, cdp=True)}")

        await browser.close()
    


if __name__ == "__main__":
    asyncio.run(main())
