import json

with open("crux_negation_selectors/discovered_selectors.json", "r", encoding="utf-8") as additional_rejectors_file:
    additional_rejectors = json.load(additional_rejectors_file)
    working_selectors = [selector for selector in additional_rejectors.values() if selector["banner_gone"] == True]
    # CSS
    # Set eindeutig, dann weider list für dump. Keine mehrstufigen ablehnung zu selten für Zeitaufand
    css_selectors = sorted({selector["selector"] for selector in working_selectors if selector["method"] == "rule" and "->" not in selector["selector"]})
        
    # Generic
    # Set eindeutig, dann weider list für dump. *= um genereschsch von CSS zu trennen
    generic_selectors = sorted({selector["selector"] for selector in working_selectors if selector["method"] == "generic" and "*=" in selector["selector"]})
    
with open("utils/tcf_terms.json", "r", encoding="utf-8") as original_file:
        original = json.load(original_file)
        original["knownRejectSelectors"] = css_selectors
        original["genericRejectSelectors"] = generic_selectors
with open ("utils/tcf_terms.json" , "w", encoding="utf-8") as original_file:
    json.dump(original, original_file, indent=2, ensure_ascii=False)
    original_file.write("\n")