import json
import time
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

cdx_adress = "http://web.archive.org/cdx/search/cdx?"

def get_wayback_request (url : str, start : int, end: int) -> Request:
    # Collapse: Nicht genauer als Day, fl: Antwort
    cdx_request = urlencode([("url", url),("from", str(start)),("to", str(end)),("output", "json"),("filter", "statuscode:200"),("filter", "mimetype:text/html"),("collapse", "timestamp:8"),("fl", "timestamp,original,digest")])
    wayback_request = Request(cdx_adress+cdx_request, headers={"User-Agent" : "Research für Bachelor Arbeit(Uni Regensburg). Kontakt: benedikt.hart@stud.uni-regensburg.de"})
    return wayback_request


def get_wayback_location(wayback_request : Request) -> list[dict]:
    time.sleep(3) # merhmalige Ausführung bei der Api (Last)
    for i in range(4):
        print(f"Try:{i}")
        try:
            with urlopen(wayback_request, timeout=70) as response:
                response_string = json.loads(response.read().decode())
                break
        except Exception:
            time.sleep(4*i)
    else: return []
       
    # Verarbeiten
    try:
        header = response_string[0]
        body = response_string[1:]
        response_array = []
        for row in body:
            row_dict = {header[0] : row [0], header[1] : row [1], header[2] : row [2]}
            response_array.append(row_dict)  
        print(response_array)
        return response_array
    except IndexError:
        print("Liste nicht da")
        return []
    except json.JSONDecodeError:
        print("Format Json")
        return []
    

def _distance_days(timestamp : str, target_date : datetime) -> int:
    return abs((datetime.strptime(timestamp[:8], "%Y%m%d") - target_date).days)


def choose_capture(response_list : list[dict], target_dates : list[str], max_days_gap : int) -> list[dict]:
    # Sortieren nach Datum 
    response_sorted = sorted(response_list, key=lambda ts: ts["timestamp"])

    # Für jeden Stichtag nächstes Datum
    captures = []
    already_selected_timestamps = set()
    if not response_sorted:
        return []
    for single_target_date in target_dates:
        target_date_formatted = datetime.strptime(single_target_date, "%Y%m%d")
        # Nächsten Zeitpunkt finden
        best_snapshot = min(response_sorted, key=lambda row: _distance_days(row["timestamp"], target_date_formatted))
        # Für Lücke
        if _distance_days(best_snapshot["timestamp"], target_date_formatted) > max_days_gap:
            print(f"Kein Snapshot gefunden: Abstand max:{max_days_gap}Tage von: {single_target_date}")
            continue
        # Einmalige Snapshots -> nur für ein Stichtag mit sel timestamps
        if best_snapshot["timestamp"] in already_selected_timestamps:
            continue
        already_selected_timestamps.add(best_snapshot["timestamp"])
        captures.append({**best_snapshot, "stichtag": single_target_date})
    return captures


def build_wayback_url(capture : dict) -> str:
    # Normale Replay-URL (ohne id_), damit der Browser die archivierten Skripte nachlaedt
    return f"https://web.archive.org/web/{capture['timestamp']}/{capture['original']}"


# Test
if __name__ == "__main__":
    request = get_wayback_request("spiegel.de", 20150101, 20261231)
    response = get_wayback_location(request)
    for capture in choose_capture(response, ["20160101", "20180101", "20200101", "20220101", "20240101", "20260101"], 60):
        print(capture["stichtag"], build_wayback_url(capture))
    