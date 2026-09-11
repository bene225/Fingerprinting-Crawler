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
    const canvas2d_methods = ["getImageData, isPointInPath, measureText"]; //Die beiden Test
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
    const WebGL_methods = ["getImageData, isPointInPath, measureText"]; //Die beiden Test
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

    const audio_constructor = "OfflineAudioContext";
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
})();