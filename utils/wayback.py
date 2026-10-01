import json
import time
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
    

def choose_capture(response_list : list[dict], k : int) -> list[dict]:
    # Doppleter Digest weg + sortieren
    response_uniqe = {row["digest"] : row for row in response_list}.values()
    response_sorted = sorted(response_uniqe, key=lambda ts: ts["timestamp"])
    
    # TODO Zeitpunkte für Snapshots wählen
    

# Test
if __name__ == "__main__":
    request = get_wayback_request("wikipedia.org", 20260101, 20261231)
    response = get_wayback_location(request)
    print(choose_capture(response, 3))
    print (response)
    