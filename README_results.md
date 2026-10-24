# Forschungsdaten

Rohdaten der Messreihen zur Bachelorarbeit „Vom Cookie zum Fingerprint: Eine empirische Untersuchung zur Substitution zustandsbehafteter Tracker im modernen Web“ (Benedikt Hartl, Universität Regensburg, 2026). Erzeugt mit dem Crawler aus dem Repository `Fingerprinting-Crawler`, ausgewertet mit `analysis/ff1.ipynb` bis `ff3.ipynb`.

## Dateien

| Datei | Messreihe | Zeitraum 2026 | Websites |
|---|---|---|---|
| `Forschungsfrage 1/ff1_live.jsonl` | FF1, Live-Messung | 09.–10.10. | 500 |
| `Forschungsfrage 1/ff1_hist.jsonl` | FF1, Snapshots der Wayback Machine an 6 Stichtagen | 09.–11.10. | 500 |
| `Forschungsfrage 1/ff1/` | Screenshots zu FF1 (4.081 JPEG) | | |
| `Forschungsfrage 2/ff2_alles_erlaubt.jsonl` | FF2, Bedingung 1: keine Sperre | 12.–14.10. | 1.000 |
| `Forschungsfrage 2/ff2_nur_cdp.jsonl` | FF2, Bedingung 2: Sperre des Browsers | 12.–14.10. | 1.000 |
| `Forschungsfrage 2/ff2_alles_geblockt.jsonl` | FF2, Bedingung 3: Sperre des Browsers und der JavaScript-Cookies | 12.–14.10. | 1.000 |
| `Forschungsfrage 3/ff3_keine_aktion.jsonl` | FF3, keine Aktion | 14.–16.10. | 999 |
| `Forschungsfrage 3/ff3_zustimmen.jsonl` | FF3, Zustimmung | 14.–16.10. | 999 |
| `Forschungsfrage 3/ff3_ablehnen.jsonl` | FF3, Ablehnung | 14.–16.10. | 999 |

Die Websites stammen aus der Tranco-Liste 647LX, je Rangbereich gleich viele, mit festem Startwert gezogen (Abschnitt 5.3.2). Die ersten 500 bilden die Stichprobe von FF1, FF2 und FF3 hängen 500 weitere an. FF3 lässt economictimes.com aus, weil der Browser an ihren Aufrufen hängen blieb. In `ff3_ablehnen.jsonl` steht dazu nur eine Fehlerzeile.

Format: JSON Lines (UTF-8), jede Zeile ist ein JSON-Objekt. Zeitstempel in Ortszeit.

## Zeilenarten

| Art | Erkennbar an | Inhalt |
|---|---|---|
| Konfiguration | kein Feld `success` | alle Einstellungen eines Starts, eine Zeile je Start des Crawlers |
| Messung | `success: true` und `stats_vor_consent` | Kennzahlen beider Messpunkte und alle Aufrufe |
| Fehler | `success: false` | `error`: Fehlermeldung, die Website wurde später erneut besucht |
| Kein Snapshot (nur `ff1_hist`) | `no_snapshot: true` | kein Snapshot im Toleranzfenster von ±120 Tagen um `stichtag` |
| Übersprungen (nur `ff1_hist`) | `skipped` | Website lädt live nicht, kein Archiv-Crawl |

Fehlerzeilen bleiben als Protokoll stehen. Gültig ist je Website (im Archiv je Website und Stichtag) die letzte Zeile mit `success` und `internet_ok` gleich `true`. So werten auch die Notebooks aus.

## Felder einer Messzeile

| Feld | Bedeutung |
|---|---|
| `id`, `website`, `crawl_name`, `crawl_time` | laufende Nummer, besuchte Startseite, Messreihe, Zeitpunkt |
| `internet_ok` | Internetverbindung nach dem Besuch vorhanden |
| `stats_vor_consent` | Messpunkt 1, vor dem Consent-Banner |
| `stats_nach_consent` | Messpunkt 2, nach dem Banner, umfasst alle Aufrufe seit dem Laden |
| `events` | jeder überwachte Aufruf: `api`, `method`, `url` (Adresse des Frames), `third_party` (`true`, `false` oder `"Keine py_url"` = nicht zuordenbar), `script_url` (Host des Drittanbieter-Skripts). Die ersten `stats_vor_consent.n_fp_calls` Einträge gehören zu Messpunkt 1 |

Felder in `stats_vor_consent` und `stats_nach_consent`:

| Gruppe | Felder |
|---|---|
| Seite | `title`, `status` (nur Messpunkt 1), `final_url`, `cross_domain_redirect`, `screenshot`, `hist_crawl` |
| Fingerprinting | `n_fp_calls`, `n_fp_calls_1p`, `n_fp_calls_3p`, `n_fp_calls_unbekannt`, `fp_calls_per_api`, `fp_calls_per_api_1p`, `fp_calls_per_api_3p`, `fp_calls_per_method`, `n_fp_sources`, `fp_sources` |
| Anfragen | `n_3p_requests`, `requests_per_type`, `n_3p_domains`, `domains_3p`, `n_script_domains_3p`, `script_domains_3p` |
| Cookies (nur live) | `n_cookies`, `n_cookies_1p`, `n_cookies_3p`, `n_cookies_http_sicher` (HttpOnly), `n_cookies_http_oder_js`, `n_cookie_sources_3p`, `cookie_sources_3p`, `cookie_sources_partitioned` |
| Archiv (nur `ff1_hist`) | `stichtag`, `timestamp`, `wait_seconds`, `wait_capped` (diese vier nur Messpunkt 1), `n_archive_429`, `n_archive_conn_errors`, `n_archive_5xx`, `n_blocked_live_requests`, `blocked_live_domains`, `script_capture_dates`, `script_gap_days`, `n_script_domains_gap_over_365`, `max_script_gap_days` |
| Consent (nur Messpunkt 2) | `consent_ok` (Button geklickt), `consent_check` |

`consent_check` enthält `tcf_status` und `consent_storage_changed`. In FF3 kommen hinzu: `consent_action`, `consent_click`, `consent_seconds`, `consent_selector`, `consent_stage`, `consent_cookies`, `tcf`, `consent_decision`, `consent_verified`.

First- und Third-Party trennt die eTLD+1 (Abschnitt 5.3.5). Aufrufe an `local/session storage` sind enthalten, zählen in der Arbeit aber nicht als Fingerprinting.


---
Diese README wurde mithilfe von KI (Claude) erstellt.
