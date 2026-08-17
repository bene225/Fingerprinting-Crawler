(() => {
    document.cookie;
    Object.defineProperty(document, "cookie");
    Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    const original_cookie = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
    //HTMLDocument.prototype Cookie auch nutzen?? lange veraltet.


    //neuer Setter Doc.pr um auch alle ifrmaes zu erwischen
    Object.defineProperty(Document.prototype, 'cookie', {
        set: function (val){


        }

    })
})();


//call
//https://github.com/BrunoFenzl/cookie-interceptor/
//https://stackoverflow.com/questions/32410331/proxying-of-document-cookie