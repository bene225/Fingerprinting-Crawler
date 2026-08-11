# Wie funktioniert Monekeypatching

## Canvas Elemente in JS
https://developer.mozilla.org/de/docs/Web/API/HTMLCanvasElement#instanzmethoden


## Wrapper bauen
https://developer.mozilla.org/de/docs/Web/JavaScript/Reference/Global_Objects/Function/apply

- Wrapper vs Proxy 

## Verscheidene Funktionen für FP
Laperdrix, P., Bielova, N., Baudry, B., & Avoine, G. (2020). Browser fingerprinting: A survey. ACM Transactions on the Web (TWEB)

- canvas bei Websiet laden schon da, dann nur rechnen, canvas Existenz normal -> fkt untersuchen
- audio entsteht erst bei new AuContext() 
-  **AudioContext ist legitim, offlineaudiocontext nicht**
- AudioC abdecken  mit AudioBuffer.prototype.getChannelData, Nutzung für Hash