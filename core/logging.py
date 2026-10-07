from config import CrawlConfig
from dataclasses import asdict
from datetime import datetime
from json import dumps, loads, JSONDecodeError
from pathlib import Path
from playwright.async_api import Page
import re

# Anfang des Crawlers -> Einstellungen werden an den Anfang von Results geschrieben
def write_config(config : CrawlConfig) -> None:
        config_asdict = asdict(config)
        with open(config.path_to_output, "a", encoding="utf-8") as out_file:
            out_file.write(dumps(config_asdict, default=str ) + "\n")
        
# Schreibt die Ergebnisse von collect_stats in das JSONL
def write_website(id : int, website : str, config : CrawlConfig, events : list, stats_vor_consent : dict, stats_nach_consent : dict | None, internet_ok : bool) -> None:
    # Umformung Dataclass -> dict
    events_asdict = [asdict(event) for event in events]
    # events (groß) ans Ende, damit die Zeile vorne lesbar bleibt
    crawl_result = {"id" : id, "website" : website, "success" : True, "internet_ok" : internet_ok, "stats_vor_consent" : stats_vor_consent, "stats_nach_consent" : stats_nach_consent, "events" : events_asdict}
    with open(config.path_to_output, "a", encoding="utf-8") as out_file:
                out_file.write(dumps(crawl_result, default=str ) + "\n")

# Fehlgeschlagene Website (oder Snapshot) mitschreiben, um sie gezielt nochmal zu crawlen
def write_error(id : int, website : str, config : CrawlConfig, error : str, internet_ok : bool, stichtag : str | None = None) -> None:
    error_result = {"id" : id, "website" : website, "success" : False, "internet_ok" : internet_ok, "error" : error}
    if stichtag is not None:
        error_result["stichtag"] = stichtag
    with open(config.path_to_output, "a", encoding="utf-8") as out_file:
                out_file.write(dumps(error_result, default=str ) + "\n")

# Screenshot zum Pruefen von Hand (Bot-Sperren, Fehlerseiten). Ordner = crawl_name neben der Ausgabe
# Rueckgabe: Dateiname fuer die JSONL-Zeile, None falls fehlgeschlagen
async def write_screenshot(page : Page, config : CrawlConfig) -> str | None:
    folder = Path(config.path_to_output).parent / config.crawl_name
    folder.mkdir(parents=True, exist_ok=True)
    # Zeitpunkt + URL ohne Sonderzeichen (/ und : gehen nicht in Dateinamen)
    file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{re.sub(r'[^A-Za-z0-9.-]+', '_', page.url)[:100]}.jpg"
    try:
        # Nur sichtbarer Bereich als JPEG -> klein
        await page.screenshot(path=folder / file_name, type="jpeg", quality=60, timeout=10000)
    except Exception as e:
        # Screenshot ist nur Hilfe, ein Fehler soll die Messung nicht verwerfen
        print(f"Screenshot fehlgeschlagen: {e!r}")
        return None
    return file_name

# Stichtag ohne passenden Snapshot: gueltiges Ergebnis, kein Fehler -> bei Resume nicht nochmal CDX fragen
def write_no_snapshot(id : int, website : str, config : CrawlConfig, stichtag : str, internet_ok : bool) -> None:
    no_snapshot_result = {"id" : id, "website" : website, "success" : True, "internet_ok" : internet_ok, "stichtag" : stichtag, "no_snapshot" : True}
    with open(config.path_to_output, "a", encoding="utf-8") as out_file:
                out_file.write(dumps(no_snapshot_result, default=str ) + "\n")

# wichtig für resume: erledigte (Website, Stichtag), Stichtag None bei Live
# Nur success UND internet_ok zaehlt, alles andere wird nochmal gemacht
def done_crawls(config : CrawlConfig) -> set[tuple[str, str | None]]:
    done = set()
    if not Path(config.path_to_output).exists():
        return done
    with open(config.path_to_output, "r", encoding="utf-8") as in_file:
        for line in in_file:
            line = line.strip()
            if not line:
                continue
            try:
                line_dict = loads(line)
            except JSONDecodeError:
                continue
            # Config-Zeile hat kein success
            if line_dict.get("success") and line_dict.get("internet_ok"):
                # Stichtag steht bei Snapshots in den stats, bei no_snapshot direkt in der Zeile
                stichtag = line_dict.get("stichtag") or (line_dict.get("stats_vor_consent") or {}).get("stichtag")
                done.add((line_dict["website"], stichtag))
    return done

def resume_crawl(config : CrawlConfig) -> int:
    # Muss man resume?
    if not Path(config.path_to_output).exists():
        return 0
    
    with open(config.path_to_output, "r", encoding="utf-8") as in_file:
        # datei da aber leer
        last_id = -1
        for line in in_file:
            line =  line.strip()
            
            # eof aber \n
            if not line:
                continue
            try:
                line_dict = loads(line)
                last_id = line_dict.get("id", last_id)
            except JSONDecodeError:
                continue
        return last_id + 1