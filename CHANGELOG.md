# Changelog


## [1.0.3] — 2026-02-22

### Añadido
- `retrieve.py --carpetas`: lista las carpetas IMAP disponibles en la cuenta; sustituye a `imap_folders.py` que queda obsoleto
- `categorizar.py --auto`: aplica auto-categorización a productos sin familia; reemplaza a `stats.py --autocategorize`

### Cambiado
- `stats.py`: pequeños cambios estéticos en el informe html.

### Eliminado
- `stats.py --autocategorize`: movido a `categorizar.py --auto`


## [1.0.2] — 2026-02-22

### Corregido
- `retrieve.py`: Mejoras en robustez, 
### Añadido
- `retrieve.py`: añadida opción `--todos` para buscar en todos los emails y no solo los recibidos de mercadona.
### Mejorado
- Mejor tratamiento de las rutas definidas en .env
---

## [1.0.0] — 2026-02-21 — versión inicial publicada

### Funcionalidades

**Importación de tickets**
- `retrieve.py`: descarga automática de PDFs desde Gmail via IMAP; filtra por nombre del adjunto para capturar también tickets reenviados por terceros; acepta argumento `N` para limitar a los últimos N días
- `main.py`: importa PDFs individualmente o por carpeta; mueve los procesados a `tickets_procesados/` y los que fallan a `tickets_error/`; usa `SAVE_DIR` del `.env` como carpeta por defecto
- `parser.py`: extrae cabecera (fecha, nº factura, tienda, CP, tarjeta) y líneas de producto (unidades y productos a peso)
- `manual.py`: introducción manual de tickets línea a línea, con sugerencias de productos, validación, resumen antes de guardar y opción de modificar antes de confirmar; borrado de tickets por nº de factura (`--borrar`)

**Base de datos**
- `db.py`: esquema SQLite con tablas `tarjetas`, `tickets`, `lineas_ticket`, `productos`, `Familias`; las 15 familias se insertan automáticamente en una instalación limpia
- `categorizar.py`: asignación interactiva de categorías a productos; `--lista` muestra todos agrupados por familia; `--buscar` edita cualquier producto; `--tarjetas` gestiona etiquetas de tarjetas de pago; sin argumentos, detecta automáticamente si hay productos sin categorizar

**Informe HTML**
- `stats.py`: genera `informe.html` interactivo con Chart.js; filtros por año, mes, rango de fechas y tarjeta; KPIs, gráfico de gasto mensual, desglose por familia, top productos, evolución de precio por producto, alertas de subida de precio, sección de tiendas y tabla de tickets paginada
- `stats.py --csv CARPETA`: exporta `tickets.csv`, `lineas.csv` y `productos.csv`
- `stats.py --sin-familia`: lista productos sin categoría
- `stats.py --autocategorize`: aplica auto-categorización

**Automatización**
- `run.py`: orquestador que encadena retrieve → main → stats; backup automático de la BD antes de cada ejecución; log diario en `logs/` con rotación a 30 días; acepta `--sin-retrieve` y `--dias N`
- `imap_folders.py`: lista las carpetas IMAP disponibles en Gmail

**Configuración**
- `.env.example`: todas las variables documentadas (`DB_PATH`, `SAVE_DIR`, `PROCESSED_DIR`, `ERROR_DIR`, `OUTPUT_DIR`, `IMAP_FOLDER`, `LOG_DIR`, `LOG_RETENTION_DAYS`, `BACKUP_DIR`, `BACKUP_COUNT`, credenciales de correo)
