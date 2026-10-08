"""
build_rules.py – baut reject_rules.json aus den Regeln von DuckDuckGo autoconsent.

Quelle: https://github.com/duckduckgo/autoconsent (Lizenz: MPL-2.0)
Die JSON-Regeln dort beschreiben pro CMP bzw. pro Website, wie man den Banner
erkennt (detectCmp/detectPopup) und wie man ablehnt (optOut).

Wir übernehmen nur, was für Playwright nötig ist, und werfen weg:
  - "cosmetic"-Regeln  -> die blenden den Banner nur aus, lehnen aber NICHT ab
                          (für die BA wäre das ein Messfehler!)
  - Regeln, deren optOut nur aus JS-"eval" besteht (können wir nicht ausführen)

Aufruf (einmalig bzw. zum Aktualisieren):
    git clone --depth 1 https://github.com/duckduckgo/autoconsent.git
    uv run build_rules.py autoconsent reject_rules.json
"""
import json
import sys
from pathlib import Path

# Die CMPs, die autoconsent in TypeScript statt JSON implementiert.
# Hier von Hand nachgebaut (nur die Klick-Pfade, keine JS-API-Aufrufe).
MANUAL_RULES = [
    {
        "name": "onetrust",
        "detectCmp": [{"exists": "#onetrust-banner-sdk,#onetrust-pc-sdk"}],
        "detectPopup": [{"visible": "#onetrust-banner-sdk,#onetrust-pc-sdk", "check": "any"}],
        "optOut": [{"any": [
            {"click": "#onetrust-reject-all-handler"},
            {"click": ".ot-pc-refuse-all-handler"},
            {"click": ".js-reject-cookies"},
            # Fallback: Einstellungen öffnen, alle Toggles aus, speichern
            # Liste = Sequenz (Erweiterung ggü. autoconsent, siehe consent_rejector.py)
            [
                {"click": "#onetrust-pc-btn-handler"},
                {"wait": 800},
                {"click": "#onetrust-consent-sdk input.category-switch-handler:checked",
                 "all": True, "optional": True},
                {"waitForThenClick": ".save-preference-btn-handler,.js-consent-save", "timeout": 3000},
            ],
        ]}],
    },
    {
        "name": "cookiebot",
        "detectCmp": [{"exists": "#CybotCookiebotDialog,#cookiebanner"}],
        "detectPopup": [{"visible": "#CybotCookiebotDialog", "check": "any"}],
        "optOut": [{"any": [
            {"click": "#CybotCookiebotDialogBodyButtonDecline"},
            {"click": "#CybotCookiebotDialogBodyLevelButtonLevelOptinDeclineAll"},
            {"click": "#CybotCookiebotDialogBodyButtonDeclineAll"},
        ]}],
    },
    {
        "name": "consentmanager.net",
        "detectCmp": [{"exists": "#cmpbox"}],
        "detectPopup": [{"visible": "#cmpbox", "check": "any"}],
        "optOut": [{"any": [
            {"click": ".cmpboxbtnno"},
            [
                {"exists": ".cmpwelcomeprpsbtn"},
                {"click": ".cmpwelcomeprpsbtn > a[aria-checked=true]", "all": True, "optional": True},
                {"click": ".cmpboxbtnsave"},
            ],
        ]}],
    },
    {
        # Sourcepoint läuft in einem iframe -> Regel wird gegen Frames geprüft,
        # deren URL auf das Muster passt.
        "name": "sourcepoint-frame",
        "runContext": {"main": False, "frame": True,
                       "urlPattern": r"(message_id=|/privacy-manager/index\.html|sp-prod\.net)"},
        "detectCmp": [{"exists": ".message-container,.message,[class*=sp_choice_type]"}],
        "detectPopup": [{"visible": "[class*=sp_choice_type]", "check": "any"}],
        "optOut": [{"any": [
            {"click": ".sp_choice_type_13"},          # "Alle ablehnen" im Notice
            {"click": ".sp_choice_type_REJECT_ALL"},  # im Privacy Manager
            {"click": ".sp_choice_type_SE"},
        ]}],
    },
    {
        "name": "trustarc-top",
        "detectCmp": [{"exists": "#truste-show-consent,#truste-consent-track"}],
        "detectPopup": [{"visible": "#truste-consent-content,#truste-consent-track", "check": "any"}],
        "optOut": [{"click": "#truste-consent-required"}],
    },
    {
        "name": "klaro",
        "detectCmp": [{"exists": ".klaro > .cookie-notice,.klaro > .cookie-modal"}],
        "detectPopup": [{"visible": ".klaro > .cookie-notice,.klaro > .cookie-modal", "check": "any"}],
        "optOut": [{"any": [
            {"click": ".klaro .cn-decline"},
            {"click": ".klaro .cm-btn-decline"},
        ]}],
    },
]

USED_KEYS = ("name", "runContext", "detectCmp", "detectPopup", "optOut")


def contains_eval(steps) -> bool:
    return "EVAL_" in json.dumps(steps) or '"eval"' in json.dumps(steps)


def only_eval(steps) -> bool:
    """True, wenn im optOut kein einziger Klick vorkommt."""
    s = json.dumps(steps)
    return '"click"' not in s and '"waitForThenClick"' not in s


def main(repo: Path, out: Path) -> None:
    rules, skipped = [], {"cosmetic": 0, "eval_only": 0, "no_optout": 0}
    files = sorted((repo / "rules" / "autoconsent").glob("*.json")) + \
            sorted((repo / "rules" / "generated").glob("*.json"))

    for f in files:
        r = json.loads(f.read_text())
        if r.get("cosmetic"):
            skipped["cosmetic"] += 1
            continue
        if not r.get("optOut"):
            skipped["no_optout"] += 1
            continue
        if only_eval(r["optOut"]):
            skipped["eval_only"] += 1
            continue
        rule = {k: r[k] for k in USED_KEYS if k in r}
        rule["source"] = "generated" if "generated" in f.parts else "autoconsent"
        rule["partial_eval"] = contains_eval(r["optOut"])
        rules.append(rule)

    for m in MANUAL_RULES:
        rules.append({**m, "source": "manual", "partial_eval": False})

    # Seitenspezifische Regeln (mit urlPattern) zuerst prüfen, dann generische CMPs.
    rules.sort(key=lambda r: 0 if r.get("runContext", {}).get("urlPattern") else 1)

    out.write_text(json.dumps({
        "_license": "Regeln abgeleitet aus duckduckgo/autoconsent, MPL-2.0",
        "rules": rules,
    }, indent=1, ensure_ascii=False))
    print(f"{len(rules)} Regeln geschrieben -> {out}   übersprungen: {skipped}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
