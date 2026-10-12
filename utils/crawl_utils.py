# Balken + Restzeit fuer die Konsole. processed = in diesem Lauf bearbeitete Websites (beim Fortsetzen uebersprungene zaehlen nicht)
import time


def progress_line(position : int, total : int, start : float, processed : int) -> str:
    elapsed = time.time() - start
    remaining = elapsed / processed * (total - position) if processed else 0
    filled = 20 * position // total
    return f"[{'#' * filled}{'-' * (20 - filled)}] {position}/{total} ({100 * position // total} %) | {elapsed / 3600:.1f} h gelaufen, noch ca. {remaining / 3600:.1f} h"