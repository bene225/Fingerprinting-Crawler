import playwright.async_api as async_api

# Datenübergabe, TODO fertigstellen
class DetectedFingerprint:
    
    def __init__(self, type : str, method : str, url : str ) -> None:
        self.type = type
        self.method = method
        self.url = url
        

    