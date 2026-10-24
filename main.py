import argparse
from typing import Any

from core.historical import crawl_historical
from config import CrawlConfig
from core.live import crawl, crawl_block
from core.consent_crawl import crawl_consent
from pathlib import Path
from utils.crawl_utils import run_with_restart
from utils.tranco_worker import read_sites_tranco


if __name__ == "__main__":
    # Genau ein Lauf pro Terminal: "uv run python main.py --live" bzw. "--hist" (zwei Terminals = beide gleichzeitig)
    parser = argparse.ArgumentParser(description="Crawl starten")
    run = parser.add_mutually_exclusive_group(required=True)
    run.add_argument("--live", action="store_true", help="FF1 Live-Crawl (vor und nach Consent)")
    run.add_argument("--hist", action="store_true", help="FF1 Archiv-Crawl (Wayback)")
    run.add_argument("--block", action="store_true", help="FF2 Cookie-Block: alles erlaubt / nur CDP / alles geblockt (je vor und nach Consent)")
    run.add_argument("--consent", action="store_true", help="FF3 Consent: keine Aktion / zustimmen / ablehnen (Cookies wie FF2 alles erlaubt)")
    args = parser.parse_args()

    # Tranco-Liste: gleich viele Websites aus jedem logarithmischen Rangbereich (rank_bands in der Config). Gleiche Werte fuer Live und Archiv
    # batch_size spaeter erhoehen: es kommen nur die weiteren Websites dazu, fertige werden beim Fortsetzen uebersprungen
    webpages = Path("utils/tranco_647LX.csv")
    batch : dict[str, Any] = dict(batch_size= 1000, batch_seed= 1)

    # FF1 Live-Punkt: vor und nach Consent gemessen, nichts blocken
    live_config = CrawlConfig(
        path_to_output=Path("results/Forschungsfrage 1/ff1_live.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff1",
        allow_3p= True,
        consent= True,
        consent_tries= 4, # 2 s: das Banner ist nach der Ladezeit (10 s) schon da
        headless= False,
        loading_time= 10,
        visit_time_after_consent= 10,
        site_timeout= 90,
        js_cookie_block= False,
        **batch
    )
    # FF1 Snapshots: gleiche Messung (Monkeypatch, Consent), Stichtage alle 2 Jahre + Brueckenpunkt
    hist_config = CrawlConfig(
        path_to_output=Path("results/Forschungsfrage 1/ff1_hist.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff1",
        allow_3p= True,
        consent= True,
        consent_tries= 4,
        headless= False,
        loading_time= 10,
        visit_time_after_consent= 10,
        site_timeout= 240, # Wayback laedt langsamer als live: HTML bis 90 s + Warten auf Skripte bis wayback_max_wait (zweimal) + Screenshots
        wayback_load_timeout= 90,
        wayback_max_wait= 45, # Hoechstens so lange nach dem Laden auf spaet startende Skripte warten (endet frueher, wenn nichts mehr kommt)
        wayback_pause= 2, # Pause nach jedem Snapshot. Die Rate begrenzt archive_rate, mehr Pause bringt kaum Schonung
        archive_rate= 2.5, # Anfragen pro Sekunde an Wayback (alle gleichzeitigen Seiten zusammen). Sinkt nach jeder Drosselung um 30 %
        archive_light= True, # Bilder, Schriften, Videos im Archiv nicht laden (Anfrage zaehlt trotzdem mit). False = alles laden
        parallel_snapshots= 3,
        max_days_gap= 120,
        # 1. Januar alle 2 Jahre. Letzter = Brueckenpunkt: Tag des Live-Crawls eintragen
        target_dates= ("20160101", "20180101", "20200101", "20220101", "20240101", "20261009"),
        **batch
    )

    # FF2 Cookie-Block: gleiche Messung wie FF1 live, je Modus eigene Datei ff2_<modus>.jsonl (allow_3p/js_cookie_block setzt BLOCK_MODES in core/live.py)
    block_config = CrawlConfig(
        path_to_output=Path("results/Forschungsfrage 2/ff2.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff2",
        consent= True,
        consent_tries= 4,
        headless= False,
        loading_time= 10,
        visit_time_after_consent= 10,
        site_timeout= 90,
        **batch
    )

    # FF3 Consent: Zeitwerte wie FF2, Cookies wie FF2 alles_erlaubt. Je Modus eigene Datei ff3_<modus>.jsonl (core/consent_crawl.py)
    consent_config = CrawlConfig(
        path_to_output=Path("results/Forschungsfrage 3/ff3.jsonl"),
        path_to_webpages=webpages,
        crawl_name= "ff3",
        allow_3p= True,
        js_cookie_block= False,
        consent= True,
        consent_tries= 4,
        consent_window= 20, # Bannersuche + Klick in fester Zeit: Messung nach Consent in allen drei Modi gleich spaet
        headless= False,
        loading_time= 10,
        visit_time_after_consent= 10,
        site_timeout= 120, # 90 wie FF2 + Zeitfenster
        **batch
    )
    # Restliche Args in der Config


    sites = read_sites_tranco(live_config)
    if args.live:
        run_with_restart(crawl, live_config, sites)
    elif args.hist:
        run_with_restart(crawl_historical, hist_config, sites)
    elif args.block:
        run_with_restart(crawl_block, block_config, sites)
    else:
        run_with_restart(crawl_consent, consent_config, sites)
