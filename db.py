import sqlite3
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ruta a la base de datos, configurable en .env como DB_PATH
DB_NAME = str(Path(os.getenv("DB_PATH", "mercadona.db")))


def obtener_conexion():
    """Devuelve una conexión a la base de datos con claves foráneas activadas."""
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def crear_base_datos():
    """Crea todas las tablas e índices si no existen."""
    conn = obtener_conexion()
    c = conn.cursor()

    # Tarjetas de pago (identificadas por los últimos 4 dígitos)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tarjetas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ultimos4    INTEGER NOT NULL UNIQUE CHECK(ultimos4 BETWEEN 0 AND 9999),
            descripcion TEXT
        )
    """)

    # Un ticket por compra
    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_ticket  TEXT     NOT NULL UNIQUE,
            datetime       DATETIME,
            tienda         TEXT,
            codigo_postal  TEXT,
            total          REAL     NOT NULL,
            tarjeta_id     INTEGER  NOT NULL,
            creado_en      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(tarjeta_id) REFERENCES tarjetas(id)
        )
    """)

    # Catálogo de productos únicos detectados en todos los tickets.
    # familia_id permite agrupar por categoría de gasto.
    c.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT    NOT NULL UNIQUE,
            familia_id  INTEGER,
            FOREIGN KEY(familia_id) REFERENCES Familias(Fam_id)
        )
    """)

    # Cada fila es una línea dentro de un ticket.
    # es_peso: 0 = precio por unidad, 1 = precio por kg
    c.execute("""
        CREATE TABLE IF NOT EXISTS lineas_ticket (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id            INTEGER NOT NULL,
            descripcion_original TEXT    NOT NULL,
            producto_id          INTEGER,
            cantidad             REAL    NOT NULL,
            precio_unitario      REAL,
            importe              REAL    NOT NULL,
            es_peso              INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(ticket_id)   REFERENCES tickets(id) ON DELETE CASCADE,
            FOREIGN KEY(producto_id) REFERENCES productos(id)
        )
    """)

    # Categorías de producto (cargadas desde familias.sql)
    c.execute("""
        CREATE TABLE IF NOT EXISTS Familias (
            Fam_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            Descripcion TEXT NOT NULL,
            Emoji       TEXT
        )
    """)

    # Índices para las búsquedas más frecuentes
    c.execute("CREATE INDEX IF NOT EXISTS idx_tickets_numero     ON tickets(numero_ticket)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_lineas_producto    ON lineas_ticket(producto_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_lineas_descripcion ON lineas_ticket(descripcion_original)")

    # Familias de producto — se insertan solo si la tabla está vacía
    c.execute("SELECT COUNT(*) FROM Familias")
    if c.fetchone()[0] == 0:
        familias = [
            (1,  'Frutas y verduras',          '🥦'),
            (2,  'Carne y charcutería',         '🥩'),
            (3,  'Pescado y marisco',            '🐟'),
            (4,  'Lácteos y huevos',             '🥛'),
            (5,  'Pan y bollería',               '🍞'),
            (6,  'Conservas y legumbres',        '🥫'),
            (7,  'Pasta, arroz y cereales',      '🍝'),
            (8,  'Aceites, salsas y condimentos','🫙'),
            (9,  'Snacks y dulces',              '🍫'),
            (10, 'Bebidas',                      '🧃'),
            (11, 'Congelados',                   '🧊'),
            (12, 'Droguería y limpieza',         '🧹'),
            (13, 'Higiene y cuidado personal',   '🧴'),
            (14, 'Otras',                        '🗂️'),
            (15, 'Comidas preparadas',           '🥘'),
        ]
        c.executemany(
            "INSERT INTO Familias (Fam_id, Descripcion, Emoji) VALUES (?, ?, ?)",
            familias
        )

    conn.commit()
    conn.close()
