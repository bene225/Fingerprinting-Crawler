import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from playwright.async_api import async_playwright

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            print("Header der Anfrage:")
            for k in ("User-Agent", "Accept-Language"):
                print(f"  {k}: {self.headers.get(k)}")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html></html>")
    

async def main():
    srv = HTTPServer(("127.0.0.1", 8765), H)
    Thread(target=srv.serve_forever, daemon=True).start()
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)  # wie im Crawler
        page = await (await b.new_context()).new_page()
        await page.goto("http://127.0.0.1:8765/")
        await b.close()
    srv.shutdown()

asyncio.run(main())