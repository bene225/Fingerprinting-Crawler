import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

USER_AGENT = "Research für Bachelor Arbeit(Uni Regensburg). Kontakt: benedikt.hartl@stud.uni-regensburg.de"
# Nur den hinteren Teil des Links behalten, da Wayback schreibt um (Tracking) original_url
WAYBACK_URL = re.compile(r"^https?://web\.archive\.org/web/\d+[a-z_]*/(.+)$")
# Aufnahmezeitpunkt (14 Ziffern) der ausgelieferten Kopie in der Archiv-Adresse
WAYBACK_TIMESTAMP = re.compile(r"^https?://web\.archive\.org/web/(\d{14})[a-z_]*/")

# Für Snapshot suche -> Tage Abstand
def _distance_days(timestamp : str, target_date : datetime) -> int:
    return abs((datetime.strptime(timestamp[:8], "%Y%m%d") - target_date).days)

# Snapshots innerhalb der Bedingingen wählen und nicht doppelt, bekommt Array von nearest_sn
def choose_capture(response_list : list[dict], target_dates : list[str], max_days_gap : int) -> list[dict]:
    # Für jeden Stichtag nächstes Datum
    captures = []
    already_selected_timestamps = set()
    if not response_list:
        return []
    for single_target_date in target_dates:
        target_date_formatted = datetime.strptime(single_target_date, "%Y%m%d")
        # Nächsten Zeitpunkt finden
        best_snapshot = min(response_list, key=lambda row: _distance_days(row["timestamp"], target_date_formatted))
        # Für Lücke
        if _distance_days(best_snapshot["timestamp"], target_date_formatted) > max_days_gap:
            print(f"Kein Snapshot gefunden: Abstand max:{max_days_gap}Tage von: {single_target_date}")
            continue
        # Einmalige Snapshots -> nur für ein Stichtag mit selben timestamps
        if best_snapshot["timestamp"] in already_selected_timestamps:
            continue
        already_selected_timestamps.add(best_snapshot["timestamp"])
        captures.append({**best_snapshot, "stichtag": single_target_date})
    return captures


# Weiterleitung nicht folgen, nur das Ziel (Header Location) lesen
class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

_replay_opener = build_opener(_NoRedirect)


# Naechste Kopie zu einem Datum: Die Replay-Adresse web.archive.org/web/<Datum>/<Seite> leitet direkt auf sie weiter (schnell, ohne CDX)
# None = nie archiviert (oder gesperrt), Fehler = Wayback nicht erreichbar
# Ruft nicht auf, sondern Wayback nichts hat verweist es auf nächste Kopie. Header wird dann wieterverwendt (kein CDX mehr)
# Link zu nächstem Datum
def nearest_capture(site : str, target_date : str) -> dict | None:
    request = Request(f"https://web.archive.org/web/{target_date}/{site}", method="HEAD", headers={"User-Agent" : USER_AGENT})
    for _ in range(2):
        try:
            _replay_opener.open(request, timeout=20)
            # Statt weiterleiten fFehler werfen und neue Loc auslesen
        except HTTPError as error:
            location = urljoin(request.full_url, error.headers.get("Location") or "")
            if error.code in (301, 302, 307, 308) and capture_timestamp(location):
                return {"timestamp" : capture_timestamp(location), "original" : original_url(location)}
            if error.code in (403, 404, 410, 451):
                return None
            # 429: sofort aufgeben, der Aufrufer pausiert (nach 429 weiterfragen kann zu einer IP-Sperre fuehren)
            if error.code == 429:
                break
        except Exception:
            pass
        time.sleep(5) # Zeitueberschreitung oder 5xx: einmal nochmal
    raise RuntimeError(f"Wayback nicht erreichbar: {site} {target_date}")


# Snapshots einer Website zu den Stichtagen (Abstand höchstens max_days_gap). None = Wayback nicht erreichbar
# Verknüopfen choose und find und parallelisierung
def find_captures(site : str, target_dates : list[str], max_days_gap : int) -> list[dict] | None:
    try:
        # Drei Abfragen gleichzeitig (Archiv schonen)
        with ThreadPoolExecutor(max_workers=3) as pool:
            nearest = list(pool.map(lambda target_date: nearest_capture(site, target_date), target_dates))
    except RuntimeError as e:
        print(e)
        return None
    # Je Stichtag die nächste Kopie, zu weit entfernte und doppelte fallen weg
    return choose_capture([capture for capture in nearest if capture], target_dates, max_days_gap)


# Testabfrage an WB Sperre?
def archive_reachable() -> bool:
    try:
        nearest_capture("https://example.com", "20200101")
        return True
    except RuntimeError:
        return False

# Link für die messende Abfrage
def build_wayback_url(capture : dict) -> str:
    # Normale Replay-URL (ohne id_)
    return f"https://web.archive.org/web/{capture['timestamp']}/{capture['original']}"


def original_url(wayback_url : str) -> str | None:
    # .../web/20160101002715js_/https://tracker.com/x.js -> https://tracker.com/x.js
    # None falls nichts archiviert
    match = WAYBACK_URL.match(wayback_url)
    return match.group(1) if match else None


def capture_timestamp(wayback_url : str) -> str | None:
    # .../web/20191223122052js_/https://tracker.com/x.js -> 20191223122052 (wann das Archiv diese Kopie aufgenommen hat)
    match = WAYBACK_TIMESTAMP.match(wayback_url)
    return match.group(1) if match else None


def capture_gap_days(copy_timestamp : str, snapshot_timestamp : str) -> int:
    # Ganze Tage, positiv = Kopie neuer als der Snapshot, negativ = älter
    return (datetime.strptime(copy_timestamp[:8], "%Y%m%d") - datetime.strptime(snapshot_timestamp[:8], "%Y%m%d")).days

