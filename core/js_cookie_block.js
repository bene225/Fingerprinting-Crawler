(() => {
    //document.cookie;
    //Object.defineProperty(document, "cookie");
    //Object.getOwnPropertyDescriptor(Document.prototype, "cookie");

    const original_cookie_descriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie') || Object.getOwnPropertyDescriptor(HTMLDocument.prototype, 'cookie');
    //HTMLDocument.prototype Cookie auch nutzen?? lange veraltet.


    //neuer Setter Doc.pr um auch alle ifrmaes zu erwischen
    Object.defineProperty(Document.prototype, 'cookie', {
        //1 Million Site Measurement
        set: function (val){
            //Urls von Cookieaufruf aus Browser auslesen.
            const new_stack = new Error().stack || '';
            const script_urls = new_stack.match(/https?:\/\/[^\s\):]+/g) || [];
            // Url für 1P-Vergleich
            const py_url = window._location_url;

            //Notfalls durchreichen, falls Übertrgungsfehler von py script
            if (!py_url){
                return original_cookie_descriptor.set.call(document,val);
            }
            let third_party = true
            for (let script_url of script_urls){
                
            }

        }

    })
})();


//call
//https://github.com/BrunoFenzl/cookie-interceptor/
//https://stackoverflow.com/questions/32410331/proxying-of-document-cookie
//https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error/stack