from config import CrawlConfig


import csv
import random
from itertools import islice, zip_longest


def read_sites_tranco(config : CrawlConfig) -> list[str]:
    # Tranco (rank,domain ohne Kopfzeile) in logarithmische Rangbereiche teilen (1-1000, 1001-10000, ...), aus jedem gleich viele Seiten
    with open(config.path_to_webpages, encoding="utf-8") as in_file:
        domains = [row[1] for row in islice(csv.reader(in_file), config.rank_bands[-1])]
    bands = []
    lower = 0
    for upper in config.rank_bands:
        band = domains[lower:upper]
        # Feste Zufallsreihenfolge pro Bereich (gleicher Startwert = gleiche Seiten): mehr Seiten = es kommen nur weitere dazu
        random.Random(f"{config.batch_seed}-{upper}").shuffle(band)
        bands.append(band)
        lower = upper
    # Reihum je eine Seite pro Bereich: auch ein vorzeitiger Abbruch hat alle Bereiche gleich stark
    sites = [domain for one_round in zip_longest(*bands) for domain in one_round if domain]
    return [f"https://{domain}" for domain in sites[:config.batch_size]]