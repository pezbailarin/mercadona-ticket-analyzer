#!/usr/bin/env python3
"""
main.py — Punto de entrada del Mercadona Ticket Analyzer.

Uso:
    python3 main.py ticket.pdf          # procesar un único ticket
    python3 main.py carpeta_con_pdfs/   # procesar todos los PDFs de una carpeta
"""

import sys
import os
import shutil
import sqlite3
from pathlib import Path
from db import crear_base_datos, obtener_conexion
from parser import leer_pdf, parsear_ticket

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Carpetas configurables en .env
_DIR_BASE     = Path(__file__).parent
SAVE_DIR      = Path(os.getenv("SAVE_DIR", "")).expanduser()          # carpeta de entrada (retrieve.py)
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", _DIR_BASE / "tickets_procesados")).expanduser()
ERROR_DIR     = Path(os.getenv("ERROR_DIR",     _DIR_BASE / "tickets_error")).expanduser()


def obtener_o_crear_tarjeta(ultimos4):
    """
    Devuelve el ID de la tarjeta con los últimos 4 dígitos indicados.
    Si no existe, la crea y devuelve el ID recién generado.
    """
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM tarjetas WHERE ultimos4 = ?", (ultimos4,))
    row = cursor.fetchone()

    if row:
        conn.close()
        return row[0]

    # La tarjeta no existe: la insertamos sin descripción (se puede rellenar manualmente)
    cursor.execute(
        "INSERT INTO tarjetas (ultimos4, descripcion) VALUES (?, ?)",
        (ultimos4, None)
    )
    conn.commit()
    tarjeta_id = cursor.lastrowid
    conn.close()
    return tarjeta_id


def obtener_o_crear_producto(cursor, descripcion):
    """
    Devuelve el ID del producto con esa descripción exacta.
    Si no existe en el catálogo, lo inserta y devuelve el nuevo ID.
    Así cada producto queda registrado una sola vez, permitiendo agrupar
    compras del mismo artículo entre diferentes tickets.
    """
    cursor.execute("SELECT id FROM productos WHERE descripcion = ?", (descripcion,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("INSERT INTO productos (descripcion) VALUES (?)", (descripcion,))
    return cursor.lastrowid


def guardar_ticket(datos):
    """
    Inserta un ticket y sus líneas en la base de datos.
    Si el número de factura ya existe, muestra un aviso y no hace nada.
    """
    conn = obtener_conexion()
    cursor = conn.cursor()

    tarjeta_id = obtener_o_crear_tarjeta(datos["ultimos4"])

    try:
        cursor.execute("""
            INSERT INTO tickets
            (numero_ticket, datetime, tienda, codigo_postal, total, tarjeta_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datos["numero_ticket"],
            datos["datetime"],
            datos["tienda"],
            datos.get("codigo_postal"),   # puede ser None si el PDF no lo incluye
            datos["total"],
            tarjeta_id
        ))

    except sqlite3.IntegrityError:
        # El UNIQUE sobre numero_ticket evita duplicados
        print("⚠️  Este ticket ya está importado.")
        conn.close()
        return "duplicado"

    ticket_id = cursor.lastrowid

    # Insertar cada línea del ticket y enlazarla con el catálogo de productos
    for linea in datos["lineas"]:
        producto_id = obtener_o_crear_producto(cursor, linea["descripcion"])

        cursor.execute("""
            INSERT INTO lineas_ticket
            (ticket_id, descripcion_original, producto_id, cantidad, precio_unitario, importe, es_peso)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket_id,
            linea["descripcion"],
            producto_id,
            linea["cantidad"],
            linea["precio_unitario"],
            linea["importe"],
            1 if linea["es_peso"] else 0
        ))

    conn.commit()
    conn.close()
    print(f"✅ Ticket {datos['numero_ticket']} guardado correctamente.")
    return True


def procesar_pdf(ruta_pdf):
    """Lee, parsea y guarda un único fichero PDF de ticket. Si tiene éxito, mueve el PDF."""
    print(f"📄 Procesando: {ruta_pdf}")
    texto = leer_pdf(ruta_pdf)
    datos = parsear_ticket(texto)

    # Validación básica: campos mínimos imprescindibles
    campos_requeridos = ("numero_ticket", "ultimos4", "datetime")
    if not all(c in datos for c in campos_requeridos):
        print("❌ No se pudo interpretar correctamente el ticket.")
        ERROR_DIR.mkdir(parents=True, exist_ok=True)
        destino_err = ERROR_DIR / Path(ruta_pdf).name
        shutil.move(ruta_pdf, str(destino_err))
        print(f"   → Movido a {ERROR_DIR}/ para revisión manual")
        return

    guardado = guardar_ticket(datos)

    if guardado in (True, "duplicado"):
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        destino = PROCESSED_DIR / Path(ruta_pdf).name
        shutil.move(ruta_pdf, str(destino))
        if guardado == "duplicado":
            print(f"   → Movido a {PROCESSED_DIR}/ (ya estaba importado)")
        else:
            print(f"   → Movido a {PROCESSED_DIR}/")

    return guardado  # True | "duplicado" | False | None


if __name__ == "__main__":
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Importa tickets de Mercadona (PDF) a la base de datos SQLite.",
        epilog="""
Ejemplos:
  python3 main.py                         Procesa la carpeta SAVE_DIR del .env
  python3 main.py ticket.pdf              Importa un único PDF
  python3 main.py ~/Descargas/mercadona/  Importa todos los PDFs de una carpeta

PDFs procesados → PROCESSED_DIR (por defecto: tickets_procesados/)
PDFs con error  → ERROR_DIR     (por defecto: tickets_error/)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "ruta", nargs="?", default=None,
        help="Fichero PDF o carpeta con PDFs (por defecto: SAVE_DIR del .env)"
    )
    args = parser.parse_args()

    crear_base_datos()

    if args.ruta:
        ruta = args.ruta
    elif SAVE_DIR and SAVE_DIR.is_dir():
        ruta = str(SAVE_DIR)
        print(f"📂 Usando carpeta de entrada: {ruta}")
    else:
        print("❌ No se indicó ninguna ruta y SAVE_DIR no está definido o no existe en el .env.")
        sys.exit(1)

    if os.path.isdir(ruta):
        # Modo carpeta: procesar todos los PDFs encontrados
        pdfs = sorted(f for f in os.listdir(ruta) if f.lower().endswith(".pdf"))
        if not pdfs:
            print("⚠️  No se encontraron ficheros PDF en la carpeta.")
            sys.exit(0)
        for nombre in pdfs:
            procesar_pdf(os.path.join(ruta, nombre))
    elif os.path.isfile(ruta):
        procesar_pdf(ruta)
    else:
        print(f"❌ No se encuentra el fichero o carpeta: {ruta}")
        sys.exit(1)
