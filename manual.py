#!/usr/bin/env python3
"""
manual.py — Introducción y gestión manual de tickets.

Uso:
    python3 manual.py              # introducir un ticket nuevo
    python3 manual.py --borrar     # buscar un ticket por número y borrarlo
"""


import argparse

import sys
import re
from datetime import datetime
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
from db import obtener_conexion
from main import obtener_o_crear_tarjeta, obtener_o_crear_producto


class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    WHITE  = "\033[97m"


def limpiar_pantalla():
    print("\033[2J\033[H", end="")


# ── Normalización de entrada ─────────────────────────────────────

def normalizar_decimal(val):
    """Acepta tanto ',' como '.' como separador decimal."""
    return val.strip().replace(',', '.')


def normalizar_fecha_raw(val):
    """
    Acepta formatos flexibles:
      20/2/26 → 20/02/2026 00:00
      20/2/2026 10:5 → 20/02/2026 10:05
      20/02/2026 → 20/02/2026 00:00
    """
    val = val.strip()
    # Separar fecha y hora si las hay
    partes = val.split()
    fecha_str = partes[0]
    hora_str  = partes[1] if len(partes) > 1 else "0:0"

    # Fecha: d/m/a
    try:
        d, m, a = fecha_str.split('/')
    except ValueError:
        return None
    d = d.zfill(2)
    m = m.zfill(2)
    if len(a) == 2:
        a = "20" + a
    elif len(a) != 4:
        return None

    # Hora: h:m
    try:
        h, mi = hora_str.split(':')
    except ValueError:
        h, mi = "0", "0"
    h  = h.zfill(2)
    mi = mi.zfill(2)

    normalizada = f"{d}/{m}/{a} {h}:{mi}"
    try:
        dt = datetime.strptime(normalizada, "%d/%m/%Y %H:%M")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return None


def validar_fecha(val):
    if normalizar_fecha_raw(val) is None:
        return "Formato incorrecto. Usa DD/MM/YYYY HH:MM (o abreviado: 20/2/26)"
    return None


def validar_numero_ticket(val):
    if not re.match(r'^\d{4}-\d{3}-\d{6}$', val):
        return "Formato incorrecto. Debe ser XXXX-XXX-XXXXXX (ej: 2726-012-813323)"
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("SELECT id FROM tickets WHERE numero_ticket = ?", (val,))
    existe = c.fetchone()
    conn.close()
    if existe:
        return f"El ticket {val} ya existe en la base de datos."
    return None


def validar_ultimos4(val):
    if not re.match(r'^\d{4}$', val):
        return "Deben ser exactamente 4 dígitos."
    return None


def validar_numero(val):
    try:
        float(normalizar_decimal(val))
        return None
    except ValueError:
        return "Introduce un número (ej: 1.45 o 1,45)"


def preguntar(prompt, validar=None, ejemplo=None, opcional=False):
    sugerencia = f" {C.DIM}(ej: {ejemplo}){C.RESET}" if ejemplo else ""
    while True:
        try:
            val = input(f"  {prompt}{sugerencia}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{C.YELLOW}Cancelado.{C.RESET}\n")
            sys.exit(0)
        if not val:
            if opcional:
                return None
            print(f"  {C.RED}Campo obligatorio.{C.RESET}")
            continue
        if validar:
            error = validar(val)
            if error:
                print(f"  {C.RED}{error}{C.RESET}")
                continue
        return val


# ── Sugerencias de producto ──────────────────────────────────────

def buscar_productos_conocidos(query):
    if len(query) < 2:
        return []
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute("""
        SELECT p.descripcion, COALESCE(f.Emoji,'🗂️'), COALESCE(f.Descripcion,'Sin cat.')
        FROM productos p
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        WHERE p.descripcion LIKE ?
        ORDER BY p.descripcion
        LIMIT 8
    """, (f"%{query.upper()}%",))
    rows = c.fetchall()
    conn.close()
    return rows


def pedir_producto():
    """
    Pide el nombre del producto. Si hay coincidencias, las muestra numeradas
    y ofrece seleccionar una o seguir con lo escrito.
    Devuelve (descripcion, es_nuevo) o (None, _) si se deja en blanco.
    """
    try:
        desc_raw = input(f"  Producto (Enter para terminar): ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n{C.YELLOW}Cancelado.{C.RESET}\n")
        sys.exit(0)

    if not desc_raw:
        return None, False

    sugerencias = buscar_productos_conocidos(desc_raw)

    if not sugerencias:
        return desc_raw.upper(), True

    # Mostrar sugerencias numeradas
    print(f"  {C.DIM}Productos conocidos:{C.RESET}")
    for i, (desc, emoji, fam) in enumerate(sugerencias, 1):
        print(f"  {C.CYAN}{i:>2}{C.RESET}  {emoji} {desc}  {C.DIM}({fam}){C.RESET}")

    print(f"  {C.DIM}  0  Usar «{desc_raw.upper()}» tal como está{C.RESET}")
    print(f"  {C.DIM}  Enter  También usa «{desc_raw.upper()}» tal como está{C.RESET}")

    while True:
        try:
            sel = input(f"  Selecciona (0-{len(sugerencias)}): ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{C.YELLOW}Cancelado.{C.RESET}\n")
            sys.exit(0)

        if sel == '' or sel == '0':
            return desc_raw.upper(), True

        try:
            idx = int(sel) - 1
            if 0 <= idx < len(sugerencias):
                return sugerencias[idx][0], False
            print(f"  {C.RED}Número fuera de rango.{C.RESET}")
        except ValueError:
            print(f"  {C.RED}Escribe un número.{C.RESET}")


# ── Categorización de productos nuevos ──────────────────────────

def _categorizar_nuevos(cursor):
    """Si hay productos del ticket sin familia, ofrece categorizarlos al momento."""
    cursor.execute("""
        SELECT p.id, p.descripcion, ROUND(SUM(l.importe), 2)
        FROM productos p
        JOIN lineas_ticket l ON l.producto_id = p.id
        WHERE p.familia_id IS NULL
        GROUP BY p.id
        ORDER BY 3 DESC
    """)
    sin_familia = cursor.fetchall()
    if not sin_familia:
        return

    print(f"  {C.YELLOW}⚠  {len(sin_familia)} producto(s) sin categoría en este ticket:{C.RESET}")
    for _, desc, gasto in sin_familia:
        print(f"     {C.DIM}{desc}  ({gasto:.2f} €){C.RESET}")
    print()

    try:
        resp = input(f"  ¿Categorizar ahora? (s/N): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return
    if resp != 's':
        print(f"  {C.DIM}Puedes hacerlo más tarde con: python3 categorizar.py{C.RESET}\n")
        return

    familias = cargar_familias()
    familias_por_id = {f["id"]: f for f in familias}

    for prod_id, desc, gasto in sin_familia:
        limpiar_pantalla()
        print(f"\n  {C.BOLD}Categorizar producto nuevo{C.RESET}\n")
        print(f"  {C.WHITE}{desc}{C.RESET}  {C.DIM}({gasto:.2f} €){C.RESET}")
        mostrar_menu_familias(familias)
        while True:
            try:
                resp = input("  Familia (número, s=saltar): ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return
            if resp == 's':
                break
            try:
                fam_id = int(resp)
                if fam_id not in familias_por_id:
                    raise ValueError
            except ValueError:
                print(f"  {C.RED}Opción no válida.{C.RESET}")
                continue
            conn2 = obtener_conexion()
            conn2.execute("UPDATE productos SET familia_id = ? WHERE id = ?", (fam_id, prod_id))
            conn2.commit()
            conn2.close()
            fam = familias_por_id[fam_id]
            print(f"  {C.GREEN}✓ {desc} → {fam['emoji']} {fam['nombre']}{C.RESET}\n")
            break


# ── Modo: introducir ticket ──────────────────────────────────────

def run_introducir():
    limpiar_pantalla()
    print(f"\n  {C.BOLD}Mercadona · Introducción manual de ticket{C.RESET}")
    print(f"  {C.DIM}Ctrl+C en cualquier momento para cancelar.{C.RESET}\n")
    print(f"  {C.DIM}{'─' * 50}{C.RESET}\n")

    numero = preguntar("Nº de factura simplificada",
                       validar=validar_numero_ticket,
                       ejemplo="2726-012-813323")

    fecha_raw = preguntar("Fecha y hora",
                          validar=validar_fecha,
                          ejemplo="20/2/26 10:30  ó  20/02/2026")
    fecha = normalizar_fecha_raw(fecha_raw)

    tienda = preguntar("Tienda (dirección)", ejemplo="AVDA. VALENCIA 75")

    cp = preguntar("Código postal", ejemplo="12005",
                   validar=lambda v: None if re.match(r'^\d{5}$', v) else "Debe tener 5 dígitos")

    ultimos4 = preguntar("Últimos 4 dígitos de la tarjeta",
                         validar=validar_ultimos4, ejemplo="4102")

    total_raw = preguntar("Total del ticket (€)", validar=validar_numero, ejemplo="34.50")
    total = float(normalizar_decimal(total_raw))

    # ── Líneas ──
    print(f"\n  {C.DIM}{'─' * 50}{C.RESET}")
    print(f"  {C.BOLD}Líneas del ticket{C.RESET}  {C.DIM}(deja el producto en blanco para terminar){C.RESET}\n")

    lineas = []
    suma = 0.0

    while True:
        n = len(lineas) + 1
        print(f"  {C.CYAN}Línea {n}{C.RESET}")

        desc, _ = pedir_producto()

        if desc is None:
            if not lineas:
                print(f"  {C.RED}Añade al menos una línea.{C.RESET}\n")
                continue
            break

        try:
            es_peso_raw = input(f"  ¿Producto a peso? (s/N): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{C.YELLOW}Cancelado.{C.RESET}\n")
            sys.exit(0)
        es_peso = es_peso_raw == 's'

        if es_peso:
            cant_str   = preguntar("Cantidad (kg)", validar=validar_numero, ejemplo="0.450")
            precio_str = preguntar("Precio por kg (€/kg)", validar=validar_numero, ejemplo="5.99")
        else:
            cant_str   = preguntar("Cantidad (unidades)", validar=validar_numero, ejemplo="2")
            precio_str = preguntar("Precio unitario (€)", validar=validar_numero, ejemplo="1.45")

        cantidad = float(normalizar_decimal(cant_str))
        precio   = float(normalizar_decimal(precio_str))
        importe  = round(cantidad * precio, 2)
        suma    += importe

        lineas.append({
            "descripcion":     desc,
            "cantidad":        cantidad,
            "precio_unitario": precio,
            "importe":         importe,
            "es_peso":         1 if es_peso else 0,
        })

        cant_fmt = f"{cantidad:.3f} kg" if es_peso else f"{cantidad:g}x"
        print(f"  {C.GREEN}✓ {desc}  {cant_fmt}  ×  {precio:.2f} €  =  {importe:.2f} €{C.RESET}\n")

    # ── Resumen + gestión de discrepancias ──
    while True:
        limpiar_pantalla()
        print(f"\n  {C.BOLD}Resumen del ticket{C.RESET}\n")
        print(f"  Nº factura : {C.WHITE}{numero}{C.RESET}")
        print(f"  Fecha      : {fecha}")
        print(f"  Tienda     : {tienda}  ({cp})")
        print(f"  Tarjeta    : ···{ultimos4}")
        print(f"\n  {C.DIM}{'─' * 50}{C.RESET}")
        for i, l in enumerate(lineas, 1):
            print(f"  {i:>2}. {l['descripcion']:<35} {l['importe']:>7.2f} €")
        print(f"  {C.DIM}{'─' * 50}{C.RESET}")

        diff = round(total - suma, 2)
        color_suma = C.GREEN if abs(diff) < 0.02 else C.YELLOW
        print(f"  {'Suma líneas':<38} {color_suma}{suma:>7.2f} €{C.RESET}")
        print(f"  {'Total ticket':<38} {C.BOLD}{total:>7.2f} €{C.RESET}")

        hay_error = abs(diff) >= 0.02
        if hay_error:
            print(f"\n  {C.YELLOW}⚠  Diferencia: {diff:+.2f} €{C.RESET}  "
                  f"{C.DIM}(¿falta una línea, descuento o error de introducción?){C.RESET}")

        print()
        if hay_error:
            print(f"  {C.DIM}g{C.RESET}  Guardar de todos modos")
            print(f"  {C.DIM}m{C.RESET}  Modificar (añadir/quitar líneas)")
            print(f"  {C.DIM}c{C.RESET}  Cancelar sin guardar")
            opciones = ['g', 'm', 'c']
            prompt = "  Opción (g/m/c): "
        else:
            print(f"  {C.DIM}g{C.RESET}  Guardar")
            print(f"  {C.DIM}m{C.RESET}  Modificar (añadir/quitar líneas)")
            print(f"  {C.DIM}c{C.RESET}  Cancelar sin guardar")
            opciones = ['g', 'm', 'c']
            prompt = "  Opción (g/m/c): "

        try:
            accion = input(prompt).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.YELLOW}Cancelado.{C.RESET}\n")
            sys.exit(0)

        if accion == 'c':
            print(f"\n  {C.YELLOW}No guardado.{C.RESET}\n")
            return

        elif accion == 'm':
            # ── Modo modificación ──
            limpiar_pantalla()
            print(f"\n  {C.BOLD}Modificar líneas{C.RESET}\n")
            for i, l in enumerate(lineas, 1):
                cant_fmt = f"{l['cantidad']:.3f} kg" if l['es_peso'] else f"{l['cantidad']:g}x"
                print(f"  {C.CYAN}{i:>2}{C.RESET}  {l['descripcion']:<35} "
                      f"{cant_fmt}  ×  {l['precio_unitario']:.2f} €  =  {l['importe']:.2f} €")
            print()
            print(f"  {C.DIM}Escribe el número de una línea para borrarla,")
            print(f"  'a' para añadir una línea nueva, o Enter para volver al resumen.{C.RESET}")

            while True:
                try:
                    op = input("  > ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    break
                if not op:
                    break
                elif op == 'a':
                    # Añadir línea nueva
                    print()
                    desc, _ = pedir_producto()
                    if desc is None:
                        break
                    try:
                        es_peso_raw = input(f"  ¿Producto a peso? (s/N): ").strip().lower()
                    except (KeyboardInterrupt, EOFError):
                        break
                    es_peso = es_peso_raw == 's'
                    if es_peso:
                        cant_str   = preguntar("Cantidad (kg)",       validar=validar_numero, ejemplo="0.450")
                        precio_str = preguntar("Precio por kg (€/kg)", validar=validar_numero, ejemplo="5.99")
                    else:
                        cant_str   = preguntar("Cantidad (unidades)", validar=validar_numero, ejemplo="2")
                        precio_str = preguntar("Precio unitario (€)", validar=validar_numero, ejemplo="1.45")
                    cantidad = float(normalizar_decimal(cant_str))
                    precio   = float(normalizar_decimal(precio_str))
                    importe  = round(cantidad * precio, 2)
                    suma    += importe
                    lineas.append({"descripcion": desc, "cantidad": cantidad,
                                   "precio_unitario": precio, "importe": importe,
                                   "es_peso": 1 if es_peso else 0})
                    cant_fmt = f"{cantidad:.3f} kg" if es_peso else f"{cantidad:g}x"
                    print(f"  {C.GREEN}✓ Añadido: {desc}  {cant_fmt}  ×  {precio:.2f} €  =  {importe:.2f} €{C.RESET}")
                    break
                else:
                    try:
                        idx = int(op) - 1
                        if not (0 <= idx < len(lineas)):
                            raise ValueError
                        eliminada = lineas.pop(idx)
                        suma -= eliminada['importe']
                        print(f"  {C.YELLOW}✗ Eliminada: {eliminada['descripcion']}{C.RESET}")
                        break
                    except ValueError:
                        print(f"  {C.RED}Opción no válida.{C.RESET}")

        elif accion == 'g':
            break  # salir del while y guardar

    # ── Insertar en BD ──
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        tarjeta_id = obtener_o_crear_tarjeta(int(ultimos4))
        cursor.execute("""
            INSERT INTO tickets (numero_ticket, datetime, tienda, codigo_postal, total, tarjeta_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (numero, fecha, tienda, cp, total, tarjeta_id))
        ticket_id = cursor.lastrowid

        for l in lineas:
            producto_id = obtener_o_crear_producto(cursor, l["descripcion"])
            cursor.execute("""
                INSERT INTO lineas_ticket
                (ticket_id, descripcion_original, producto_id,
                 cantidad, precio_unitario, importe, es_peso)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ticket_id, l["descripcion"], producto_id,
                  l["cantidad"], l["precio_unitario"], l["importe"], l["es_peso"]))

        conn.commit()
        print(f"\n  {C.GREEN}✅ Ticket {numero} guardado correctamente ({len(lineas)} líneas).{C.RESET}\n")

        # Ofrecer categorizar los productos nuevos sin familia
        _categorizar_nuevos(cursor)

    except Exception as e:
        conn.rollback()
        print(f"\n  {C.RED}Error al guardar: {e}{C.RESET}\n")
    finally:
        conn.close()


# ── Modo: borrar ticket ──────────────────────────────────────────

def run_borrar():
    limpiar_pantalla()
    print(f"\n  {C.BOLD}Mercadona · Borrar ticket{C.RESET}")
    print(f"  {C.DIM}Las líneas se borrarán automáticamente (CASCADE).{C.RESET}\n")

    while True:
        try:
            query = input("  Nº de factura (o parte de él, q para salir): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if query.lower() == 'q':
            return
        if not query:
            continue

        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.numero_ticket, t.datetime, t.tienda, t.total,
                   COUNT(l.id) as n_lineas
            FROM tickets t
            LEFT JOIN lineas_ticket l ON l.ticket_id = t.id
            WHERE t.numero_ticket LIKE ?
            GROUP BY t.id
            ORDER BY t.datetime DESC
        """, (f"%{query}%",))
        resultados = cursor.fetchall()
        conn.close()

        if not resultados:
            print(f"  {C.YELLOW}Sin resultados para «{query}».{C.RESET}\n")
            continue

        print(f"\n  {C.DIM}{len(resultados)} resultado(s):{C.RESET}\n")
        for idx, (tid, num, dt, tienda, total, n_lin) in enumerate(resultados, 1):
            print(f"  {C.CYAN}{idx:>2}{C.RESET}  {num}  {dt}  {tienda}  "
                  f"{C.BOLD}{total:.2f} €{C.RESET}  {C.DIM}({n_lin} líneas){C.RESET}")

        print(f"\n  {C.DIM}Número para borrar · Enter para nueva búsqueda · q para salir{C.RESET}")
        try:
            sel = input("  Selecciona: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if sel == 'q':
            return
        if not sel:
            continue

        try:
            idx = int(sel) - 1
            if not (0 <= idx < len(resultados)):
                raise ValueError
        except ValueError:
            print(f"  {C.RED}Número no válido.{C.RESET}")
            continue

        tid, num, dt, tienda, total, n_lin = resultados[idx]
        print(f"\n  {C.YELLOW}⚠  Vas a borrar:{C.RESET}")
        print(f"     {num}  ·  {dt}  ·  {tienda}  ·  {total:.2f} €  ·  {n_lin} líneas")

        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.descripcion, l.cantidad, l.precio_unitario, l.importe, l.es_peso
            FROM lineas_ticket l
            JOIN productos p ON l.producto_id = p.id
            WHERE l.ticket_id = ?
            ORDER BY l.id
        """, (tid,))
        lineas = cursor.fetchall()
        conn.close()

        print()
        for desc, cant, precio, imp, es_p in lineas:
            cant_fmt = f"{cant:.3f} kg" if es_p else f"{cant:g}x"
            print(f"     {desc:<38} {cant_fmt}  {precio:.2f} €  =  {imp:.2f} €")

        print()
        try:
            confirm = input(f"  {C.RED}{C.BOLD}¿Confirmar borrado? (s/N): {C.RESET}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return

        if confirm != 's':
            print(f"  {C.DIM}Cancelado.{C.RESET}\n")
            continue

        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("DELETE FROM tickets WHERE id = ?", (tid,))
        conn.commit()
        conn.close()
        print(f"  {C.GREEN}✅ Ticket {num} borrado.{C.RESET}\n")


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Introducción y gestión manual de tickets de Mercadona.",
        epilog="""
Ejemplos:
  python3 manual.py            Introduce un ticket nuevo línea a línea
  python3 manual.py --borrar   Busca un ticket por nº de factura y lo borra

Formato del nº de factura: XXXX-XXX-XXXXXX  (ej: 2726-012-813323)
Formatos de fecha aceptados: DD/MM/AAAA HH:MM  o abreviados como  20/2/26 9:5
Los decimales aceptan tanto punto como coma: 1.45 = 1,45
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--borrar", action="store_true",
                        help="Busca un ticket por nº de factura y lo borra (con todas sus líneas)")
    args = parser.parse_args()

    if args.borrar:
        run_borrar()
    else:
        run_introducir()
