# Configurar autenticación OAuth2 con Gmail

Por defecto, `retrieve.py` usa una **Contraseña de aplicación** de Google para acceder a Gmail. Esta guía explica cómo cambiar a **OAuth2**, el método recomendado por Google y más seguro a largo plazo.

---

## Requisitos previos

- Una cuenta de Google (la misma que usas para recibir los tickets)
- El entorno virtual del proyecto activado

---

## Paso 1 — Crear un proyecto en Google Cloud Console

1. Ve a https://console.cloud.google.com
2. En la barra superior, haz clic en el selector de proyectos (o pulsa CTRL-O) → **Nuevo proyecto**
3. Ponle un nombre (por ejemplo `mercadona-tickets`) y haz clic en **Crear**
4. Asegúrate de que el proyecto nuevo está seleccionado en la barra superior antes de continuar.

---

## Paso 2 — Activar la API de Gmail

1. En el menú de la izquierda ve a **APIs y servicios → Biblioteca**
2. Busca `Gmail API` y haz clic en el resultado.
3. Haz clic en **Habilitar**

---

## Paso 3 — Configurar la identidad

1. Ve a **APIs y servicios → Pantalla de consentimiento de OAuth** y  pulsa **Comenzar**  
2. Configuración inicial:
    * App name: pon un nombre cualquiera
    * User support email: tu propio correo de gmail.
    * Audience: selecciona EXTERNO
    * Developer Contact info: de nuevo tu propio correo.
 3. Haz click en guardar.
 
--- 

## Paso 4 —  Autorizar tu cuenta

1. En el menú lateral de la sección de Auth busca la pestaña **Público**.
2. Busca el apartado **Usuarios de prueba**
3. Pulsa en **+ ADD USERS**
4. Escribe tu dirección de correo y pulsa guardar.

---
 
## Paso 5 — Generar las credenciales (archivo JSON)

1. Ve a **APIs y servicios -> Credenciales**
2. Pulsa **+Crear Credenciales** y elige **ID de cliente de OAuth**
3. En el desplegable "Tipo de aplicación" elige **Aplicación de Escritorio**
4. Ponle un nombre (P.ej. "Llave Python") y pulsa **Crear**
5. En la ventana que aparece no copies nada: pulsa el enlace **Descargar JSON**
    * Busca en tu sistema el archivo descargado y cambiale el nombre a credentials.json
    * Muevelo a la carpeta del analizador de Tickets Mercadona
 
 ---
 
## Paso 6 — Primer inicio y autentificación

Al ejecutar `retrieve.py` por vez primera aparece un enlace. Copialo y abrelo en un navegador.
Elige tu cuenta de gmail, concede los permisos que se te pidan, ignora cualquier advertencia de seguridad y copia el código que aparece al final. 
`Retrieve.py` está esperando ese código. Pégalo y acepta. 

---

## Paso 7 — Configurar el .env

Añade esta línea a tu `.env`:

```
GOOGLE_CREDENTIALS=/ruta/absoluta/al/proyecto/credentials.json
```

Si quieres guardar el token en una ubicación distinta a la carpeta del proyecto,
añade también:

```
OAUTH_TOKEN=/ruta/absoluta/al/proyecto/token.json
```

Puedes dejar `APP_PASSWORD` en el `.env` o borrarlo — si `GOOGLE_CREDENTIALS`
está definido, el script usa OAuth2 y no mira `APP_PASSWORD`.
