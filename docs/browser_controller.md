# Entscheidungen zu Browser Controller

## Sicherstellen, dass keine 3P Cookies mehr geladen werden können
## if self._allow_3p == False:
### --test-third-party-cookie-phaseout
https://www.chromium.org/Home/chromium-privacy/privacy-sandbox/third-party-cookie-phaseout/

- Flag in Chrome, welche alle von 3P gesetzten Cookies deaktivieren soll
- Funktionsweise kann sich in Zukunft theoretisch ändern (- reproduzierbarkeit)
- Nicht wirklich nachvollziehbar (- verlässlichkeit)
- offizieller Flag eines der meistgenutzen Browser (+ verlässlichkeit)

### context.route 

- selber geschrieben und fix (+reprpduzierbarkeit)
- unterschiedlicher Umfang zur Flag
- völlig nachvollziehbar
- wiederverwendbar
- erweiterbar