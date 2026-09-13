import tldextract

# Bsp: blog.bmw.de => bmw.de
# Erkennung des Hosts 
def origin_domain(url_uncut : str) -> str:
    url_parts = tldextract.extract(url_uncut)
    hostname = url_parts.registered_domain
    return hostname