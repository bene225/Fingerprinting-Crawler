from config import CrawlConfig
from dataclasses import asdict
from json import dumps

def write_config(config : CrawlConfig):
        config_asdict = asdict(config)
        with open(config.path_to_output, "a", encoding="utf-8") as out_file:
            out_file.write(dumps(config_asdict, default=str ) + "\n")
        