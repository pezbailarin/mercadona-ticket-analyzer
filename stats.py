#!/usr/bin/env python3
"""
stats.py — Estadísticas y análisis de los tickets de Mercadona.

Genera un informe HTML interactivo con:
  - Resumen general (gasto total, ticket medio, nº de compras)
  - Gasto por mes
  - Gasto por familia
  - Productos más comprados
  - Productos sin familia asignada
  - Validación de totales (detecta tickets con diferencias)
  - Auto-categorización sugerida por palabras clave

Uso:
    python3 stats.py                  # genera informe.html
    python3 stats.py --sin-familia    # lista productos sin familia asignada
"""

import sqlite3
import os

import argparse

from db import obtener_conexion, DB_NAME
import os as _os
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv as _load; _load()
except ImportError:
    pass
# Directorio de salida del informe HTML (configurable en .env como OUTPUT_DIR)
_OUTPUT_DIR = _Path(_os.getenv("OUTPUT_DIR", _Path(__file__).parent)).expanduser()

CHARTJS_URL   = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
CHARTJS_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chartjs.cache.js")

def obtener_chartjs():
    """
    Devuelve el código de Chart.js como string.
    1. Si existe la caché local, la usa.
    2. Si no, intenta descargarlo y guardarlo en caché.
    3. Si no hay conexión, devuelve un <script src=...> al CDN como fallback.
    """
    if os.path.exists(CHARTJS_CACHE):
        with open(CHARTJS_CACHE, "r") as f:
            return f"<script>\n{f.read()}\n</script>"
    try:
        import urllib.request
        print("📦 Descargando Chart.js (solo la primera vez)...")
        with urllib.request.urlopen(CHARTJS_URL, timeout=10) as resp:
            js = resp.read().decode("utf-8")
        with open(CHARTJS_CACHE, "w") as f:
            f.write(js)
        print(f"   Guardado en caché: {CHARTJS_CACHE}")
        return f"<script>\n{js}\n</script>"
    except Exception:
        # Sin conexión: fallback al CDN (requiere internet al abrir el HTML)
        return f'<script src="{CHARTJS_URL}"></script>'



# ============================================================
# REGLAS DE AUTO-CATEGORIZACIÓN
# Formato: (palabras_clave, familia_id)
# Se evalúan en orden; gana la primera que encaja.
# Las palabras clave se comparan contra la descripción en mayúsculas.
#
# IDs de familias:
#  1 Frutas y verduras          9  Snacks y dulces
#  2 Carne y charcutería       10  Bebidas
#  3 Pescado y marisco         11  Congelados
#  4 Lácteos y huevos          12  Droguería y limpieza
#  5 Pan y bollería            13  Higiene y cuidado personal
#  6 Conservas y legumbres     14  Otras
#  7 Pasta, arroz y cereales   15  Comidas preparadas
#  8 Aceites, salsas y cond.
# ============================================================

def validar_totales():
    """
    Comprueba que la suma de líneas de cada ticket coincide con su total.
    Devuelve lista de dicts con los tickets que presentan diferencias.
    """
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.numero_ticket, t.datetime, t.total,
               ROUND(SUM(l.importe), 2) AS suma_lineas,
               ROUND(t.total - SUM(l.importe), 2) AS diferencia
        FROM tickets t
        JOIN lineas_ticket l ON l.ticket_id = t.id
        GROUP BY t.id
        HAVING ABS(diferencia) > 0.01
    """)
    problemas = [
        {"id": r[0], "numero": r[1], "datetime": r[2],
         "total": r[3], "suma_lineas": r[4], "diferencia": r[5]}
        for r in cursor.fetchall()
    ]
    conn.close()
    return problemas


def productos_sin_familia():
    """Devuelve lista de productos que aún no tienen familia asignada."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.descripcion, ROUND(SUM(l.importe), 2) as gasto_total
        FROM productos p
        JOIN lineas_ticket l ON l.producto_id = p.id
        WHERE p.familia_id IS NULL
        GROUP BY p.id
        ORDER BY gasto_total DESC
    """)
    result = [{"id": r[0], "descripcion": r[1], "gasto_total": r[2]}
              for r in cursor.fetchall()]
    conn.close()
    return result


def obtener_estadisticas():
    """
    Calcula todas las estadísticas necesarias para el informe.
    Devuelve un dict con todos los datos.
    """
    conn = obtener_conexion()
    cursor = conn.cursor()

    stats = {}

    # --- Resumen general ---
    cursor.execute("""
        SELECT COUNT(*) as num_tickets,
               ROUND(SUM(total), 2) as gasto_total,
               ROUND(AVG(total), 2) as ticket_medio,
               MIN(datetime) as primera_compra,
               MAX(datetime) as ultima_compra
        FROM tickets
    """)
    r = cursor.fetchone()
    stats["resumen"] = {
        "num_tickets":    r[0],
        "gasto_total":    r[1],
        "ticket_medio":   r[2],
        "primera_compra": r[3],
        "ultima_compra":  r[4]
    }

    # Fecha e importe del último ticket
    cursor.execute("""
        SELECT datetime, total FROM tickets
        ORDER BY datetime DESC LIMIT 1
    """)
    ult = cursor.fetchone()
    stats["resumen"]["ultima_fecha"]  = ult[0] if ult else "—"
    stats["resumen"]["ultima_total"]  = ult[1] if ult else 0

    # Gasto medio mensual: gasto total dividido entre meses con datos
    cursor.execute("""
        SELECT COUNT(DISTINCT strftime('%Y-%m', datetime)) as num_meses,
               ROUND(SUM(total), 2) as gasto_total
        FROM tickets
    """)
    rm = cursor.fetchone()
    num_meses = rm[0] or 1
    stats["resumen"]["gasto_medio_mensual"] = round(rm[1] / num_meses, 2)

    # --- Gasto por mes ---
    cursor.execute("""
        SELECT strftime('%Y-%m', datetime) as mes,
               COUNT(*) as num_tickets,
               ROUND(SUM(total), 2) as gasto
        FROM tickets
        GROUP BY mes
        ORDER BY mes
    """)
    stats["por_mes"] = [
        {"mes": r[0], "num_tickets": r[1], "gasto": r[2]}
        for r in cursor.fetchall()
    ]

    # --- Gasto por familia ---
    cursor.execute("""
        SELECT f.Emoji, f.Descripcion,
               ROUND(SUM(l.importe), 2) as gasto,
               COUNT(DISTINCT l.id) as num_lineas
        FROM lineas_ticket l
        JOIN productos p ON l.producto_id = p.id
        JOIN Familias f ON p.familia_id = f.Fam_id
        GROUP BY f.Fam_id
        ORDER BY gasto DESC
    """)
    stats["por_familia"] = [
        {"emoji": r[0], "nombre": r[1], "gasto": r[2], "num_lineas": r[3]}
        for r in cursor.fetchall()
    ]

    # Calcular porcentajes sobre el gasto total categorizado
    gasto_categorizado = sum(f["gasto"] for f in stats["por_familia"])
    for f in stats["por_familia"]:
        f["pct"] = round(f["gasto"] / gasto_categorizado * 100, 1) if gasto_categorizado else 0

    # --- Top 15 productos por importe acumulado ---
    cursor.execute("""
        SELECT p.descripcion, f.Emoji, f.Descripcion as familia,
               COUNT(l.id) as veces,
               ROUND(SUM(l.importe), 2) as gasto_total,
               ROUND(AVG(l.precio_unitario), 2) as precio_medio
        FROM lineas_ticket l
        JOIN productos p ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        GROUP BY p.id
        ORDER BY gasto_total DESC
        LIMIT 15
    """)
    stats["top_productos"] = [
        {"descripcion": r[0], "emoji": r[1] or "🗂️", "familia": r[2] or "Sin categoría",
         "veces": r[3], "gasto_total": r[4], "precio_medio": r[5]}
        for r in cursor.fetchall()
    ]

    # --- Productos sin familia ---
    stats["sin_familia"] = productos_sin_familia()

    # --- Validación de totales ---
    stats["tickets_con_diferencias"] = validar_totales()

    # --- Gasto por tienda ---
    cursor.execute("""
        SELECT tienda, codigo_postal,
               COUNT(*) as num_tickets,
               ROUND(SUM(total), 2) as gasto_total
        FROM tickets
        GROUP BY tienda
        ORDER BY gasto_total DESC
    """)
    stats["por_tienda"] = [
        {"tienda": r[0], "cp": r[1], "num_tickets": r[2], "gasto_total": r[3]}
        for r in cursor.fetchall()
    ]

    # --- Alertas de subida de precio ---
    cursor.execute("""
        SELECT p.id, p.descripcion,
               COALESCE(f.Descripcion, 'Sin categoría') as familia,
               COALESCE(f.Emoji, '🗂️') as emoji,
               p.familia_id,
               l.precio_unitario, t.datetime
        FROM lineas_ticket l
        JOIN tickets t ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        ORDER BY p.id, t.datetime
    """)
    from collections import defaultdict
    hist = defaultdict(list)
    meta = {}
    for pid, desc, fam, emoji, fam_id, precio, dt in cursor.fetchall():
        hist[pid].append((dt[:10], precio))
        meta[pid] = {"desc": desc, "fam": fam, "emoji": emoji, "fam_id": fam_id}

    FAMILIAS_ESTACIONALES = {1}   # Frutas y verduras (fam_id=1)
    UMBRAL_NORMAL     = 15.0       # % de subida para alertar
    UMBRAL_ESTACIONAL = 25.0       # % más permisivo para productos estacionales
    MIN_COMPRAS       = 3          # necesitamos al menos 3 puntos

    alertas = []
    for pid, puntos in hist.items():
        if len(puntos) < MIN_COMPRAS:
            continue
        precios    = [p for _, p in puntos]
        actual     = precios[-1]
        fecha_act  = puntos[-1][0]
        media_hist = sum(precios[:-1]) / len(precios[:-1])
        if media_hist <= 0:
            continue
        pct = (actual - media_hist) / media_hist * 100
        m = meta[pid]
        umbral = UMBRAL_ESTACIONAL if m["fam_id"] in FAMILIAS_ESTACIONALES else UMBRAL_NORMAL
        if pct >= umbral:
            alertas.append({
                "desc":       m["desc"],
                "familia":    m["fam"],
                "emoji":      m["emoji"],
                "fam_id":     m["fam_id"],
                "pct":        round(pct, 1),
                "actual":     actual,
                "media_hist": round(media_hist, 3),
                "fecha":      fecha_act,
                "estacional": m["fam_id"] in FAMILIAS_ESTACIONALES,
                "n_compras":  len(puntos),
            })
    alertas.sort(key=lambda a: a["pct"], reverse=True)
    stats["alertas_precio"] = alertas

    # --- Alertas de subida de precio ---
    cursor.execute("""
        SELECT p.id, p.descripcion,
               COALESCE(f.Descripcion, 'Sin categoría') as familia,
               COALESCE(f.Emoji, '🗂️') as emoji,
               p.familia_id,
               l.precio_unitario, t.datetime
        FROM lineas_ticket l
        JOIN tickets t ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        ORDER BY p.id, t.datetime
    """)
    from collections import defaultdict
    _hist = defaultdict(list)
    _meta = {}
    for _pid, _desc, _fam, _emoji, _fam_id, _precio, _dt in cursor.fetchall():
        _hist[_pid].append((_dt[:10], _precio))
        _meta[_pid] = {"desc": _desc, "fam": _fam, "emoji": _emoji, "fam_id": _fam_id}

    FAM_ESTACIONALES  = {1}    # Frutas y verduras
    UMBRAL_NORMAL     = 15.0
    UMBRAL_ESTACIONAL = 25.0
    MIN_COMPRAS       = 3

    alertas = []
    for _pid, _puntos in _hist.items():
        if len(_puntos) < MIN_COMPRAS:
            continue
        _precios   = [p for _, p in _puntos]
        _actual    = _precios[-1]
        _fecha_act = _puntos[-1][0]
        _media     = sum(_precios[:-1]) / len(_precios[:-1])
        if _media <= 0:
            continue
        _pct = (_actual - _media) / _media * 100
        _m   = _meta[_pid]
        _umbral = UMBRAL_ESTACIONAL if _m["fam_id"] in FAM_ESTACIONALES else UMBRAL_NORMAL
        if _pct >= _umbral:
            alertas.append({
                "desc":       _m["desc"],
                "familia":    _m["fam"],
                "emoji":      _m["emoji"],
                "fam_id":     _m["fam_id"],
                "pct":        round(_pct, 1),
                "actual":     _actual,
                "media_hist": round(_media, 3),
                "fecha":      _fecha_act,
                "estacional": _m["fam_id"] in FAM_ESTACIONALES,
                "n_compras":  len(_puntos),
            })
    alertas.sort(key=lambda a: a["pct"], reverse=True)
    stats["alertas_precio"] = alertas

    conn.close()
    return stats



def obtener_records():
    """Calcula los récords y curiosidades para el informe."""
    conn = obtener_conexion()
    cur = conn.cursor()
    rec = {}

    # Día de locura
    cur.execute("""
        SELECT DATE(datetime) as dia, COUNT(*) as n,
               GROUP_CONCAT(numero_ticket, ', ') as tickets
        FROM tickets GROUP BY dia ORDER BY n DESC, dia DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["dia_locura"] = {"dia": r[0], "n": r[1], "tickets": r[2]}

    # Ticket más caro
    cur.execute("SELECT numero_ticket, datetime, total FROM tickets ORDER BY total DESC LIMIT 1")
    r = cur.fetchone()
    if r:
        rec["ticket_caro"] = {"numero": r[0], "fecha": r[1][:10], "total": r[2]}

    # Ermitaño: mayor tiempo entre compras
    cur.execute("""
        SELECT a.datetime, b.datetime,
               CAST((JULIANDAY(b.datetime) - JULIANDAY(a.datetime)) AS INTEGER) as dias
        FROM tickets a JOIN tickets b ON b.id = (
            SELECT id FROM tickets WHERE datetime > a.datetime ORDER BY datetime LIMIT 1
        )
        ORDER BY dias DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["ermitano"] = {"desde": r[0][:10], "hasta": r[1][:10], "dias": r[2]}

    # Despistado: menor tiempo entre tickets del mismo día
    cur.execute("""
        SELECT a.datetime, b.datetime,
               ROUND((JULIANDAY(b.datetime) - JULIANDAY(a.datetime)) * 24 * 60, 0) as minutos
        FROM tickets a JOIN tickets b
          ON DATE(a.datetime) = DATE(b.datetime) AND b.datetime > a.datetime
        ORDER BY minutos ASC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["despistado"] = {"t1": r[0][11:16], "t2": r[1][11:16],
                             "dia": r[0][:10], "minutos": int(r[2])}

    # La joya: item más caro
    cur.execute("""
        SELECT p.descripcion, l.precio_unitario, l.es_peso, t.datetime, t.numero_ticket
        FROM lineas_ticket l
        JOIN productos p ON l.producto_id = p.id
        JOIN tickets t ON l.ticket_id = t.id
        ORDER BY l.precio_unitario DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        unidad = "€/kg" if r[2] else "€"
        rec["joya"] = {"desc": r[0], "precio": r[1], "unidad": unidad,
                       "fecha": r[3][:10], "numero": r[4]}

    # Monocromático: ticket más caro con todos los productos de una sola familia
    cur.execute("""
        SELECT t.numero_ticket, t.datetime, t.total,
               f.Descripcion, f.Emoji,
               COUNT(DISTINCT p.familia_id) as nf
        FROM tickets t
        JOIN lineas_ticket l ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        WHERE p.familia_id IS NOT NULL
        GROUP BY t.id HAVING nf = 1
        ORDER BY t.total DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["monocromatico"] = {"numero": r[0], "fecha": r[1][:10],
                                "total": r[2], "familia": r[3], "emoji": r[4]}

    # Logística: ticket con más productos distintos
    cur.execute("""
        SELECT t.numero_ticket, t.datetime, COUNT(DISTINCT l.producto_id) as n
        FROM tickets t JOIN lineas_ticket l ON l.ticket_id = t.id
        GROUP BY t.id ORDER BY n DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["logistica"] = {"numero": r[0], "fecha": r[1][:10], "n": r[2]}

    # Por los pelos: ticket a la hora más tarde
    cur.execute("SELECT numero_ticket, datetime, TIME(datetime) FROM tickets ORDER BY TIME(datetime) DESC LIMIT 1")
    r = cur.fetchone()
    if r:
        rec["por_los_pelos"] = {"numero": r[0], "fecha": r[1][:10], "hora": r[2][:5]}

    # Madrugador: ticket más temprano
    cur.execute("SELECT numero_ticket, datetime, TIME(datetime) FROM tickets ORDER BY TIME(datetime) ASC LIMIT 1")
    r = cur.fetchone()
    if r:
        rec["madrugador"] = {"numero": r[0], "fecha": r[1][:10], "hora": r[2][:5]}

    # Acaparador: más unidades del mismo artículo en un ticket (solo unidades, no peso)
    cur.execute("""
        SELECT t.numero_ticket, t.datetime, p.descripcion, ROUND(l.cantidad, 0) as cant
        FROM lineas_ticket l
        JOIN tickets t ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        WHERE l.es_peso = 0
        ORDER BY l.cantidad DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["acaparador"] = {"numero": r[0], "fecha": r[1][:10],
                             "desc": r[2], "cant": int(r[3])}

    # Explorador: ticket con más categorías distintas
    cur.execute("""
        SELECT t.numero_ticket, t.datetime, COUNT(DISTINCT p.familia_id) as n
        FROM tickets t
        JOIN lineas_ticket l ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        WHERE p.familia_id IS NOT NULL
        GROUP BY t.id ORDER BY n DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["explorador"] = {"numero": r[0], "fecha": r[1][:10], "n": r[2]}

    # Siempre fiel: producto comprado en más tickets distintos
    cur.execute("""
        SELECT p.descripcion, COUNT(DISTINCT l.ticket_id) as n
        FROM lineas_ticket l JOIN productos p ON l.producto_id = p.id
        GROUP BY p.id ORDER BY n DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["siempre_fiel"] = {"desc": r[0], "n": r[1]}

    # Día del juicio: fecha con más artículos de Droguería (fam_id=12)
    cur.execute("""
        SELECT DATE(t.datetime) as dia,
               CAST(SUM(CASE WHEN l.es_peso = 0 THEN l.cantidad ELSE 1 END) AS INTEGER) as u
        FROM lineas_ticket l
        JOIN tickets t ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        WHERE p.familia_id = 12
        GROUP BY dia ORDER BY u DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["juicio_final"] = {"dia": r[0], "unidades": r[1]}

    # Minimalista: ticket con menos líneas (al menos 2)
    cur.execute("""
        SELECT t.numero_ticket, t.datetime, COUNT(l.id) as n
        FROM tickets t JOIN lineas_ticket l ON l.ticket_id = t.id
        GROUP BY t.id HAVING n >= 2
        ORDER BY n ASC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["minimalista"] = {"numero": r[0], "fecha": r[1][:10], "n": r[2]}

    # Mi segunda casa: tienda con más gasto
    cur.execute("""
        SELECT tienda, ROUND(SUM(total), 2) as gasto, COUNT(*) as visitas
        FROM tickets GROUP BY tienda ORDER BY gasto DESC LIMIT 1
    """)
    r = cur.fetchone()
    if r:
        rec["segunda_casa"] = {"tienda": r[0], "gasto": r[1], "visitas": r[2]}

    conn.close()
    return rec

def cargar_datos_completos():
    """
    Carga todos los tickets y líneas de la BD en una estructura JSON-serializable
    para ser embebida en el HTML y filtrada en el navegador.
    """
    import json
    conn = obtener_conexion()
    cursor = conn.cursor()

    # Tarjetas (para el filtro)
    cursor.execute("SELECT id, ultimos4, descripcion FROM tarjetas ORDER BY id")
    tarjetas = [
        {"id": r[0], "ultimos4": r[1],
         "label": r[2] if r[2] else f"····{r[1]}"}
        for r in cursor.fetchall()
    ]

    # Tickets — incluye tarjeta_id para poder filtrar
    cursor.execute("""
        SELECT t.id, t.datetime, t.total, t.tienda, t.codigo_postal, t.tarjeta_id
        FROM tickets t
        ORDER BY t.datetime
    """)
    tickets = [
        {"id": r[0], "datetime": r[1], "total": r[2],
         "tienda": r[3], "cp": r[4], "tarjeta_id": r[5],
         "mes": r[1][:7]}
        for r in cursor.fetchall()
    ]

    # Líneas enriquecidas con familia
    cursor.execute("""
        SELECT l.ticket_id, l.importe, l.cantidad, l.precio_unitario, l.es_peso,
               p.descripcion, p.familia_id,
               COALESCE(f.Descripcion, 'Sin categoría') as familia,
               COALESCE(f.Emoji, '🗂️') as emoji
        FROM lineas_ticket l
        JOIN productos p ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
    """)
    lineas = [
        {"tid": r[0], "importe": r[1], "cantidad": r[2],
         "precio_unitario": r[3], "es_peso": r[4],
         "descripcion": r[5], "familia_id": r[6],
         "familia": r[7], "emoji": r[8]}
        for r in cursor.fetchall()
    ]

    # Familias (para el orden y colores)
    cursor.execute("SELECT Fam_id, Descripcion, Emoji FROM Familias ORDER BY Fam_id")
    familias = [{"id": r[0], "nombre": r[1], "emoji": r[2]} for r in cursor.fetchall()]

    # Historial de precios por producto (para gráfico de evolución)
    cursor.execute("""
        SELECT p.id, p.descripcion,
               COALESCE(f.Emoji, '🗂️') as emoji,
               COALESCE(f.Descripcion, 'Sin categoría') as familia,
               t.datetime, l.precio_unitario, l.es_peso
        FROM lineas_ticket l
        JOIN tickets t ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        ORDER BY p.descripcion, t.datetime
    """)
    # Agrupar por producto
    precios_raw = cursor.fetchall()
    precios = {}
    for pid, desc, emoji, familia, dt, precio, es_peso in precios_raw:
        if desc not in precios:
            precios[desc] = {"emoji": emoji, "familia": familia, "es_peso": es_peso, "puntos": []}
        precios[desc]["puntos"].append({"d": dt[:10], "p": precio})

    conn.close()
    return json.dumps({"tickets": tickets, "lineas": lineas, "familias": familias,
                       "precios": precios, "tarjetas": tarjetas},
                      ensure_ascii=False)


def generar_html(stats):
    """Genera el informe HTML interactivo con filtros de fecha en el navegador."""
    from datetime import datetime as _dt
    fecha_generacion = _dt.now().strftime("%d/%m/%Y %H:%M")

    records = obtener_records()

    r = stats["resumen"]

    alertas_html = ""
    if stats["tickets_con_diferencias"]:
        items = "".join(
            f"<li>Ticket <code>{d['numero']}</code> ({d['datetime']}): "
            f"total {d['total']:.2f} € vs suma líneas {d['suma_lineas']:.2f} € "
            f"<strong>(diff: {d['diferencia']:+.2f} €)</strong></li>"
            for d in stats["tickets_con_diferencias"]
        )
        alertas_html = f"""
        <div class="alert">
            ⚠️ <strong>{len(stats['tickets_con_diferencias'])} ticket(s) con diferencias entre total y suma de líneas</strong>
            (posibles descuentos o promociones no parseados):
            <ul>{items}</ul>
        </div>"""

    sin_fam_html = ""
    if stats["sin_familia"]:
        items = "".join(
            f"<li><code>{p['descripcion']}</code> — {p['gasto_total']:.2f} € acumulados</li>"
            for p in stats["sin_familia"]
        )
        sin_fam_html = f"""
        <div class="alert alert-info">
            ℹ️ <strong>{len(stats['sin_familia'])} producto(s) sin familia asignada.</strong>
            Ejecuta <code>python3 categorizar.py</code> para asignarles una categoría.
            <ul>{items}</ul>
        </div>"""



    # ── HTML de récords ──────────────────────────────────────────
    def _rec_card(emoji, titulo, valor, detalle):
        return f"""
        <div class="record-card">
          <div class="rec-header">{emoji} {titulo}</div>
          <div class="rec-value">{valor}</div>
          <div class="rec-detail">{detalle}</div>
        </div>"""

    rec = records
    rec_cards = ""

    if rec.get("dia_locura"):
        rd = rec["dia_locura"]
        n_txt = f"{rd['n']} ticket{'s' if rd['n'] > 1 else ''}"
        rec_cards += _rec_card("📅", "Día de locura", n_txt,
            f"El {rd['dia']} se hicieron {rd['n']} compras distintas.")

    if rec.get("ticket_caro"):
        rd = rec["ticket_caro"]
        rec_cards += _rec_card("💰", "Ticket más caro", f"{rd['total']:.2f} €",
            f"Ticket {rd['numero']} · {rd['fecha']}")

    if rec.get("ermitano"):
        rd = rec["ermitano"]
        rec_cards += _rec_card("⌛", "Ermitaño", f"{rd['dias']} días sin comprar",
            f"Entre el {rd['desde']} y el {rd['hasta']}")

    if rec.get("despistado"):
        rd = rec["despistado"]
        rec_cards += _rec_card("⚡", "Despistado", f"{rd['minutos']} min entre compras",
            f"El {rd['dia']}: una a las {rd['t1']} y otra a las {rd['t2']}")

    if rec.get("joya"):
        rd = rec["joya"]
        rec_cards += _rec_card("💎", "La joya de la corona",
            f"{rd['precio']:.2f} {rd['unidad']}",
            f"{rd['desc']} · {rd['fecha']}")

    if rec.get("monocromatico"):
        rd = rec["monocromatico"]
        rec_cards += _rec_card("🎨", "Monocromático",
            f"{rd['emoji']} {rd['familia']} · {rd['total']:.2f} €",
            f"Ticket {rd['numero']} · {rd['fecha']} · todo de una sola categoría")

    if rec.get("logistica"):
        rd = rec["logistica"]
        rec_cards += _rec_card("🏗️", "Logística Nivel Pro",
            f"{rd['n']} productos distintos",
            f"Ticket {rd['numero']} · {rd['fecha']}")

    if rec.get("por_los_pelos"):
        rd = rec["por_los_pelos"]
        rec_cards += _rec_card("🕒", "Por los pelos",
            f"A las {rd['hora']}",
            f"Ticket {rd['numero']} · {rd['fecha']}")

    if rec.get("madrugador"):
        rd = rec["madrugador"]
        rec_cards += _rec_card("🌅", "Madrugador",
            f"A las {rd['hora']}",
            f"Ticket {rd['numero']} · {rd['fecha']}")

    if rec.get("acaparador"):
        rd = rec["acaparador"]
        rec_cards += _rec_card("🧻", "Acaparador",
            f"{rd['cant']} × {rd['desc']}",
            f"Ticket {rd['numero']} · {rd['fecha']}")

    if rec.get("explorador"):
        rd = rec["explorador"]
        rec_cards += _rec_card("🧭", "Explorador",
            f"{rd['n']} categorías distintas",
            f"Ticket {rd['numero']} · {rd['fecha']}")

    if rec.get("siempre_fiel"):
        rd = rec["siempre_fiel"]
        rec_cards += _rec_card("🔁", "Siempre fiel",
            rd['desc'],
            f"Comprado en {rd['n']} tickets distintos")

    if rec.get("juicio_final"):
        rd = rec["juicio_final"]
        rec_cards += _rec_card("🧹", "Día del juicio final",
            f"{rd['unidades']} artículos de limpieza",
            f"El {rd['dia']}")

    if rec.get("minimalista"):
        rd = rec["minimalista"]
        rec_cards += _rec_card("🧮", "Minimalista",
            f"Solo {rd['n']} líneas",
            f"Ticket {rd['numero']} · {rd['fecha']}")

    if rec.get("segunda_casa"):
        rd = rec["segunda_casa"]
        rec_cards += _rec_card("🏠", "Mi segunda casa",
            rd['tienda'],
            f"{rd['gasto']:.2f} € en {rd['visitas']} visitas")

    records_section_html = f"""
  <div class="section">
    <h2>🏆 Récords</h2>
    <div class="records-grid">
      {rec_cards}
    </div>
  </div>"""


    # Alertas de subida de precio
    alertas_precio_html = ""
    if stats.get("alertas_precio"):
        FAM_PESO_VARIABLE = {2}  # Carne — precio por envase, peso variable
        filas_alertas = ""
        for a in stats["alertas_precio"]:
            nota = ""
            if a["fam_id"] in FAM_PESO_VARIABLE:
                nota = ' <span class="alerta-nota">⚠ precio por envase — el peso podría variar entre compras</span>'
            elif a["estacional"]:
                nota = ' <span class="alerta-nota">puede ser estacional</span>'
            filas_alertas += (
                f'<tr>'
                f'<td>{a["emoji"]} {a["desc"]}</td>'
                f'<td class="alerta-fam">{a["familia"]}{nota}</td>'
                f'<td class="num alerta-pct">+{a["pct"]}%</td>'
                f'<td class="num">{a["actual"]:.2f} €</td>'
                f'<td class="num alerta-media">{a["media_hist"]:.2f} €</td>'
                f'<td class="num alerta-n">{a["n_compras"]}x</td>'
                f'</tr>'
            )
        n = len(stats["alertas_precio"])
        alertas_precio_html = f"""
  <details class="section alerta-precio-section">
    <summary><h2>📈 Alertas de precio <span class="alerta-badge">{n}</span></h2></summary>
    <p class="alerta-desc">Productos cuyo último precio supera su media histórica de forma significativa.</p>
    <table>
      <thead><tr>
        <th>Producto</th><th>Familia</th>
        <th style="text-align:right">Subida</th>
        <th style="text-align:right">Último precio</th>
        <th style="text-align:right">Media histórica</th>
        <th style="text-align:right">Compras</th>
      </tr></thead>
      <tbody>{filas_alertas}</tbody>
    </table>
  </details>"""


    datos_json = cargar_datos_completos()

    fam_colores_js = '["#4ade80","#f97316","#38bdf8","#facc15","#a78bfa","#fb7185","#34d399","#60a5fa","#f472b6","#94a3b8","#c084fc","#2dd4bf","#fbbf24","#e879f9","#f87171"]'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mercadona · Informe de gasto</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMiAzMiI+CiAgPHJlY3Qgd2lkdGg9IjMyIiBoZWlnaHQ9IjMyIiByeD0iNyIgZmlsbD0iIzBmMTExNyIvPgogIDwhLS0gTWFuZ28gZGVsIGNhcnJpdG8gLS0+CiAgPGxpbmUgeDE9IjQiIHkxPSI3IiB4Mj0iOCIgeTI9IjciIHN0cm9rZT0iIzRhZGU4MCIgc3Ryb2tlLXdpZHRoPSIyLjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgogIDwhLS0gQ3VlcnBvIGRlbCBjYXJyaXRvIC0tPgogIDxwYXRoIGQ9Ik04IDcgTDEwIDE4IFExMC41IDIwIDEzIDIwIEwyNCAyMCBRMjYgMjAgMjYuNSAxOCBMMjggMTAgTDkuNSAxMCIgCiAgICAgICAgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNGFkZTgwIiBzdHJva2Utd2lkdGg9IjIuMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+CiAgPCEtLSBSdWVkYXMgLS0+CiAgPGNpcmNsZSBjeD0iMTQiIGN5PSIyNCIgcj0iMiIgZmlsbD0iIzRhZGU4MCIvPgogIDxjaXJjbGUgY3g9IjIzIiBjeT0iMjQiIHI9IjIiIGZpbGw9IiM0YWRlODAiLz4KPC9zdmc+">
{obtener_chartjs()}
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
  :root {{
    --bg:      #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --accent:  #4ade80; --accent2: #facc15; --text:   #e2e8f0;
    --muted:   #64748b; --danger:  #f87171; --info:   #38bdf8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif;
         font-weight: 300; line-height: 1.6; padding: 2rem 1rem; }}
  .container {{ max-width: 1000px; margin: 0 auto; }}

  header {{ display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1.5rem;
            border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; }}
  header h1 {{ font-family: 'DM Serif Display', serif; font-size: 2.2rem;
               font-weight: 400; letter-spacing: -0.02em; }}
  header h1 span {{ color: var(--accent); }}
  header .sub {{ color: var(--muted); font-size: 0.9rem; }}

  /* Filtros */
  .filtros {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.1rem 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .filtros-row {{ display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end; }}
  .filtro-grupo {{ display: flex; flex-direction: column; gap: 0.3rem; }}
  .filtro-grupo label {{ font-size: 0.7rem; text-transform: uppercase;
                         letter-spacing: 0.08em; color: var(--muted); }}
  .filtro-grupo input[type=date] {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    border-radius: 7px; padding: 0.4rem 0.7rem; font-family: inherit;
    font-size: 0.875rem; cursor: pointer;
  }}
  .filtro-grupo input[type=date]:focus {{ outline: none; border-color: var(--accent); }}
  .filtros .sep {{ color: var(--border); font-size: 1.2rem; padding-bottom: 0.2rem; }}
  /* Selector año */
  .años-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem; }}
  .btn-año {{
    background: transparent; border: 1px solid var(--border); color: var(--muted);
    border-radius: 7px; padding: 0.3rem 0.9rem; font-family: inherit;
    font-size: 0.85rem; cursor: pointer; transition: all 0.15s;
  }}
  .btn-año:hover {{ border-color: var(--accent); color: var(--accent); }}
  .btn-año.activo {{ background: var(--accent); border-color: var(--accent); color: #0f1117; font-weight: 600; }}
  /* Botones de mes */
  .meses-row {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; min-height: 2rem; }}
  .btn-mes {{
    background: transparent; border: 1px solid var(--border); color: var(--muted);
    border-radius: 7px; padding: 0.25rem 0.7rem; font-family: inherit;
    font-size: 0.8rem; cursor: pointer; transition: all 0.15s; text-transform: capitalize;
  }}
  .btn-mes:hover {{ border-color: var(--accent); color: var(--accent); }}
  .btn-mes.activo {{ background: var(--accent); border-color: var(--accent); color: #0f1117; font-weight: 600; }}
  .btn-mes.vacio {{ opacity: 0.25; cursor: default; pointer-events: none; }}
  /* Botones de tarjeta */
  .tarjetas-row {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.5rem; position: relative; }}
  .btn-tarjeta {{
    background: transparent; border: 1px solid var(--border); color: var(--muted);
    border-radius: 7px; padding: 0.25rem 0.8rem; font-family: inherit;
    font-size: 0.8rem; cursor: pointer; transition: all 0.15s;
  }}
  .btn-tarjeta:hover {{ border-color: var(--accent2); color: var(--accent2); }}
  .btn-tarjeta.activo {{ background: var(--accent2); border-color: var(--accent2); color: #0f1117; font-weight: 600; }}
  .btn-reset {{
    background: transparent; border: 1px solid var(--border); color: var(--muted);
    border-radius: 7px; padding: 0.3rem 0.9rem; font-family: inherit;
    font-size: 0.8rem; cursor: pointer; transition: all 0.15s; display: none;
  }}
  .btn-reset:hover {{ border-color: var(--danger); color: var(--danger); }}
  #filtro-tarjeta-activa {{
    position: absolute; top: 0; right: 0;
    color: var(--accent2); font-size: 0.78rem;
    display: none;
  }}
  #filtro-activo {{
    font-size: 0.78rem; color: var(--accent); margin-left: auto;
    align-self: center; display: none;
  }}
  /* Tabla tickets */
  .ticket-row {{ cursor: pointer; }}
  .ticket-row td {{ transition: background 0.1s; }}
  .ticket-detalle {{ display: none; }}
  .ticket-detalle td {{ background: rgba(255,255,255,0.02); padding: 0; }}
  .ticket-detalle-inner {{ padding: 0.5rem 1rem 0.75rem 2rem; font-size: 0.82rem; }}
  .ticket-detalle-inner table {{ margin-top: 0.4rem; }}
  .ticket-detalle-inner th {{ font-size: 0.68rem; }}
  .ticket-detalle.open {{ display: table-row; }}

  /* KPIs */
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
           gap: 1rem; margin-bottom: 1.5rem; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--border);
          border-radius: 12px; padding: 1.25rem 1.5rem; transition: border-color 0.2s; }}
  .kpi .label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase;
                 letter-spacing: 0.08em; margin-bottom: 0.4rem; }}
  .kpi .value {{ font-size: 1.8rem; font-weight: 600; line-height: 1.1; }}
  .kpi .sub {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.3rem; }}

  /* Secciones */
  .section {{ background: var(--surface); border: 1px solid var(--border);
              border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
  .section h2 {{ font-family: 'DM Serif Display', serif; font-size: 1.2rem;
                 font-weight: 400; margin-bottom: 1.25rem; }}
  .chart-wrap {{ position: relative; height: 240px; }}

  /* Tablas */
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ text-align: left; font-size: 0.7rem; text-transform: uppercase;
        letter-spacing: 0.08em; color: var(--muted); padding: 0 0.75rem 0.75rem;
        border-bottom: 1px solid var(--border); font-weight: 500; }}
  td {{ padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255,255,255,0.02); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .bold {{ font-weight: 600; color: var(--accent); }}
  .emoji {{ font-size: 1rem; margin-right: 0.3rem; }}
  .fam-tag {{ font-size: 0.75rem; color: var(--muted); }}
  .bar-wrap {{ background: var(--border); border-radius: 99px; height: 6px; min-width: 80px; }}
  .bar {{ background: var(--accent); border-radius: 99px; height: 6px; transition: width 0.4s; }}
  .empty-row td {{ color: var(--muted); text-align: center; padding: 1.5rem; }}

  /* Alertas */
  .alert {{ background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.3);
            border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.5rem; font-size: 0.875rem; }}
  .alert ul {{ margin: 0.5rem 0 0 1.25rem; }}
  .alert li {{ margin-bottom: 0.25rem; }}
  .alert small {{ display: block; margin-top: 0.5rem; color: var(--muted); }}
  .alert-info {{ background: rgba(56,189,248,0.08); border-color: rgba(56,189,248,0.3); }}
  code {{ background: var(--border); border-radius: 4px; padding: 0.1em 0.4em; font-size: 0.85em; }}

  /* ── Récords ── */
  .records-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 0.75rem;
    margin-bottom: 1.5rem;
  }}
  .record-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.85rem 1rem;
    cursor: default;
    transition: border-color 0.15s, transform 0.15s;
    position: relative;
  }}
  .record-card:hover {{
    border-color: var(--accent);
    transform: translateY(-2px);
  }}
  .record-card .rec-header {{
    display: flex; align-items: center; gap: 0.5rem;
    font-size: 0.78rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em;
    margin-bottom: 0.35rem;
  }}
  .record-card .rec-value {{
    font-size: 1.05rem; font-weight: 600; color: var(--text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .record-card .rec-detail {{
    display: none;
    position: absolute;
    bottom: calc(100% + 6px); left: 0; right: 0;
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: 8px;
    padding: 0.6rem 0.8rem;
    font-size: 0.82rem;
    color: var(--muted);
    z-index: 10;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    line-height: 1.5;
  }}
  .record-card:hover .rec-detail {{ display: block; }}

  footer {{ text-align: center; color: var(--muted); font-size: 0.78rem;
            margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid var(--border); }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
  .alerta-precio-section {{ border-color: rgba(248,113,113,0.3); }}
  .alerta-precio-section summary {{
    list-style: none; cursor: pointer; display: flex; align-items: center;
    padding: 0.25rem 0; user-select: none;
  }}
  .alerta-precio-section summary::-webkit-details-marker {{ display: none; }}
  .alerta-precio-section summary h2 {{ margin: 0; pointer-events: none; }}
  .alerta-precio-section summary::after {{
    content: '▶'; font-size: 0.7rem; color: var(--muted);
    margin-left: 0.6rem; transition: transform 0.2s;
  }}
  .alerta-precio-section[open] summary::after {{ transform: rotate(90deg); }}
  .alerta-precio-section[open] summary {{ margin-bottom: 0.5rem; }}
  .alerta-badge {{
    display: inline-block; background: rgba(248,113,113,0.2);
    color: #f87171; border-radius: 999px; font-size: 0.7rem;
    font-family: 'DM Sans', sans-serif; font-weight: 500;
    padding: 0.1rem 0.55rem; margin-left: 0.5rem; vertical-align: middle;
  }}
  .alerta-desc {{ font-size: 0.82rem; color: var(--muted); margin-bottom: 1rem; }}
  .alerta-pct {{ color: #f87171; font-weight: 600; }}
  .alerta-fam {{ font-size: 0.8rem; color: var(--muted); }}
  .alerta-nota {{ font-size: 0.7rem; color: #facc15; font-style: italic; }}
  .alerta-media {{ color: var(--muted); }}
  .alerta-n {{ color: var(--muted); font-size: 0.82rem; }}
  @media (max-width: 640px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}

  /* Buscador de evolución de precio */
  .precio-buscador {{ position: relative; margin-bottom: 0.5rem; }}
  .precio-buscador input {{
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    color: var(--text); border-radius: 8px; padding: 0.6rem 1rem;
    font-family: inherit; font-size: 0.95rem;
  }}
  .precio-buscador input:focus {{ outline: none; border-color: var(--accent); }}
  .sugerencias {{
    position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; margin-top: 4px;
    max-height: 220px; overflow-y: auto; display: none;
  }}
  .sugerencias.visible {{ display: block; }}
  .sug-item {{
    padding: 0.5rem 1rem; cursor: pointer; font-size: 0.875rem;
    border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }}
  .sug-item:last-child {{ border-bottom: none; }}
  .sug-item:hover {{ background: rgba(255,255,255,0.04); }}
  .sug-item .sug-fam {{ font-size: 0.75rem; color: var(--muted); }}
  .precio-stats {{
    display: flex; gap: 1.5rem; flex-wrap: wrap;
    padding: 0.75rem 0; border-bottom: 1px solid var(--border); margin-bottom: 0.5rem;
  }}
  .precio-stat {{ display: flex; flex-direction: column; gap: 0.2rem; }}
  .precio-stat .ps-label {{ font-size: 0.7rem; text-transform: uppercase;
                             letter-spacing: 0.08em; color: var(--muted); }}
  .precio-stat .ps-value {{ font-size: 1.2rem; font-weight: 600; }}
  .precio-stat .ps-sub {{ font-size: 0.68rem; color: var(--muted); margin-top: 0.15rem; }}
  .precio-vacio {{ color: var(--muted); font-size: 0.9rem; padding: 1rem 0; text-align: center; }}
  .precio-aviso-peso {{
    background: rgba(250,204,21,0.08); border: 1px solid rgba(250,204,21,0.3);
    border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 0.75rem;
    font-size: 0.82rem; color: #facc15;
  }}
  /* Paginación */
  .paginacion {{
    display: flex; align-items: center; gap: 0.5rem;
    margin-top: 1rem; padding-top: 1rem;
    border-top: 1px solid var(--border); flex-wrap: wrap;
  }}
  .btn-pag {{
    background: transparent; border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; width: 2rem; height: 2rem; font-size: 1rem;
    cursor: pointer; transition: all 0.15s; display: flex; align-items: center; justify-content: center;
  }}
  .btn-pag:hover:not(:disabled) {{ border-color: var(--accent); color: var(--accent); }}
  .btn-pag:disabled {{ opacity: 0.25; cursor: default; }}
  .pag-info {{ font-size: 0.82rem; color: var(--muted); min-width: 8rem; text-align: center; }}
  .pag-select {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.25rem 0.5rem; font-family: inherit;
    font-size: 0.82rem; cursor: pointer; margin-left: 0.5rem;
  }}
  .pag-label {{ font-size: 0.78rem; color: var(--muted); }}
</style>
</head>
<body>
<div class="container">

  <header>
    <div>
      <h1>🛒 Mercadona <span>·</span> Informe de gasto</h1>
      <span class="sub" id="header-rango">{r['primera_compra']} → {r['ultima_compra']}</span>
    </div>
  </header>

  {alertas_html}
  {sin_fam_html}

  <!-- Filtros -->
  <div class="filtros">
    <div class="tarjetas-row" id="tarjetas-row"><span id="filtro-tarjeta-activa"></span></div>
    <div class="años-row" id="años-row"></div>
    <div class="meses-row" id="meses-row"></div>
    <div class="filtros-row">
      <div class="filtro-grupo">
        <label>Desde</label>
        <input type="date" id="fecha-desde">
      </div>
      <div class="filtro-grupo">
        <label>Hasta</label>
        <input type="date" id="fecha-hasta">
      </div>
      <button class="btn-reset" id="btn-reset" onclick="resetFiltros()">✕ Quitar filtros</button>
      <span id="filtro-activo"></span>
    </div>
  </div>

  <!-- KPIs dinámicos -->
  <div class="kpis">
    <div class="kpi">
      <div class="label">Gasto total</div>
      <div class="value" style="color:var(--accent)" id="kpi-total">—</div>
    </div>
    <div class="kpi">
      <div class="label">Gasto medio mensual</div>
      <div class="value" style="color:var(--accent2)" id="kpi-mensual">—</div>
    </div>
    <div class="kpi">
      <div class="label">Ticket medio</div>
      <div class="value" style="color:var(--info)" id="kpi-ticket-medio">—</div>
    </div>
    <div class="kpi">
      <div class="label">Compras</div>
      <div class="value" style="color:#a78bfa" id="kpi-compras">—</div>
    </div>
    <div class="kpi">
      <div class="label">Productos distintos</div>
      <div class="value" style="color:#f97316" id="kpi-productos">—</div>
    </div>
    <div class="kpi">
      <div class="label">Última compra</div>
      <div class="value" style="color:var(--info)" id="kpi-ultima-total">—</div>
      <div class="sub" id="kpi-ultima-fecha">—</div>
    </div>
  </div>

  <!-- Gráficos -->
  <div class="grid2">
    <div class="section">
      <h2>📅 Gasto por mes</h2>
      <div class="chart-wrap"><canvas id="chartMes"></canvas></div>
    </div>
    <div class="section">
      <h2>🥧 Gasto por familia</h2>
      <div class="chart-wrap"><canvas id="chartFamilia"></canvas></div>
    </div>
  </div>

  <!-- Desglose familias -->
  <div class="section">
    <h2>📊 Desglose por familia</h2>
    <table>
      <thead><tr>
        <th>Familia</th>
        <th style="text-align:right">Gasto</th>
        <th style="text-align:right">%</th>
        <th style="min-width:120px"></th>
      </tr></thead>
      <tbody id="tabla-familias"></tbody>
    </table>
  </div>

  <!-- Tiendas -->
  <div class="section">
    <h2>📍 Por tienda</h2>
    <table>
      <thead><tr>
        <th>Dirección</th>
        <th style="text-align:right">C.P.</th>
        <th style="text-align:right">Visitas</th>
        <th style="text-align:right">Gasto total</th>
      </tr></thead>
      <tbody id="tabla-tiendas"></tbody>
    </table>
  </div>

  <!-- Top productos -->
  <div class="section">
    <h2>🏆 Productos más comprados</h2>
    <table>
      <thead><tr>
        <th>Producto</th>
        <th>Familia</th>
        <th style="text-align:right">Veces</th>
        <th style="text-align:right">Precio medio</th>
        <th style="text-align:right">Gasto total</th>
      </tr></thead>
      <tbody id="tabla-productos"></tbody>
    </table>
  </div>

  <!-- Tabla de tickets -->
  <div class="section">
    <h2>🧾 Tickets</h2>
    <table>
      <thead><tr>
        <th>Fecha</th>
        <th>Tienda</th>
        <th style="text-align:right">Importe</th>
        <th style="width:1rem"></th>
      </tr></thead>
      <tbody id="tabla-tickets"></tbody>
    </table>
    <div class="paginacion" id="paginacion">
      <button class="btn-pag" id="pag-first" onclick="irPagina('first')" title="Primeros">⟪</button>
      <button class="btn-pag" id="pag-prev"  onclick="irPagina('prev')"  title="Anteriores">‹</button>
      <span id="pag-info" class="pag-info"></span>
      <button class="btn-pag" id="pag-next"  onclick="irPagina('next')"  title="Siguientes">›</button>
      <button class="btn-pag" id="pag-last"  onclick="irPagina('last')"  title="Últimos">⟫</button>
      <select id="pag-tam" onchange="cambiarTamPagina()" class="pag-select">
        <option value="5" selected>5</option>
        <option value="20">20</option>
        <option value="50">50</option>
        <option value="100">100</option>
        <option value="250">250</option>
      </select>
      <span class="pag-label">por página</span>
    </div>
  </div>


  <!-- Evolución de precio -->
  <div class="section">
    <h2>📈 Evolución de precio</h2>
    <div class="precio-buscador">
      <input type="text" id="precio-input" placeholder="Escribe un producto…" autocomplete="off">
      <div id="precio-sugerencias" class="sugerencias"></div>
    </div>
    <div id="precio-resultado" style="display:none">
      <div id="precio-aviso-peso" class="precio-aviso-peso" style="display:none">
        ⚠️ Este producto se vende por envase — el peso podría variar entre compras, por lo que las comparaciones de precio son orientativas.
      </div>
      <div class="precio-stats" id="precio-stats"></div>
      <div class="chart-wrap" style="margin-top:1rem"><canvas id="chartPrecio"></canvas></div>
    </div>
    <div id="precio-vacio" class="precio-vacio">Busca un producto para ver su evolución de precio</div>
  </div>

  {records_section_html}

  {alertas_precio_html}

  <footer>Generado por <a href="https://github.com/pezbailarin/mercadona-ticket-analyzer" target="_blank"><strong>Mercadona Ticket Analyzer</strong></a> · {fecha_generacion} · base de datos: <code>{DB_NAME}</code></footer>
</div>

<script>
// ── Datos embebidos ──────────────────────────────────────────────
const DATOS = {datos_json};
const FAM_COLORES = {fam_colores_js};

// ── Estado del filtro ────────────────────────────────────────────
let filtroAño     = "";
let filtroMes     = "";
let filtroDesde   = "";
let filtroHasta   = "";
let filtroTarjeta = "";

// ── Inicialización ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function init() {{

  // Botones de tarjeta (solo si hay más de una)
  if (DATOS.tarjetas && DATOS.tarjetas.length > 1) {{
    const tarjetasRow = document.getElementById('tarjetas-row');
    DATOS.tarjetas.forEach(tar => {{
      const btn = document.createElement('button');
      btn.className = 'btn-tarjeta';
      btn.textContent = '💳 ' + tar.label;
      btn.dataset.tarjetaId = tar.id;
      btn.addEventListener('click', () => {{
        filtroTarjeta = (filtroTarjeta === tar.id) ? "" : tar.id;
        tarjetasRow.querySelectorAll('.btn-tarjeta').forEach(b => b.classList.remove('activo'));
        if (filtroTarjeta) btn.classList.add('activo');
        actualizar();
      }});
      tarjetasRow.appendChild(btn);
    }});
  }}

  // Construir mapa año → set de meses con datos
  const mesesConDatos = new Set(DATOS.tickets.map(t => t.mes));
  const años = [...new Set(DATOS.tickets.map(t => t.mes.slice(0,4)))].sort();

  // Botones de año
  const añosRow = document.getElementById('años-row');
  años.forEach(a => {{
    const btn = document.createElement('button');
    btn.className = 'btn-año';
    btn.textContent = a;
    btn.dataset.año = a;
    btn.addEventListener('click', () => seleccionarAño(a));
    añosRow.appendChild(btn);
  }});

  // Render meses (vacío hasta que se seleccione año)
  renderMeses();

  // Límites de fechas
  const fechas = DATOS.tickets.map(t => t.datetime.slice(0,10)).sort();
  document.getElementById('fecha-desde').min = fechas[0];
  document.getElementById('fecha-desde').max = fechas[fechas.length-1];
  document.getElementById('fecha-hasta').min = fechas[0];
  document.getElementById('fecha-hasta').max = fechas[fechas.length-1];

  document.getElementById('fecha-desde').addEventListener('change', e => {{
    filtroDesde = e.target.value;
    if (filtroDesde || filtroHasta) {{
      filtroAño = filtroMes = "";
      renderMeses();
      document.querySelectorAll('.btn-año').forEach(b => b.classList.remove('activo'));
    }}
    actualizar();
  }});

  document.getElementById('fecha-hasta').addEventListener('change', e => {{
    filtroHasta = e.target.value;
    if (filtroDesde || filtroHasta) {{
      filtroAño = filtroMes = "";
      renderMeses();
      document.querySelectorAll('.btn-año').forEach(b => b.classList.remove('activo'));
    }}
    actualizar();
  }});

  actualizar();
}});

function seleccionarAño(a) {{
  if (filtroAño === a) {{
    // Segundo clic en el mismo año → deseleccionar
    filtroAño = filtroMes = "";
  }} else {{
    filtroAño = a;
    filtroMes = "";
  }}
  filtroDesde = filtroHasta = "";
  document.getElementById('fecha-desde').value = "";
  document.getElementById('fecha-hasta').value = "";
  document.querySelectorAll('.btn-año').forEach(b =>
    b.classList.toggle('activo', b.dataset.año === filtroAño));
  renderMeses();
  actualizar();
}}

function renderMeses() {{
  const mesesConDatos = new Set(DATOS.tickets.map(t => t.mes));
  const row = document.getElementById('meses-row');
  row.innerHTML = '';
  if (!filtroAño) return;
  const MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  MESES.forEach((nombre, i) => {{
    const mesKey = filtroAño + '-' + String(i+1).padStart(2,'0');
    const btn = document.createElement('button');
    btn.className = 'btn-mes' + (mesesConDatos.has(mesKey) ? '' : ' vacio');
    btn.textContent = nombre;
    btn.dataset.mes = mesKey;
    if (filtroMes === mesKey) btn.classList.add('activo');
    btn.addEventListener('click', () => {{
      if (btn.classList.contains('vacio')) return;
      filtroMes = (filtroMes === mesKey) ? "" : mesKey;
      row.querySelectorAll('.btn-mes').forEach(b => b.classList.remove('activo'));
      if (filtroMes) btn.classList.add('activo');
      actualizar();
    }});
    row.appendChild(btn);
  }});
}}

function hayFiltroActivo() {{
  return filtroAño || filtroMes || filtroDesde || filtroHasta || filtroTarjeta;
}}

function actualizarBtnReset() {{
  const btn = document.getElementById('btn-reset');
  if (btn) btn.style.display = hayFiltroActivo() ? 'inline-block' : 'none';
}}

function resetFiltros() {{
  filtroAño = filtroMes = filtroDesde = filtroHasta = filtroTarjeta = "";
  document.getElementById('fecha-desde').value = "";
  document.getElementById('fecha-hasta').value = "";
  document.querySelectorAll('.btn-año, .btn-mes, .btn-tarjeta').forEach(b => b.classList.remove('activo'));
  document.getElementById('meses-row').innerHTML = '';
  actualizar();
  actualizarBtnReset();
}}

// ── Filtrado ─────────────────────────────────────────────────────
function ticketsFiltrados() {{
  return DATOS.tickets.filter(t => {{
    const fecha = t.datetime.slice(0,10);
    if (filtroAño     && t.mes.slice(0,4) !== filtroAño)      return false;
    if (filtroMes     && t.mes !== filtroMes)                  return false;
    if (filtroDesde   && fecha < filtroDesde)                  return false;
    if (filtroHasta   && fecha > filtroHasta)                  return false;
    if (filtroTarjeta && t.tarjeta_id !== filtroTarjeta)       return false;
    return true;
  }});
}}

// ── Actualización completa ───────────────────────────────────────
let chartMes      = null;
let chartFamilia  = null;

function actualizar() {{
  const tickets = ticketsFiltrados();
  const tids    = new Set(tickets.map(t => t.id));
  const lineas  = DATOS.lineas.filter(l => tids.has(l.tid));

  actualizarFiltroActivo(tickets);
  actualizarBtnReset();
  actualizarKPIs(tickets, lineas);
  actualizarGraficoMes(tickets);
  actualizarGraficoFamilia(lineas);
  actualizarTablaFamilias(lineas);
  actualizarTablaTiendas(tickets);
  actualizarTablaProductos(lineas);
  actualizarTablaTickets(tickets);
}}

function actualizarFiltroActivo(tickets) {{
  const el = document.getElementById('filtro-activo');
  const elTar = document.getElementById('filtro-tarjeta-activa');
  // Texto de tarjeta
  if (filtroTarjeta) {{
    const tar = DATOS.tarjetas.find(t => t.id === filtroTarjeta);
    const tarLabel = tar ? (tar.label !== '····' + tar.ultimos4 ? '"' + tar.label + '"' : tar.ultimos4) : filtroTarjeta;
    elTar.style.display = 'block';
    elTar.textContent = '💳 compras realizadas con ' + (tar && tar.label !== '····' + tar.ultimos4 ? tarLabel : 'la tarjeta terminada en ' + tarLabel);
  }} else {{
    elTar.style.display = 'none';
    elTar.textContent = '';
  }}
  // Texto de fecha/año/mes
  const hayFecha = filtroMes || filtroAño || filtroDesde || filtroHasta;
  if (!hayFecha) {{ el.style.display = 'none'; el.textContent = ''; return; }}
  el.style.display = 'inline';
  if (filtroMes) {{
    const [y, m] = filtroMes.split('-');
    el.textContent = '📅 ' + new Date(y, m-1).toLocaleDateString('es-ES', {{month:'long', year:'numeric'}});
  }} else if (filtroAño) {{
    el.textContent = '📅 año ' + filtroAño;
  }} else {{
    el.textContent = '📅 ' + (filtroDesde || '…') + ' → ' + (filtroHasta || '…');
  }}
}}

function fmt(n) {{ return n.toFixed(2) + ' €'; }}

function actualizarKPIs(tickets, lineas) {{
  const total    = tickets.reduce((s,t) => s+t.total, 0);
  const meses    = new Set(tickets.map(t => t.mes)).size || 1;
  const productos = new Set(lineas.map(l => l.descripcion)).size;
  const ultimo   = tickets.length ? tickets[tickets.length-1] : null;

  document.getElementById('kpi-total').textContent        = fmt(total);
  document.getElementById('kpi-mensual').textContent      = fmt(total / meses);
  document.getElementById('kpi-ticket-medio').textContent = tickets.length ? fmt(total / tickets.length) : '—';
  document.getElementById('kpi-compras').textContent      = tickets.length;
  document.getElementById('kpi-productos').textContent    = productos;
  document.getElementById('kpi-ultima-total').textContent = ultimo ? fmt(ultimo.total) : '—';
  document.getElementById('kpi-ultima-fecha').textContent = ultimo ? ultimo.datetime : '—';
}}

function actualizarGraficoMes(tickets) {{
  // Agrupar por mes
  const porMes = {{}};
  tickets.forEach(t => {{ porMes[t.mes] = (porMes[t.mes] || 0) + t.total; }});
  const labels = Object.keys(porMes).sort();
  const data   = labels.map(m => +porMes[m].toFixed(2));

  if (chartMes) chartMes.destroy();
  chartMes = new Chart(document.getElementById('chartMes'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [{{ label: 'Gasto (€)', data,
        backgroundColor: '#4ade8099', borderColor: '#4ade80',
        borderWidth: 1, borderRadius: 6 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ labels: {{ color:'#94a3b8', font:{{family:'DM Sans'}} }} }} }},
      scales: {{
        x: {{ ticks: {{ color:'#64748b' }}, grid: {{ color:'#2a2d3a' }} }},
        y: {{ ticks: {{ color:'#64748b', callback: v => v+'€' }}, grid: {{ color:'#2a2d3a' }} }}
      }}
    }}
  }});
}}

function actualizarGraficoFamilia(lineas) {{
  // Agrupar por familia
  const porFam = {{}};
  lineas.forEach(l => {{
    const k = l.emoji + ' ' + l.familia;
    porFam[k] = (porFam[k] || 0) + l.importe;
  }});
  // Ordenar por gasto desc
  const entries = Object.entries(porFam).sort((a,b) => b[1]-a[1]);
  const labels  = entries.map(e => e[0]);
  const data    = entries.map(e => +e[1].toFixed(2));

  if (chartFamilia) chartFamilia.destroy();
  chartFamilia = new Chart(document.getElementById('chartFamilia'), {{
    type: 'doughnut',
    data: {{
      labels,
      datasets: [{{ data, backgroundColor: FAM_COLORES, borderWidth: 0, hoverOffset: 8 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position:'right',
        labels: {{ color:'#94a3b8', font:{{family:'DM Sans', size:11}}, boxWidth:12, padding:8 }} }} }}
    }}
  }});
}}

function actualizarTablaFamilias(lineas) {{
  const porFam = {{}};
  lineas.forEach(l => {{
    if (!porFam[l.familia]) porFam[l.familia] = {{ emoji: l.emoji, gasto: 0, items: {{}} }};
    porFam[l.familia].gasto += l.importe;
    // Agrupar items por descripción dentro de la familia
    const k = l.descripcion;
    if (!porFam[l.familia].items[k]) porFam[l.familia].items[k] = {{ gasto: 0, n: 0 }};
    porFam[l.familia].items[k].gasto += l.importe;
    porFam[l.familia].items[k].n++;
  }});
  const total = Object.values(porFam).reduce((s,f) => s+f.gasto, 0);
  const famId = nom => 'fam-det-' + nom.replace(/[^a-zA-Z0-9]/g,'_');
  const filas = Object.entries(porFam)
    .sort((a,b) => b[1].gasto - a[1].gasto)
    .map(([nom, f]) => {{
      const pct = total ? (f.gasto/total*100).toFixed(1) : 0;
      const detId = famId(nom);
      const itemsHTML = Object.entries(f.items)
        .sort((a,b) => b[1].gasto - a[1].gasto)
        .map(([desc, d]) => `
          <tr>
            <td style="padding-left:2.5rem;font-size:0.82rem">${{desc}}</td>
            <td class="num" style="font-size:0.82rem;color:var(--muted)">${{d.n}}x</td>
            <td class="num" style="font-size:0.82rem">${{fmt(d.gasto)}}</td>
            <td></td>
          </tr>`).join('');
      return `
        <tr class="fam-row" onclick="toggleFamilia('${{detId}}')" style="cursor:pointer">
          <td><span class="emoji">${{f.emoji}}</span>${{nom}} <span id="arr-${{detId}}" style="font-size:0.7rem;color:var(--muted);margin-left:0.3rem">▶</span></td>
          <td class="num">${{fmt(f.gasto)}}</td>
          <td class="num">${{pct}}%</td>
          <td><div class="bar-wrap"><div class="bar" style="width:${{pct}}%"></div></div></td>
        </tr>
        <tr id="${{detId}}" style="display:none">
          <td colspan="4" style="padding:0">
            <table style="width:100%">${{itemsHTML}}</table>
          </td>
        </tr>`;
    }});
  document.getElementById('tabla-familias').innerHTML =
    filas.length ? filas.join('') : '<tr class="empty-row"><td colspan="4">Sin datos</td></tr>';
}}

function toggleFamilia(id) {{
  const row = document.getElementById(id);
  const arr = document.getElementById('arr-' + id);
  const open = row.style.display === 'none';
  row.style.display = open ? 'table-row' : 'none';
  if (arr) arr.textContent = open ? '▼' : '▶';
}}

function actualizarTablaTiendas(tickets) {{
  const porTienda = {{}};
  tickets.forEach(t => {{
    const k = t.tienda;
    if (!porTienda[k]) porTienda[k] = {{ cp: t.cp, gasto: 0, n: 0 }};
    porTienda[k].gasto += t.total;
    porTienda[k].n++;
  }});
  const filas = Object.entries(porTienda)
    .sort((a,b) => b[1].gasto - a[1].gasto)
    .map(([tienda, d]) => `<tr>
      <td>${{tienda}}</td>
      <td class="num">${{d.cp || '—'}}</td>
      <td class="num">${{d.n}}</td>
      <td class="num bold">${{fmt(d.gasto)}}</td>
    </tr>`);
  document.getElementById('tabla-tiendas').innerHTML =
    filas.length ? filas.join('') : '<tr class="empty-row"><td colspan="4">Sin datos</td></tr>';
}}

function actualizarTablaProductos(lineas) {{
  const porProd = {{}};
  lineas.forEach(l => {{
    if (!porProd[l.descripcion]) porProd[l.descripcion] = {{ emoji:l.emoji, familia:l.familia, gasto:0, n:0, precios:[] }};
    porProd[l.descripcion].gasto += l.importe;
    porProd[l.descripcion].n++;
    porProd[l.descripcion].precios.push(l.precio_unitario);
  }});
  const filas = Object.entries(porProd)
    .sort((a,b) => b[1].gasto - a[1].gasto)
    .slice(0, 15)
    .map(([desc, p]) => {{
      const precioMedio = p.precios.reduce((s,v)=>s+v,0) / p.precios.length;
      return `<tr>
        <td><span class="emoji">${{p.emoji}}</span>${{desc}}</td>
        <td class="fam-tag">${{p.familia}}</td>
        <td class="num">${{p.n}}x</td>
        <td class="num">${{precioMedio.toFixed(2)}} €</td>
        <td class="num bold">${{fmt(p.gasto)}}</td>
      </tr>`;
    }});
  document.getElementById('tabla-productos').innerHTML =
    filas.length ? filas.join('') : '<tr class="empty-row"><td colspan="5">Sin datos</td></tr>';
}}

// ── Tabla de tickets con detalle desplegable ──────────────────────
// Estado de paginación de tickets
let _ticketsPag   = [];
let _pagActual    = 0;
let _pagTam       = 5;

function actualizarTablaTickets(tickets) {{
  _ticketsPag = [...tickets].sort((a,b) => b.datetime.localeCompare(a.datetime));
  _pagActual  = 0;
  renderPagina();
}}

function renderPagina() {{
  const lineasPorTicket = {{}};
  DATOS.lineas.forEach(l => {{
    if (!lineasPorTicket[l.tid]) lineasPorTicket[l.tid] = [];
    lineasPorTicket[l.tid].push(l);
  }});

  const total   = _ticketsPag.length;
  const inicio  = _pagActual * _pagTam;
  const fin     = Math.min(inicio + _pagTam, total);
  const pagina  = _ticketsPag.slice(inicio, fin);
  const totPags = Math.ceil(total / _pagTam) || 1;

  const filas = pagina.map(t => {{
    const lineas = lineasPorTicket[t.id] || [];
    const lineasHTML = lineas.map(l => `
      <tr>
        <td>${{l.emoji}} ${{l.descripcion}}</td>
        <td class="num" style="color:var(--muted)">${{l.cantidad % 1 === 0 ? l.cantidad : l.cantidad.toFixed(3)}}${{l.es_peso ? ' kg' : 'x'}}</td>
        <td class="num">${{l.precio_unitario.toFixed(2)}} €</td>
        <td class="num bold">${{l.importe.toFixed(2)}} €</td>
      </tr>`).join('');
    return `
      <tr class="ticket-row" onclick="toggleTicket(${{t.id}})">
        <td>${{t.datetime}}</td>
        <td style="color:var(--muted);font-size:0.85rem">${{t.tienda}}</td>
        <td class="num bold">${{t.total.toFixed(2)}} €</td>
        <td style="color:var(--muted);font-size:0.8rem" id="arrow-${{t.id}}">▶</td>
      </tr>
      <tr class="ticket-detalle" id="det-${{t.id}}">
        <td colspan="4">
          <div class="ticket-detalle-inner">
            <table>
              <thead><tr>
                <th>Producto</th><th style="text-align:right">Cant.</th>
                <th style="text-align:right">Precio</th><th style="text-align:right">Total</th>
              </tr></thead>
              <tbody>${{lineasHTML}}</tbody>
            </table>
          </div>
        </td>
      </tr>`;
  }}).join('');

  document.getElementById('tabla-tickets').innerHTML =
    filas || '<tr class="empty-row"><td colspan="4">Sin datos</td></tr>';

  // Info y estado de botones
  document.getElementById('pag-info').textContent =
    total ? `${{inicio+1}}–${{fin}} de ${{total}}` : '0 tickets';
  document.getElementById('pag-first').disabled = _pagActual === 0;
  document.getElementById('pag-prev').disabled  = _pagActual === 0;
  document.getElementById('pag-next').disabled  = _pagActual >= totPags - 1;
  document.getElementById('pag-last').disabled  = _pagActual >= totPags - 1;
}}

function irPagina(dir) {{
  const totPags = Math.ceil(_ticketsPag.length / _pagTam) || 1;
  if      (dir === 'first') _pagActual = 0;
  else if (dir === 'prev')  _pagActual = Math.max(0, _pagActual - 1);
  else if (dir === 'next')  _pagActual = Math.min(totPags - 1, _pagActual + 1);
  else if (dir === 'last')  _pagActual = totPags - 1;
  renderPagina();
}}

function cambiarTamPagina() {{
  _pagTam    = parseInt(document.getElementById('pag-tam').value);
  _pagActual = 0;
  renderPagina();
}}

function toggleTicket(id) {{
  const det   = document.getElementById('det-'   + id);
  const arrow = document.getElementById('arrow-' + id);
  const open  = det.classList.toggle('open');
  arrow.textContent = open ? '▼' : '▶';
}}

// ── Evolución de precio ──────────────────────────────────────────
let chartPrecio = null;
let productoActual = null;

(function initPrecioBuscador() {{
  const input  = document.getElementById('precio-input');
  const lista  = document.getElementById('precio-sugerencias');
  const todos  = Object.keys(DATOS.precios).sort();

  function mostrarSugerencias(q) {{
    const q2 = q.trim().toUpperCase();
    if (!q2) {{ lista.classList.remove('visible'); return; }}
    const matches = todos.filter(d => d.includes(q2)).slice(0, 12);
    if (!matches.length) {{ lista.classList.remove('visible'); return; }}
    lista.innerHTML = matches.map(d => {{
      const prod = DATOS.precios[d];
      return `<div class="sug-item" data-desc="${{d}}">
        <span>${{prod.emoji}} ${{d}}</span>
        <span class="sug-fam">${{prod.familia}}</span>
      </div>`;
    }}).join('');
    lista.classList.add('visible');
  }}

  input.addEventListener('input', e => mostrarSugerencias(e.target.value));
  input.addEventListener('focus', e => mostrarSugerencias(e.target.value));

  lista.addEventListener('click', e => {{
    const item = e.target.closest('.sug-item');
    if (!item) return;
    const desc = item.dataset.desc;
    input.value = desc;
    lista.classList.remove('visible');
    mostrarEvolucionPrecio(desc);
  }});

  document.addEventListener('click', e => {{
    if (!e.target.closest('.precio-buscador')) lista.classList.remove('visible');
  }});

  input.addEventListener('keydown', e => {{
    if (e.key === 'Escape') lista.classList.remove('visible');
  }});
}})();

function mostrarEvolucionPrecio(desc) {{
  const prod = DATOS.precios[desc];
  if (!prod) return;
  productoActual = desc;

  const puntos = prod.puntos;  // {{d, p}}
  // Deduplicar por fecha (misma fecha → precio de esa compra, promedio si varias)
  const porFecha = {{}};
  puntos.forEach(pt => {{
    if (!porFecha[pt.d]) porFecha[pt.d] = [];
    porFecha[pt.d].push(pt.p);
  }});
  const fechas  = Object.keys(porFecha).sort();
  const precios = fechas.map(f => +(porFecha[f].reduce((a,b)=>a+b,0)/porFecha[f].length).toFixed(3));

  const unidad  = !!prod.es_peso ? '€/kg' : '€/ud';
  // Aviso para familias con precio por envase y peso variable
  const FAM_PESO_VARIABLE_IDS = [2]; // Carne
  const esPesoVariable = FAM_PESO_VARIABLE_IDS.includes(prod.familia_id || -1);
  const pmin    = Math.min(...precios);
  const pmax    = Math.max(...precios);
  const pmedia  = +(precios.reduce((a,b)=>a+b,0)/precios.length).toFixed(3);
  const pactual = precios[precios.length-1];
  const fechaInicio = new Date(fechas[0]);
  const fechaFin    = new Date(fechas[fechas.length-1]);
  const diasTotal   = Math.round((fechaFin - fechaInicio) / (1000*60*60*24));
  const mesesTotal  = Math.round(diasTotal / 30.44);

  // Variación total con duración
  const subida = precios.length > 1
    ? (((pactual - precios[0]) / precios[0]) * 100).toFixed(1)
    : 0;
  const duracionStr = diasTotal < 30
    ? `${{diasTotal}} día${{diasTotal !== 1 ? 's' : ''}}`
    : mesesTotal < 24
      ? `${{mesesTotal}} mes${{mesesTotal !== 1 ? 'es' : ''}}`
      : `${{(mesesTotal/12).toFixed(1)}} años`;
  const colorSubida = subida > 0 ? '#f87171' : subida < 0 ? '#4ade80' : '#94a3b8';

  // Variación último año: buscar compra más cercana a hace 12 meses (±90 días)
  let htmlUltimoAño = '';
  if (fechas.length >= 2) {{
    const hoy       = new Date(fechas[fechas.length-1]); // última compra como referencia
    const objetivo  = new Date(hoy); objetivo.setFullYear(objetivo.getFullYear() - 1);
    const margen    = 90 * 24*60*60*1000; // ±90 días en ms
    let mejorIdx = -1;
    let mejorDist = Infinity;
    fechas.forEach((f, idx) => {{
      if (idx === fechas.length - 1) return; // excluir la compra actual
      const dist = Math.abs(new Date(f) - objetivo);
      if (dist <= margen && dist < mejorDist) {{
        mejorDist = dist;
        mejorIdx  = idx;
      }}
    }});
    if (mejorIdx >= 0) {{
      const pRef     = precios[mejorIdx];
      const varAño   = (((pactual - pRef) / pRef) * 100).toFixed(1);
      const colorAño = varAño > 0 ? '#f87171' : varAño < 0 ? '#4ade80' : '#94a3b8';
      const fechaRef = fechas[mejorIdx];
      htmlUltimoAño = `
        <div class="precio-stat">
          <span class="ps-label">Último año</span>
          <span class="ps-value" style="color:${{colorAño}}">${{varAño > 0 ? '+' : ''}}${{varAño}}%</span>
          <span class="ps-sub">vs ${{fechaRef}}</span>
        </div>`;
    }}
  }}

  // Stats
  document.getElementById('precio-stats').innerHTML = `
    <div class="precio-stat">
      <span class="ps-label">Actual</span>
      <span class="ps-value" style="color:var(--accent)">${{pactual.toFixed(2)}} ${{unidad}}</span>
    </div>
    <div class="precio-stat">
      <span class="ps-label">Mínimo</span>
      <span class="ps-value" style="color:#4ade80">${{pmin.toFixed(2)}} ${{unidad}}</span>
    </div>
    <div class="precio-stat">
      <span class="ps-label">Máximo</span>
      <span class="ps-value" style="color:#f87171">${{pmax.toFixed(2)}} ${{unidad}}</span>
    </div>
    <div class="precio-stat">
      <span class="ps-label">Media</span>
      <span class="ps-value" style="color:var(--accent2)">${{pmedia.toFixed(2)}} ${{unidad}}</span>
    </div>
    <div class="precio-stat">
      <span class="ps-label">Variación total (${{duracionStr}})</span>
      <span class="ps-value" style="color:${{colorSubida}}">${{subida > 0 ? '+' : ''}}${{subida}}%</span>
    </div>
    ${{htmlUltimoAño}}
    <div class="precio-stat">
      <span class="ps-label">Compras</span>
      <span class="ps-value" style="color:var(--info)">${{puntos.length}}x</span>
    </div>`;

  // Mostrar sección, ocultar placeholder
  // Aviso peso variable (carnes)
  const avisoEl = document.getElementById('precio-aviso-peso');
  if (avisoEl) avisoEl.style.display = esPesoVariable ? 'block' : 'none';

  document.getElementById('precio-resultado').style.display = 'block';
  document.getElementById('precio-vacio').style.display = 'none';

  // Gráfico
  if (chartPrecio) chartPrecio.destroy();
  chartPrecio = new Chart(document.getElementById('chartPrecio'), {{
    type: 'line',
    data: {{
      labels: fechas,
      datasets: [{{
        label: `${{desc}} (${{unidad}})`,
        data: precios,
        borderColor: '#4ade80',
        backgroundColor: 'rgba(74,222,128,0.08)',
        borderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
        pointBackgroundColor: precios.map(p =>
          p === pmin ? '#4ade80' : p === pmax ? '#f87171' : '#facc15'
        ),
        pointBorderColor: 'transparent',
        tension: 0.3,
        fill: true,
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ labels: {{ color: '#94a3b8', font: {{ family: 'DM Sans' }} }} }},
        tooltip: {{
          callbacks: {{
            label: ctx => ` ${{ctx.parsed.y.toFixed(3)}} ${{unidad}}`
          }}
        }}
      }},
      scales: {{
        x: {{ ticks: {{ color: '#64748b', maxRotation: 45 }}, grid: {{ color: '#2a2d3a' }} }},
        y: {{
          ticks: {{ color: '#64748b', callback: v => v.toFixed(2) + ' €' }},
          grid: {{ color: '#2a2d3a' }},
          suggestedMin: pmin * 0.95,
          suggestedMax: pmax * 1.05,
        }}
      }}
    }}
  }});
}}

</script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(
        description="Genera el informe HTML interactivo de tickets Mercadona.",
        epilog="""
Ejemplos:
  python3 stats.py                        Genera informe.html
  python3 stats.py --output enero.html    Nombre de salida personalizado
  python3 stats.py --sin-familia          Lista productos sin categoría y sale
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sin-familia", action="store_true",
                        help="Lista productos sin familia asignada y sale")
    parser.add_argument("--csv", metavar="CARPETA",
                        help="Exporta los datos a CSVs en la carpeta indicada y sale")
    parser.add_argument("--output", default=str(_OUTPUT_DIR / "informe.html"),
                        help="Nombre del fichero HTML de salida (default: informe.html)")
    args = parser.parse_args()

    if args.csv:
        exportar_csv(args.csv)
        sys.exit(0)

    if args.sin_familia:
        productos = productos_sin_familia()
        if not productos:
            print("✅ Todos los productos tienen familia asignada.")
        else:
            print(f"⚠️  {len(productos)} productos sin familia:\n")
            for p in productos:
                print(f"  [{p['id']:>4}] {p['descripcion']:<40} {p['gasto_total']:>7.2f} €")
        return

    print("📊 Calculando estadísticas...")
    stats = obtener_estadisticas()

    if stats["tickets_con_diferencias"]:
        print(f"⚠️  {len(stats['tickets_con_diferencias'])} ticket(s) con diferencias en totales.")
    if stats["sin_familia"]:
        print(f"ℹ️  {len(stats['sin_familia'])} producto(s) sin familia asignada.")

    html = generar_html(stats)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Informe generado: {args.output}")


def exportar_csv(ruta_salida):
    """Exporta los datos principales a un fichero CSV con varias hojas (ficheros separados)."""
    import csv
    from pathlib import Path

    base = Path(ruta_salida)
    base.mkdir(parents=True, exist_ok=True)

    conn = obtener_conexion()
    c = conn.cursor()

    # ── tickets.csv ──
    c.execute("""
        SELECT t.numero_ticket, t.datetime, t.tienda, t.codigo_postal,
               t.total, tar.ultimos4
        FROM tickets t
        JOIN tarjetas tar ON t.tarjeta_id = tar.id
        ORDER BY t.datetime
    """)
    with open(base / "tickets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["numero_ticket", "fecha", "tienda", "cp", "total", "tarjeta"])
        w.writerows(c.fetchall())

    # ── lineas.csv ──
    c.execute("""
        SELECT t.numero_ticket, t.datetime, p.descripcion,
               COALESCE(f.Descripcion, 'Sin categoría') as familia,
               l.cantidad, l.precio_unitario, l.importe, l.es_peso
        FROM lineas_ticket l
        JOIN tickets t ON l.ticket_id = t.id
        JOIN productos p ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        ORDER BY t.datetime, l.id
    """)
    with open(base / "lineas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["numero_ticket", "fecha", "producto", "familia",
                    "cantidad", "precio_unitario", "importe", "es_peso"])
        w.writerows(c.fetchall())

    # ── productos.csv ──
    c.execute("""
        SELECT p.descripcion,
               COALESCE(f.Descripcion, 'Sin categoría') as familia,
               COUNT(DISTINCT l.ticket_id) as num_tickets,
               ROUND(SUM(l.importe), 2) as gasto_total,
               MIN(l.precio_unitario) as precio_min,
               MAX(l.precio_unitario) as precio_max,
               ROUND(AVG(l.precio_unitario), 3) as precio_medio
        FROM productos p
        JOIN lineas_ticket l ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        GROUP BY p.id
        ORDER BY gasto_total DESC
    """)
    with open(base / "productos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["producto", "familia", "num_tickets", "gasto_total",
                    "precio_min", "precio_max", "precio_medio"])
        w.writerows(c.fetchall())

    conn.close()

    print(f"✅ CSV exportado en {base}/")
    print(f"   tickets.csv   — un ticket por fila")
    print(f"   lineas.csv    — una línea de ticket por fila")
    print(f"   productos.csv — resumen por producto")


if __name__ == "__main__":
    main()
