// Immer aufrufen
(() => {
    // Fügt 
    function register_fp(api,method){
        try {
            //Fingerprinting Ursprung 1P/3P
            const new_stack = new Error().stack || '';
            const script_urls = new_stack.match(/https?:\/\/[^\s\):]+/g) || [];
            // Url für 1P-Vergleich
            const py_url = window._location_url;
            let third_party = false;
            if (!py_url) {
                window.register_fp(api, method, location.href, "Keine py_url");
                return; 
            }
            for (let script_url of script_urls){
                try {
                    const script_hostname = new URL(script_url).hostname;
                    //Domain Matching (mit Subdomain)
                    if (script_hostname !== py_url && !script_hostname.endsWith('.' + py_url)) {
                        third_party = true;
                        break;
                    }
                }
                catch(e) {
                    console.log("URL Fehlerhaft");
                }
            }

            // Aufruf der Einbinung injector/register_fp in das JS (Python-BRÜCKE)
            window.register_fp(api, method, location.href, third_party);
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

    // MP für Local/session storage
    const storage_methods = ["setItem", "getItem"]; 
    storage_methods.forEach((method) => {
        if (Storage.prototype[method]){
            const fp_original_function = Storage.prototype[method];
            // Wrapper zu fp_o_f
            Storage.prototype[method] = function wrapper_and_original_fp(...args){
                register_fp("local/session storage", method);
                return fp_original_function.apply(this, args);
            }
        }
    })
    
    // MP für WebGL
    const WebGL_methods = ["getParameter", "getSupportedExtensions", "readPixels"]; 
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
        [Intl.DateTimeFormat.prototype, "resolvedOptions"],  //timezone locale calendar numberingSystem
        [NavigatorUAData.prototype, "getHighEntropyValues"]
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
        [Navigator.prototype, "userAgentData"],
        [Navigator.prototype, "plugins"],
        [Navigator.prototype, "platform"],
        [Navigator.prototype, "cookieEnabled"],
        [Navigator.prototype, "doNotTrack"],
        [Navigator.prototype, "language"],
        [Navigator.prototype , "languages"],
        [Screen.prototype, "width"],
        [Screen.prototype, "height"],
        [Screen.prototype, "colorDepth"],
        [window,  "devicePixelRatio"]];
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