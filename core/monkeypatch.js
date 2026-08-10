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
    
    const canvas_methods = ["toDataUrl", "toBlob"]; //Die beiden Test
    // Ba Text auf welche Funktionen genau getestet wird schreiben getImageData usw. suchen

    canvas_methods.forEach((name) => {
        //https://developer.mozilla.org/de/docs/Web/API/HTMLCanvasElement#instanzmethoden
        const fp_original_function = HTMLCanvasElement.prototype[name]
        // Wrapper zu fp_o_f
    }) 


});