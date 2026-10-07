from  pydantic.dataclasses import dataclass
from pydantic import FilePath, PositiveInt, PositiveFloat
from pathlib import Path
from typing import Literal


# Definineren des Objekts Config (Nötig für Steuerung des Crawlers.)  WERTE IN main.py MANIPULIEREN.
@dataclass
class CrawlConfig:
    path_to_output : Path 
    path_to_webpages: FilePath
    crawl_name : str = "default_browser_behavior" 
    BrowserType : Literal["chromium"] = "chromium" 
    allow_3p : bool = False # 3P Cookies CDP Block
    js_cookie_block : bool = False # True = Cookies über Skripte böockieren JS
    consent : bool = False # Zustimmen
    consent_tries : PositiveInt = 20 # Wie oft nach dem Banner gesucht wird
    consent_polling : PositiveFloat = 0.5 # Sekunden Pause zwischen den Versuchen
    headless : bool = False # Headful besser für rendern von Website und user_agent
    loading_time : PositiveInt = 10 # Zeit nach dem Laden bis zur Messung vor Consent (Wayback: bis zur Messung)
    visit_time_after_consent : PositiveInt = 10 # Verweildauer 
    site_timeout : PositiveInt = 50 # Warten bis abbruch
    load_timeout : PositiveInt = 30 # Max Ladezeit
    
    # FF1 historisch
    target_dates : tuple[str, ...] = ("20160101", "20200101", "20240101", "20261005") # Stichtage JJJJMMTT, Ende = heute eintragen
    max_days_gap : PositiveInt = 60 # Max. Abstand Snapshot zu Stichtag
    wayback_pause : PositiveInt = 6 # Wayback schonen
    wayback_load_timeout : PositiveInt = 60 
    # Weitere Überlegungen user_agent, autom_restart
    
    
    
    
    