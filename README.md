# Fingerprinting-Crawler

Crawler und Auswertung zur Bachelorarbeit „Vom Cookie zum Fingerprint: Eine empirische Untersuchung zur Substitution zustandsbehafteter Tracker im modernen Web“ (Benedikt Hartl, Universität Regensburg, 2026).

Der Crawler besucht Websites der Tranco-Liste mit Playwright (Chromium), zählt die Aufrufe fingerprinting-relevanter Browser-Schnittstellen und ordnet jeden Aufruf First- oder Third-Party zu. Die Methodik beschreibt Kapitel 5 der Arbeit.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `main.py` | Start der Messreihen, alle Einstellungen der Läufe |
| `config.py` | Konfigurationsobjekt mit Standardwerten |
| `core/` | Crawler: Browsersteuerung, Monkeypatching (`monkeypatch.js`), JavaScript-Cookie-Sperre (`js_cookie_block.js`), Consent-Banner, Archiv-Crawl, Ergebnisdatei |
| `utils/` | Ziehung aus der Tranco-Liste, Abfragen an die Wayback Machine, Hilfsfunktionen, Wortliste und Selektoren für Consent-Banner (`tcf_terms.json`) |
| `analysis/` | Auswertung je Forschungsfrage: `ff1.ipynb`, `ff2.ipynb`, `ff3.ipynb` |
| `tests/` | Einzeltests zu Aussagen der Arbeit |

## Einrichtung

Voraussetzung: Python 3.14 und [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run playwright install chromium
```

Die Tranco-Liste ist zu groß für das Repository. Die Liste mit der Kennung 647LX (https://tranco-list.eu/list/647LX) als CSV (`Rang,Domain`, ohne Kopfzeile) unter `utils/tranco_647LX.csv` ablegen.

## Messung

```
uv run python main.py --live      # FF1: Live-Messung
uv run python main.py --hist      # FF1: Snapshots der Wayback Machine
uv run python main.py --block     # FF2: drei Bedingungen der Cookie-Sperre
uv run python main.py --consent   # FF3: keine Aktion, Zustimmung, Ablehnung
```

Jeder Aufruf startet eine Messreihe, mehrere können in getrennten Terminals parallel laufen. Der Browser läuft sichtbar und braucht eine grafische Oberfläche. Nach einem Abbruch setzt ein neuer Start fort und besucht nur Websites ohne gültige Messung erneut. Die Ergebnisse landen in `results/Forschungsfrage 1` bis `3`, ihren Aufbau beschreibt `results/README.md` (liegt den Forschungsdaten bei).

## Auswertung

Die Notebooks in `analysis/` lesen die Ergebnisdateien aus `results/` und berechnen die Tests, Tabellen und Abbildungen der Arbeit. Die Abbildungen speichern sie als SVG unter `../Fingerprinting-Bachelor/figures/` (LaTeX-Projekt der Arbeit). Die Zelle zu den Rangbereichen braucht die Tranco-Liste.

## Code-Stand der Messungen

| Messreihe | Zeitraum | Code |
|---|---|---|
| FF1 | 09.–11.10.2026 | Tag `ff1-crawl` |
| FF2 | 12.–14.10.2026 | Tag `ff2-crawl` |
| FF3 | 14.–16.10.2026 | Commit `e5d4603` (nach dem Lauf committet) |

Die erste Zeile jeder Ergebnisdatei enthält zusätzlich alle Einstellungen des Laufs.

## Tests

| Datei | Zeigt | Arbeit |
|---|---|---|
| `tests/user_agent.py` | User-Agent des Browsers | Anhang A |
| `tests/cookie_block_probe.py` | Entfernen der Cookie-Header per `route.fetch` sperrt keine Cookies, die Sperre über das Chrome DevTools Protocol schon | Abschnitt 5.3.4 |
| `tests/consent_probe.py` | Banner-Suche zum Zustimmen auf lokalen Testseiten (CSS-Selektor, Wortliste, Shadow DOM, Iframes, Verneinungen) | Abschnitt 5.3.6 |

Start: `uv run python tests/<Datei>`, `consent_probe.py` mit dem Argument `offline`.

## Quellen

- Selektoren und Wortliste zum Zustimmen (`utils/tcf_terms.json`): Maximilian Wittig, unverändert übernommen.
- Selektoren zum Ablehnen: abgeleitet aus den Klick-Regeln von DuckDuckGo autoconsent (https://github.com/duckduckgo/autoconsent, MPL-2.0). Der Vorlauf auf 2000 Websites (Anhang B) liegt im Branch `ki`, `utils/import_selectors_to_list.py` hat sein Ergebnis in `tcf_terms.json` übernommen.

---
Diese README wurde mithilfe von KI (Claude) erstellt.
