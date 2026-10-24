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
    # FF3
    consent_action : Literal["accept", "reject", "none"] = "accept" # FF3: zustimmen, ablehnen oder Banner nicht anfassen (FF1/FF2: zustimmen)
    consent_window : PositiveInt | None = None # FF3: feste Zeit fuer Bannersuche + Klick, Messung nach Consent dadurch in allen Modi gleich spaet. None = direkt weiter (FF1/FF2)
    headless : bool = False # Headful besser für rendern von Website und user_agent
    loading_time : PositiveInt = 10 # Zeit nach dem Laden bis zur Messung vor Consent (Wayback: bis zur Messung)
    visit_time_after_consent : PositiveInt = 10 # Verweildauer 
    site_timeout : PositiveInt = 50 # Warten bis abbruch
    load_timeout : PositiveInt = 30 # Max Ladezeit
    
    # Tranco-Liste (path_to_webpages): aus jedem Rangbereich gleich viele zufaellige Websites (logarithmische Bereiche: Spitze bis Breite)
    rank_bands : tuple[PositiveInt, ...] = (1000, 10000, 100000, 1000000) # Obergrenzen der Bereiche (1-1000, 1001-10000, ...)
    batch_size : PositiveInt = 500 # Websites insgesamt. Später erhoehen = nur die weiteren kommen dazu, fertige werden übersprungen
    batch_seed : int = 1 # Zufalls-Startwert: gleicher Wert = gleiche Seiten (Fortsetzen), neuer Wert = neue Seiten
    # FF1 historisch
    target_dates : tuple[str, ...] = ("20160101", "20200101", "20240101", "20261005") # Stichtage JJJJMMTT, Ende = heute eintragen
    max_days_gap : PositiveInt = 60 # Max. Abstand Snapshot zu Stichtag
    wayback_pause : PositiveInt = 6 # Wayback schonen
    wayback_load_timeout : PositiveInt = 60 # Max. Zeit bis die Seite (HTML) da ist
    wayback_max_wait : PositiveInt = 45 # Archiv: nach dem Laden hoechstens so lange auf spaet startende Skripte warten (mindestens loading_time). Endet frueher, wenn nichts mehr kommt
    archive_rate : PositiveFloat = 2.5 # Hoechstens so viele Anfragen pro Sekunde an Wayback (alle Seiten zusammen), sonst Drosselung/Sperre
    archive_light : bool = True # Bilder, Schriften, Videos aus dem Archiv nicht laden (ca. 2/3 weniger Anfragen). WG Sperrung
    parallel_snapshots : PositiveInt = 5 # Snapshots EINER Website gleichzeitig (Archiv). Bei vielen Fehlerzeilen mit HTTP 429 verringern
    load_check_timeout : PositiveInt = 15 # Vorab-Pruefung, ob die Website live laedt (Sekunden). Laedt sie nicht, kein Archiv-Crawl
    