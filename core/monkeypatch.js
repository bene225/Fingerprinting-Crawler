// Immer aufrufen
(() => {
    // Fügt 
    function register_fp(api,method){
        try {
            // Aufruf der Einbinung injector/register_fp in das JS
            window.register_fp(api, method, location.href);
        }
        catch(exception){
            // Absutz Crawler verhindern
             console.error("register_fp Fehler", exception); 
        }
    }
    
    // MP für Canvas
    const canvas_methods = ["toDataURL", "toBlob"]; //Die beiden Test
    // Ba Text auf welche Funktionen genau getestet wird schreiben getImageData usw. suchen
    canvas_methods.forEach((method) => {
        if (HTMLCanvasElement.prototype[method]){
            //https://developer.mozilla.org/de/docs/Web/API/HTMLCanvasElement#instanzmethoden
            const fp_original_function = HTMLCanvasElement.prototype[method];
            // Wrapper zu fp_o_f
            HTMLCanvasElement.prototype[method] = function wrapper_and_original_fp(...args){
                register_fp("canvas", method);
                return fp_original_function.apply(this, args);
            }
        }
    })

     // MP für Canvas2d
    const canvas2d_methods = ["getImageData", "isPointInPath", "measureText"]; //Die beiden Test
    canvas2d_methods.forEach((method) => {
        if (CanvasRenderingContext2D.prototype[method]){
            const fp_original_function = CanvasRenderingContext2D.prototype[method];
            // Wrapper zu fp_o_f
            CanvasRenderingContext2D.prototype[method] = function wrapper_and_original_fp(...args){
                register_fp("canvas2D", method);
                return fp_original_function.apply(this, args);
            }
        }
    })
    
    // MP für WebGL
    const WebGL_methods = ["getParameter", "getSupportedExtensions", "readPixels"]; //Die beiden Test
    WebGL_methods.forEach((method) => {
        if (WebGLRenderingContext.prototype[method]){
            const fp_original_function = WebGLRenderingContext.prototype[method];
            // Wrapper zu fp_o_f
            WebGLRenderingContext.prototype[method] = function wrapper_and_original_fp(...args){
                register_fp("WebGL", method);
                return fp_original_function.apply(this, args);
            }
        }
    })
    
    //MP für Audio 
    const audio_methods = ["getChannelData"];
    audio_methods.forEach((method) => {
        if (AudioBuffer.prototype[method]){
            const fp_original_function = AudioBuffer.prototype[method];
            AudioBuffer.prototype[method] = function wrapper_and_original_fp(...args){
                register_fp("audio", method);
                return fp_original_function.apply(this, args);
            }

        }
    })

    const audio_constructors = ["OfflineAudioContext", "AudioContext"];
    for (const audio_constructor of audio_constructors){
        if (window[audio_constructor]){
            const fp_original_function = window[audio_constructor];
            window[audio_constructor] = function wrapper_and_original_fp (...args){
                register_fp("webaudio", audio_constructor);
                // Neue fkt muss wieder Instanzen vom Original erzeugen
                return new fp_original_function(...args);
            }
            // Wieder vererbung von Funktionen der normalen Funktion holen
            window[audio_constructor].prototype = fp_original_function.prototype; 
        }
    }
    // MP für weitere Restliche FKT
    const misc_methods = [
        [navigator.mediaDevices, "enumerateDevices"],
        [Navigator.prototype,    "getBattery"],
        [speechSynthesis,        "getVoices"],
        [navigator.storage,      "estimate"],
        [Intl.DateTimeFormat.prototype, "resolvedOptions"], //timezone locale calendar numberingSystem
    ]; 

    misc_methods.forEach(([api, method]) => {
        if (method && api[method]){
            const fp_original_function = api[method]
            // Wrapper zu fp_o_f
            api[method] = function wrapper_and_original_fp(...args){
                register_fp(api.constructor.name, method);
                return fp_original_function.apply(this, args);
            }
        }
    })

    // TODO: statisches Fingerprinting
    //https://developer.mozilla.org/en-US/docs/Web/API/Navigator#instance_methods
    //Laperdix (welche FP relevant für BA)
    const static_properties = [
        [Navigator.prototype, "userAgent"],
        [Navigator.prototype, "plugins"],
        [Navigator.prototype, "platform"],
        [Navigator.prototype, "cookieEnabled"],
        [Navigator.prototype, "doNotTrack"],
        [Navigator.prototype, "language"]
        [Screen.prototype, "width"],
        [Screen.prototype, "height"],
        [Screen.prototype, "colorDepth"],
        [Window.prototype,  "devicePixelRatio"]];
    static_properties.forEach(([proto, property]) => {
        const original_property_descriptor = Object.getOwnPropertyDescriptor(proto, property);
        if (!original_property_descriptor || !original_property_descriptor.get) return;
        Object.defineProperty(proto, property, {
            // Zu viel Bot Block enumerable = ture
            // Falls während website Aufruf geändert wird configurable = true
            get: function(){
                register_fp(proto.constructor.name, property);
                return original_property_descriptor.get.call(this);
            }
        })

    })
        
})();