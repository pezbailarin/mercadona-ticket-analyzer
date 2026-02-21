# Mercadona Ticket Analyzer

Herramienta en Python para importar, almacenar y analizar los tickets de compra de Mercadona a partir de los tickets en PDF que envían por correo electrónico.

---

## ¿Para qué sirve?

Mercadona envía un ticket en PDF por cada compra, si se ha registrado la tarjeta de crédito para ello. Este proyecto convierte esos PDFs en una base de datos SQLite y genera un informe HTML interactivo que permite ver el gasto por categoría, por mes, por tienda, la evolución del precio de cada artículo a lo largo del tiempo y alertas cuando un producto ha subido de precio respecto a su media histórica.

---

## Requisitos

- Python 3.9 o superior
- `pdfplumber`
- `python-dotenv`


No se necesitan más dependencias externas. El informe HTML funciona directamente en el navegador sin servidor.

---

## Instalación

```bash
git clone <url-del-repo>
cd mercadona-ticket-analyzer
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

La base de datos se crea automáticamente en el primer uso.

## Configuración

Copia `_env.example` a `.env` y edita los valores:

```bash
cp _env.example .env
```

| Variable | Descripción | Por defecto |
|---|---|---|
| `IMAP_FOLDER` | Carpeta IMAP de Gmail (`[Gmail]/All Mail` en inglés) | `[Google Mail]/Todos` |
| `EMAIL_ADDR` | Cuenta Gmail para descargar tickets | — |
| `APP_PASSWORD` | Contraseña de aplicación de Google | — |
| `SAVE_DIR` | Carpeta donde `retrieve.py` descarga los PDFs | — |
| `DB_PATH` | Ruta completa a la base de datos SQLite | `mercadona.db` en la carpeta del proyecto |
| `PROCESSED_DIR` | PDFs procesados con éxito | `tickets_procesados/` en la carpeta del proyecto |
| `ERROR_DIR` | PDFs que no se han podido parsear | `tickets_error/` en la carpeta del proyecto |

Las variables `DB_PATH`, `PROCESSED_DIR` y `ERROR_DIR` son opcionales — si no están definidas se usan los valores por defecto.

---

## Uso

### Descargar tickets del correo

```bash
python3 retrieve.py       # descarga todos los tickets de Mercadona
python3 retrieve.py 30    # solo los de los últimos 30 días
python3 retrieve.py 7     # solo los de la última semana
```

### Importar tickets PDF

```bash
python3 main.py                      # procesa la carpeta SAVE_DIR del .env
python3 main.py ticket.pdf           # un solo PDF
python3 main.py carpeta_con_pdfs/    # todos los PDFs de una carpeta
```

Los PDFs procesados con éxito se mueven automáticamente a `tickets_procesados/` o a la carpeta especificada en el fichero .env.

### Generar el informe

```bash
python3 stats.py                        # genera informe.html
python3 stats.py --output enero.html    # nombre de salida personalizado
python3 stats.py --sin-familia          # lista productos sin categoría y sale
python3 stats.py --autocategorize       # aplica auto-categorización y sale
python3 stats.py --csv ./exportacion/    # exporta datos a CSV y sale
```

Abre el HTML resultante en cualquier navegador. No requiere conexión a internet después de la primera generación (Chart.js se descarga y cachea en `.chartjs.cache.js`).

### Introducir un ticket manualmente

Las compras sin PDF (por ejemplo pagadas en efectivo) se pueden introducir a mano:

```bash
python3 manual.py                    # introducir ticket nuevo
python3 manual.py --borrar           # buscar y borrar un ticket por nº de factura
```

### Gestionar categorías de productos

```bash
python3 categorizar.py               # categorizar los productos sin familia (uno a uno)
python3 categorizar.py --lista       # ver todos los productos agrupados por familia
python3 categorizar.py --buscar      # buscar y editar cualquier producto directamente
```

---

## Automatización (cron)

Para ejecutar el ciclo completo por ejemplo cada día a las 22:35:

```
35 22 * * * cd /ruta/a/tu/proyecto && /usr/bin/python3 run.py
```

`run.py` encadena retrieve → main → stats con control de errores y escribe un log diario en `logs/`. Solo regenera el informe si se han importado tickets nuevos.

```bash
python3 run.py                   # ciclo completo
python3 run.py --sin-retrieve    # solo main + stats
python3 run.py --dias 7          # retrieve solo de los últimos 7 días
```

---

## Ejemplo rápido

```bash
# 1. Importar todos los PDFs descargados
python3 main.py ~/Descargas/mercadona/

# 2. Categorizar los productos nuevos (si los hay)
python3 categorizar.py

# 3. Ver el informe
python3 stats.py && open informe.html
```

---

## Estructura del proyecto

| Fichero | Descripción |
|---|---|
| `main.py` | Importa PDFs a la BD |
| `parser.py` | Extrae datos del texto del PDF |
| `db.py` | Gestión de la base de datos SQLite |
| `stats.py` | Genera el informe HTML interactivo |
| `categorizar.py` | Asignación interactiva de categorías |
| `manual.py` | Introducción y borrado manual de tickets |
| `mercadona.db` | Base de datos (se crea automáticamente) |
| `tickets_procesados/` | PDFs ya importados (se crea automáticamente) |

---

## Licencia

Uso personal. Sin restricciones.
