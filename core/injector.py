from playwright.async_api import Page

# Datenübergabe, TODO fertigstellen
class DetectedFingerprint:
    
    def __init__(self, type : str, method : str, url : str ) -> None:
        self.type = type
        self.method = method
        self.url = url
        

# https://playwright.dev/python/docs/api/class-browsercontext
class Injector:
    def __init__(self) -> None:
        self.events : list[DetectedFingerprint] = []
    
    async def integrade_monkeypatch(self):
        await Page.expose_binding("register_fp", _append_event)
        
    # TODO implementiere _append_event