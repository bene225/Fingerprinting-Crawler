from config import CrawlConfig
from dataclasses import asdict
from json import dumps, loads, JSONDecodeError
from pathlib import Path

def write_config(config : CrawlConfig) -> None:
        config_asdict = asdict(config)
        with open(config.path_to_output, "a", encoding="utf-8") as out_file:
            out_file.write(dumps(config_asdict, default=str ) + "\n")
        
def write_website(id : int, website : str, config : CrawlConfig, events : list) -> None:
    events_asdict = [asdict(event) for event in events]
    crawl_result = {"id" : id, "website" : website, "events" : events_asdict}
    with open(config.path_to_output, "a", encoding="utf-8") as out_file:
                out_file.write(dumps(crawl_result, default=str ) + "\n")
                
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