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
        }
    }
    
    // MP für Canvas
    const canvas_methods = ["toDataUrl", "toBlob"]; //Die beiden Test
    // Ba Text auf welche Funktionen genau getestet wird schreiben getImageData usw. suchen
    canvas_methods.forEach((method) => {
        if (HTMLCanvasElement.prototype[method]){
            //https://developer.mozilla.org/de/docs/Web/API/HTMLCanvasElement#instanzmethoden
            const fp_original_function = HTMLCanvasElement.prototype[method];
            // Wrapper zu fp_o_f
            HTMLCanvasElement.prototype[method] = function wrapper_and_original_fp(...args){
                register_fp("canvas" ,method);
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

});