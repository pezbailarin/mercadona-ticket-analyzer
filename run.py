#!/usr/bin/env python3
"""
run.py — Orquestador del Mercadona Ticket Analyzer.

Ejecuta en orden: retrieve → main → stats
Solo regenera el informe si se han importado tickets nuevos.

Uso:
    python3 run.py                  # ciclo completo
    python3 run.py --sin-retrieve   # solo main + stats (sin descargar del correo)
    python3 run.py --dias 30        # retrieve solo de los últimos 30 días
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Configuración de log ─────────────────────────────────────────
LOG_DIR  = Path(os.getenv("LOG_DIR", Path(__file__).parent / "logs")).expanduser()
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d')}.log"

# Borrar logs de más de LOG_RETENTION_DAYS días
_LOG_RETENTION = int(os.getenv("LOG_RETENTION_DAYS", "30"))
for _log in LOG_DIR.glob("run_*.log"):
    _edad = (datetime.now() - datetime.fromtimestamp(_log.stat().st_mtime)).days
    if _edad > _LOG_RETENTION:
        _log.unlink()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


def paso_backup():
    """Hace una copia de seguridad de la BD. Mantiene solo los ultimos BACKUP_COUNT backups."""
    import shutil
    from db import DB_NAME
    db_path = Path(DB_NAME)
    if not db_path.exists():
        log.info("-- backup: BD no existe todavia, se omite")
        return

    backup_dir = Path(os.getenv("BACKUP_DIR", Path(__file__).parent / "backups")).expanduser()
    backup_dir.mkdir(parents=True, exist_ok=True)

    nombre = f"mercadona_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    destino = backup_dir / nombre
    shutil.copy2(db_path, destino)
    log.info(f"-- backup: {destino.name}")

    # Rotar: conservar solo los ultimos N backups
    backup_count = int(os.getenv("BACKUP_COUNT", "30"))
    backups = sorted(backup_dir.glob("mercadona_*.db"))
    for viejo in backups[:-backup_count]:
        viejo.unlink()
        log.info(f"-- backup: eliminado {viejo.name}")


def paso_retrieve(dias=None):
    """Descarga PDFs del correo. Devuelve True si termina sin error."""
    log.info("── retrieve: descargando tickets del correo...")
    try:
        from retrieve import download_attachments
        download_attachments(dias=dias)
        log.info("── retrieve: OK")
        return True
    except Exception as e:
        log.error(f"── retrieve: ERROR — {e}")
        log.error("   El proceso continúa con los PDFs que ya estén en SAVE_DIR.")
        return False


def paso_main():
    """
    Importa los PDFs de SAVE_DIR a la BD.
    Devuelve el número de tickets nuevos importados.
    """
    log.info("── main: importando PDFs...")
    try:
        import main as _main
        from db import crear_base_datos
        crear_base_datos()

        save_dir = _main.SAVE_DIR
        if not save_dir or not save_dir.is_dir():
            log.error("── main: SAVE_DIR no definido o no existe. Comprueba el .env.")
            return 0

        pdfs = sorted(p for p in save_dir.iterdir() if p.suffix.lower() == ".pdf")
        if not pdfs:
            log.info("── main: no hay PDFs nuevos.")
            return 0

        log.info(f"── main: {len(pdfs)} PDF(s) encontrado(s).")
        nuevos = 0
        for pdf in pdfs:
            resultado = _main.procesar_pdf(str(pdf))
            if resultado is True:
                nuevos += 1

        log.info(f"── main: {nuevos} ticket(s) nuevo(s) importado(s).")
        return nuevos

    except Exception as e:
        log.error(f"── main: ERROR — {e}")
        return 0


def paso_stats():
    """Regenera el informe HTML. Devuelve True si termina sin error."""
    log.info("── stats: generando informe...")
    try:
        import stats as _stats
        from pathlib import Path as _Path
        import os as _os

        output_dir = _Path(_os.getenv("OUTPUT_DIR", _Path(__file__).parent)).expanduser()
        output     = str(output_dir / "informe.html")

        estadisticas = _stats.obtener_estadisticas()
        html = _stats.generar_html(estadisticas)
        with open(output, "w", encoding="utf-8") as f:
            f.write(html)

        log.info(f"── stats: informe generado → {output}")
        return True
    except Exception as e:
        log.error(f"── stats: ERROR — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Orquestador del Mercadona Ticket Analyzer.",
        epilog="""
Ejemplos:
  python3 run.py                   Ciclo completo: retrieve + main + stats
  python3 run.py --sin-retrieve    Solo main + stats (PDFs ya descargados)
  python3 run.py --dias 7          Descarga solo los últimos 7 días
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sin-retrieve", action="store_true",
                        help="Omite la descarga del correo, procesa lo que haya en SAVE_DIR")
    parser.add_argument("--dias", type=int, default=None, metavar="N",
                        help="Número de días hacia atrás a buscar en el correo")
    args = parser.parse_args()

    log.info("═" * 50)
    log.info("Mercadona Ticket Analyzer — inicio")
    log.info("═" * 50)

    # ── Paso 0: backup de la BD ──
    paso_backup()

    # ── Paso 1: retrieve ──
    retrieve_ok = True
    if not args.sin_retrieve:
        retrieve_ok = paso_retrieve(dias=args.dias)
    else:
        log.info("── retrieve: omitido (--sin-retrieve)")

    # ── Paso 2: main ──
    nuevos = paso_main()

    # ── Paso 3: stats ──
    paso_stats()

    log.info("═" * 50)
    log.info(f"Fin. Tickets nuevos importados: {nuevos}  ·  Log: {log_file}")
    log.info("═" * 50)


if __name__ == "__main__":
    main()
