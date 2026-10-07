import json
from pathlib import Path

# Regionen Test Reihenfolge
TR_REGIONS = ["DE", "US", "GB", "FR", "NL", "CH", "NO", "CA", "AU"]
TR_DOMAINS = Path("utils/trackerradar/data/domains")


# Wo kommt Domain vor, None falls nicht
def lookup_domain(domain : str) -> tuple[dict, str] | None:
    for region in TR_REGIONS:
        domain_file = TR_DOMAINS / region / f"{domain}.json"
        if domain_file.exists():
            return json.loads(domain_file.read_text(encoding="utf-8")), region
    return None


# Nach Crawl werden einzelne Zeilen nach tr klassifiziert
# stats_key: stats_vor_consent WB oder "stats_nach_consent" (volles Bild)
def classify_row(row : dict, stats_key : str) -> dict:
    domains = row[stats_key]["script_domains_3p"]
    tr = {"tr_fp_scores": {}, "tr_cookie_shares": {}, "tr_categories": {}, "tr_owner": {}, "tr_regions": {}, "tr_unknown": []}
    for domain in domains:
        found = lookup_domain(domain)
        if found is None:
            tr["tr_unknown"].append(domain)
            continue
        entry, region = found
        tr["tr_fp_scores"][domain] = entry.get("fingerprinting", 0) # 0-3, 2 <= Tracking
        tr["tr_cookie_shares"][domain] = entry.get("cookies", 0) # Anteil Top-Seiten mit Cookies dieser Domain
        tr["tr_categories"][domain] = entry.get("categories", [])
        tr["tr_owner"][domain] = (entry.get("owner") or {}).get("displayName", "")
        tr["tr_regions"][domain] = region
    # Erfolgsquote
    tr["tr_coverage"] = round(len(tr["tr_fp_scores"]) / len(domains), 3) if domains else None
    return tr


# Ganze Datei klasssifizieren
def classify_file(in_path : Path, out_path : Path) -> None:
    with open(in_path, encoding="utf-8") as in_file, open(out_path, "w", encoding="utf-8") as out_file:
        for line in in_file:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "stats_vor_consent" in row:
                # Events ans Ende
                events = row.pop("events", None)
                # Ergebnisse anhängen danmach auch weider events
                # vor Consent immer (+ Wayback ), nach Consent nur falls gemessen
                row["tr_vor_consent"] = classify_row(row, "stats_vor_consent")
                if row.get("stats_nach_consent"):
                    row["tr_nach_consent"] = classify_row(row, "stats_nach_consent")
                if events is not None:
                    row["events"] = events
            out_file.write(json.dumps(row) + "\n")
