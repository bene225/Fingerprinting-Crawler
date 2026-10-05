from  pydantic.dataclasses import dataclass
from pydantic import FilePath, PositiveInt
from pathlib import Path
from typing import Literal


# Definineren des Objekt Config (Nötig für Stuerung des Crawlers.)  WERTE IN main.py MANIPULIEREN.
@dataclass
class CrawlConfig:
    path_to_output : Path 
    path_to_webpages: FilePath
    crawl_name : str = "default_browser_behavior"
    BrowserType : Literal["chromium"] = "chromium" 
    allow_3p : bool = False 
    consent : bool = False
    headless : bool = False 
    concurrent_sessions : PositiveInt = 1 # TODO Parallelität noch implementieren
    loading_time : PositiveInt = 4 
    site_timeout : PositiveInt = 50 
    # FF1 historisch
    target_dates : tuple[str, ...] = ("20160101", "20200101", "20240101", "20261005") # Stichtage JJJJMMTT, Edne = heute eintragen
    max_days_gap : PositiveInt = 60 # Max. Abstand Snapshot zu Stichtag
    wayback_pause : PositiveInt = 10 # Pause nach Abfrage (Block)
    
    # Weitere Überlegungen user_agent, visit_time_after_consent, autom_restart, consent_polling+consent_tries (schon implentiert aber config schöner)
    
    
    
    
    