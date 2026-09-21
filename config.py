from  pydantic.dataclasses import dataclass
from pydantic import FilePath, PositiveInt
from typing import Literal
@dataclass
class CrawlConfig:
    path_to_output : FilePath
    path_to_webpages: FilePath
    crawl_name : str = "default_browser_behavior"
    allow_3p : bool = True
    consent : bool = False
    headless : bool = False
    concurrent_session : PositiveInt = 1 # TODO Parallelität noch implementieren
    loading_time = PositiveInt = 4 # TODO Wert noch in Funktion in Consent auslesen
    site_timeout : PositiveInt = 50
    
    
    