# Entscheidungen zu Browser Controller

## Sicherstellen, dass keine 3P Cookies mehr geladen werden können
## Verhindert das Auslesen der 3p Cookies
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

## Verhindern von Setzen von 3p Cookies
- Computer empfängt die http Response und leitet sie um
- Header wird manipuliert, Set-Cookies werden rausgeschnitten
- Dann weiterleitung der Response ohne cookie setter