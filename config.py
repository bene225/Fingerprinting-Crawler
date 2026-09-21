from  pydantic.dataclasses import dataclass
from pydantic import FilePath, PositiveInt
from typing import Literal

@dataclass
class CrawlConfig:
    path_to_output : FilePath
    path_to_webpages: FilePath
    crawl_name : str = "default_browser_behavior"
    BrowserType = Literal["chromium", "firefox"]
    allow_3p : bool = True
    consent : bool = False
    headless : bool = False
    concurrent_session : PositiveInt = 1 # TODO Parallelität noch implementieren
    loading_time = PositiveInt = 4 # TODO Wert noch in Funktion in Consent auslesen
    site_timeout : PositiveInt = 50 # TODO In Code einführen
    
    # Weitere Überlegungen user_agent, visit_time_after_consent, autom_restart, consent_polling+consent_tries (schon implentiert aber config schöner)
    
    
    
    
    