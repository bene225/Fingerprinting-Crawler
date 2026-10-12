# Balken + Restzeit fuer die Konsole. processed = in diesem Lauf bearbeitete Websites (beim Fortsetzen uebersprungene zaehlen nicht)
import time

from utils.origin_domain import origin_domain
from utils.wayback import original_url


def progress_line(position : int, total : int, start : float, processed : int) -> str:
    elapsed = time.time() - start
    remaining = elapsed / processed * (total - position) if processed else 0
    filled = 20 * position // total
    return f"[{'#' * filled}{'-' * (20 - filled)}] {position}/{total} ({100 * position // total} %) | {elapsed / 3600:.1f} h gelaufen, noch ca. {remaining / 3600:.1f} h"


# # Endgültige Adresse nach allen Weiterleitungen. Landet die Seite auf einer anderen Domain, zählen deren eigene Skripte als 3P -> cross_domain_redirect markiert das zum Filtern
def landing_fields(page_url : str, requested_url : str) -> dict:
    final_url = original_url(page_url) or page_url # Wayback-Praefix entfernen
    return {"final_url": final_url, "cross_domain_redirect": origin_domain(final_url) != origin_domain(requested_url)}