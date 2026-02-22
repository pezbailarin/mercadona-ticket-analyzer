# TODO

Mejoras pendientes para futuras versiones.

---

**Mover `--autocategorize` a `categorizar.py --auto`**
✅ Conceptualmente esta es una operación sobre categorías, no sobre el informe. Es más probable que se busque esta función  en `categorizar.py` que no en `stats.py`.

**Fecha y hora de generación en el pie del informe**
✅ Permite saber si el informe que se está viendo es reciente o no. Añadido también link a github. Añadido icono de tarjetas de crédito.

**Integrar `imap_folders.py` como `retrieve.py --carpetas`**
✅ `imap_folders.py` es un script de un solo uso que no debería ser un fichero independiente. Quedaría más aseado si fuera una opción del script al que pertenece.

**Migrar autenticación de Gmail a OAuth2**
Google tiene previsto deprecar las App Passwords para cuentas con verificación en dos pasos. OAuth2 es el método recomendado y más seguro, aunque su configuración inicial sea más compleja.

**Mostrar records**
Máximo nº de compras el mismo día, ticket más caro, mayor tiempo entre compras...

**Mejorar robustez de retrieve.py**
* ✅  `try/except` alrededor de `fetch`: si un mensaje falla (timeout, error del servidor, mensaje corrupto) registrarlo como warning y continuar con el siguiente.
* ✅ Añadir una opción a retrieve que permita elegir si se busca por remitente (más rápido y robusto, pero puede dejar fuera correos reenviados) o sencillamente, como ahora, por ticket adjunto.
 


**Rutas en .env**
✅ Ahora mismo las rutas ya son absolutas
