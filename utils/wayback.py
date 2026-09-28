from urllib.parse import urlencode

cdx_adress = "http://web.archive.org/cdx/search/cdx?"

def build_cdx_request (url : str, start, end):
    # Collapse: Nicht genauer als Day, fl: Antwort
    cdx_request = urlencode({"url" : url, "from" : start, "to" : end, "output" : "json", "filter" : "statuscode:200", "filter" : "mimetype:text/html", "collapse" : "timestamp:8", "fl" : "timestamp,original,digest"})
    print(cdx_request)
    
    
    
# Test
if __name__ == "__main__":
    build_cdx_request("wikipedia.org", 20260101, 20261231)
        