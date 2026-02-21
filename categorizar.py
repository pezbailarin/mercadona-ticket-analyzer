#!/usr/bin/env python3
"""
categorizar.py — Gestión de categorías de productos.

Modos:
    python3 categorizar.py              # categorizar los productos sin familia (uno a uno)
    python3 categorizar.py --lista      # ver todos los productos con su categoría actual
    python3 categorizar.py --buscar     # buscar y editar cualquier producto directamente
"""


import argparse

import sys
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
from db import obtener_conexion


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


def cargar_familias():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT Fam_id, Descripcion, Emoji FROM Familias ORDER BY Fam_id")
    familias = [{"id": r[0], "nombre": r[1], "emoji": r[2]} for r in cursor.fetchall()]
    conn.close()
    return familias


def cargar_productos_sin_familia():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.descripcion, ROUND(SUM(l.importe), 2) as gasto,
               COUNT(DISTINCT l.ticket_id) as num_tickets
        FROM productos p
        JOIN lineas_ticket l ON l.producto_id = p.id
        WHERE p.familia_id IS NULL
        GROUP BY p.id
        ORDER BY gasto DESC
    """)
    productos = [{"id": r[0], "descripcion": r[1], "gasto": r[2], "num_tickets": r[3],
                  "familia_id": None, "familia_nombre": None, "familia_emoji": None}
                 for r in cursor.fetchall()]
    conn.close()
    return productos


def cargar_todos_productos():
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.descripcion, ROUND(SUM(l.importe), 2) as gasto,
               COUNT(DISTINCT l.ticket_id) as num_tickets,
               p.familia_id, f.Descripcion, f.Emoji
        FROM productos p
        JOIN lineas_ticket l ON l.producto_id = p.id
        LEFT JOIN Familias f ON p.familia_id = f.Fam_id
        GROUP BY p.id
        ORDER BY f.Descripcion NULLS FIRST, p.descripcion
    """)
    productos = [{"id": r[0], "descripcion": r[1], "gasto": r[2], "num_tickets": r[3],
                  "familia_id": r[4], "familia_nombre": r[5], "familia_emoji": r[6]}
                 for r in cursor.fetchall()]
    conn.close()
    return productos


def asignar_familia(producto_id, familia_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("UPDATE productos SET familia_id = ? WHERE id = ?", (familia_id, producto_id))
    conn.commit()
    conn.close()


def desasignar_familia(producto_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("UPDATE productos SET familia_id = NULL WHERE id = ?", (producto_id,))
    conn.commit()
    conn.close()


def mostrar_menu_familias(familias):
    print(f"\n  {C.DIM}{'─' * 50}{C.RESET}")
    mitad = (len(familias) + 1) // 2
    for i in range(mitad):
        izq = familias[i]
        etiq_izq = f"  {C.CYAN}{izq['id']:>2}{C.RESET}  {izq['emoji']} {izq['nombre']:<24}"
        der = familias[i + mitad] if i + mitad < len(familias) else None
        etiq_der = f"{C.CYAN}{der['id']:>2}{C.RESET}  {der['emoji']} {der['nombre']}" if der else ""
        print(f"{etiq_izq}{etiq_der}")
    print(f"\n  {C.DIM}{'─' * 50}")
    print(f"   s  Saltar      u  Deshacer último      q  Guardar y salir{C.RESET}\n")


def editar_producto(producto, familias, familias_por_id):
    """Muestra el producto y pide una familia. Devuelve True si se asignó."""
    print(f"\n  {C.BOLD}{C.WHITE}{producto['descripcion']}{C.RESET}")
    print(f"  {C.DIM}Gasto acumulado: {producto['gasto']:.2f} €  ·  "
          f"aparece en {producto['num_tickets']} ticket(s){C.RESET}")
    if producto.get("familia_nombre"):
        print(f"  {C.DIM}Categoría actual: {producto.get('familia_emoji','')} "
              f"{producto['familia_nombre']}{C.RESET}")
    else:
        print(f"  {C.YELLOW}Sin categoría{C.RESET}")
    mostrar_menu_familias(familias)
    while True:
        try:
            respuesta = input("  Familia (número, s=saltar, q=salir): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{C.YELLOW}Saliendo.{C.RESET}\n")
            sys.exit(0)
        if respuesta == "q":
            sys.exit(0)
        elif respuesta == "s":
            return False
        else:
            try:
                fam_id = int(respuesta)
                if fam_id not in familias_por_id:
                    raise ValueError
            except ValueError:
                print(f"  {C.RED}Opción no válida.{C.RESET}")
                continue
            asignar_familia(producto["id"], fam_id)
            fam = familias_por_id[fam_id]
            print(f"  {C.GREEN}✅ {producto['descripcion']} → {fam['emoji']} {fam['nombre']}{C.RESET}")
            return True


# ── Modo 1: categorizar sin familia ─────────────────────────────

def run_categorizar():
    familias = cargar_familias()
    familias_por_id = {f["id"]: f for f in familias}
    productos = cargar_productos_sin_familia()
    total = len(productos)

    if total == 0:
        print(f"\n{C.GREEN}✅ Todos los productos tienen familia asignada.{C.RESET}\n")
        return

    historial = []
    i = 0
    while i < len(productos):
        producto = productos[i]
        asignados = len(historial)
        limpiar_pantalla()
        print(f"\n  {C.BOLD}Mercadona · Categorización interactiva{C.RESET}  "
              f"{C.DIM}(asignados: {asignados}/{total} · quedan: {total - asignados}){C.RESET}")
        print(f"\n  {C.BOLD}{C.WHITE}{producto['descripcion']}{C.RESET}")
        print(f"  {C.DIM}Gasto acumulado: {producto['gasto']:.2f} €  ·  "
              f"aparece en {producto['num_tickets']} ticket(s){C.RESET}")
        mostrar_menu_familias(familias)
        try:
            respuesta = input("  Familia: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{C.YELLOW}Saliendo sin más cambios.{C.RESET}\n")
            sys.exit(0)
        if respuesta == "q":
            break
        elif respuesta == "s":
            i += 1
        elif respuesta == "u":
            if historial:
                ultimo_id = historial.pop()
                desasignar_familia(ultimo_id)
                i = max(0, i - 1)
                while i > 0 and productos[i]["id"] != ultimo_id:
                    i -= 1
                productos[i]["familia_id"] = None
            else:
                print(f"  {C.DIM}No hay nada que deshacer.{C.RESET}")
                input("  [Enter para continuar]")
        else:
            try:
                fam_id = int(respuesta)
                if fam_id not in familias_por_id:
                    raise ValueError
            except ValueError:
                print(f"  {C.RED}Opción no válida.{C.RESET}")
                input("  [Enter para continuar]")
                continue
            asignar_familia(producto["id"], fam_id)
            historial.append(producto["id"])
            producto["familia_id"] = fam_id
            fam = familias_por_id[fam_id]
            print(f"  {C.GREEN}✅ {producto['descripcion']} → {fam['emoji']} {fam['nombre']}{C.RESET}")
            i += 1

    limpiar_pantalla()
    asignados = len(historial)
    print(f"\n  {C.BOLD}Sesión finalizada{C.RESET}")
    print(f"  {C.GREEN}✅ Asignados en esta sesión: {asignados}{C.RESET}")
    restantes = total - asignados
    if restantes > 0:
        print(f"  {C.YELLOW}⏭  Pendientes: {restantes}{C.RESET}  "
              f"{C.DIM}(vuelve a ejecutar el script para continuar){C.RESET}")
    else:
        print(f"  {C.GREEN}🎉 Todos los productos están categorizados.{C.RESET}")
    print()


# ── Modo 2: listar todos los productos ──────────────────────────

def run_lista():
    productos = cargar_todos_productos()
    if not productos:
        print(f"\n{C.DIM}No hay productos en la base de datos.{C.RESET}\n")
        return

    limpiar_pantalla()
    familia_actual = "__inicio__"
    print(f"\n  {C.BOLD}Mercadona · Lista de productos ({len(productos)} total){C.RESET}\n")
    for p in productos:
        fam   = p["familia_nombre"] or "Sin categoría"
        emoji = p["familia_emoji"]  or "🗂️"
        if fam != familia_actual:
            familia_actual = fam
            print(f"\n  {C.CYAN}{C.BOLD}{emoji} {fam}{C.RESET}")
            print(f"  {C.DIM}{'─' * 46}{C.RESET}")
        print(f"    {p['descripcion']:<40} {C.DIM}{p['gasto']:>7.2f} €  {p['num_tickets']}x{C.RESET}")
    print()


# ── Modo 3: buscar y editar ──────────────────────────────────────

def run_buscar():
    familias     = cargar_familias()
    familias_por_id = {f["id"]: f for f in familias}

    while True:
        limpiar_pantalla()
        print(f"\n  {C.BOLD}Mercadona · Buscar y editar producto{C.RESET}  "
              f"{C.DIM}(q para salir){C.RESET}\n")
        try:
            query = input("  Buscar: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if query.lower() == "q":
            return
        if not query:
            continue

        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.descripcion, ROUND(SUM(l.importe), 2) as gasto,
                   COUNT(DISTINCT l.ticket_id) as num_tickets,
                   p.familia_id, f.Descripcion, f.Emoji
            FROM productos p
            JOIN lineas_ticket l ON l.producto_id = p.id
            LEFT JOIN Familias f ON p.familia_id = f.Fam_id
            WHERE p.descripcion LIKE ?
            GROUP BY p.id
            ORDER BY gasto DESC
        """, (f"%{query.upper()}%",))
        resultados = [{"id": r[0], "descripcion": r[1], "gasto": r[2], "num_tickets": r[3],
                       "familia_id": r[4], "familia_nombre": r[5], "familia_emoji": r[6]}
                      for r in cursor.fetchall()]
        conn.close()

        if not resultados:
            print(f"\n  {C.YELLOW}Sin resultados para «{query}».{C.RESET}")
            input("  [Enter para nueva búsqueda]")
            continue

        print(f"\n  {C.DIM}{len(resultados)} resultado(s):{C.RESET}\n")
        for idx, p in enumerate(resultados, 1):
            fam_str = (f"{p['familia_emoji']} {p['familia_nombre']}"
                       if p["familia_nombre"] else f"{C.YELLOW}Sin categoría{C.RESET}")
            print(f"  {C.CYAN}{idx:>2}{C.RESET}  {p['descripcion']:<40} "
                  f"{C.DIM}{p['gasto']:>7.2f} €{C.RESET}  {fam_str}")

        print(f"\n  {C.DIM}Número para editar · Enter para nueva búsqueda · q para salir{C.RESET}")
        try:
            sel = input("  Selecciona: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if sel == "q":
            return
        if not sel:
            continue
        try:
            idx = int(sel) - 1
            if not (0 <= idx < len(resultados)):
                raise ValueError
        except ValueError:
            print(f"  {C.RED}Número no válido.{C.RESET}")
            input("  [Enter para continuar]")
            continue

        limpiar_pantalla()
        editar_producto(resultados[idx], familias, familias_por_id)
        input(f"\n  {C.DIM}[Enter para continuar buscando]{C.RESET}")


# ── Main ─────────────────────────────────────────────────────────

# ── Gestión de tarjetas ─────────────────────────────────────────

def run_tarjetas():
    """Permite etiquetar las tarjetas con un nombre descriptivo."""
    limpiar_pantalla()
    print(f"\n  {C.BOLD}Mercadona · Etiquetas de tarjetas{C.RESET}\n")

    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id, ultimos4, descripcion FROM tarjetas ORDER BY id")
    tarjetas = cursor.fetchall()
    conn.close()

    if not tarjetas:
        print(f"  {C.DIM}No hay tarjetas en la base de datos.{C.RESET}\n")
        return

    for tid, ultimos4, desc in tarjetas:
        etiq = desc if desc else f"{C.YELLOW}sin etiqueta{C.RESET}"
        print(f"  {C.CYAN}{tid}{C.RESET}  ····{ultimos4}  {etiq}")

    print(f"\n  {C.DIM}Escribe el número de la tarjeta para editarla, Enter para salir.{C.RESET}")

    while True:
        try:
            sel = input("\n  Selecciona: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return
        if not sel:
            return
        try:
            tid = int(sel)
            tarjeta = next((t for t in tarjetas if t[0] == tid), None)
            if not tarjeta:
                raise ValueError
        except ValueError:
            print(f"  {C.RED}Número no válido.{C.RESET}")
            continue

        _, ultimos4, desc_actual = tarjeta
        print(f"  Tarjeta ····{ultimos4}  —  etiqueta actual: {C.WHITE}{desc_actual or '(ninguna)'}{C.RESET}")
        try:
            nueva = input(f"  Nueva etiqueta (Enter para borrarla): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return

        conn = obtener_conexion()
        conn.execute("UPDATE tarjetas SET descripcion = ? WHERE id = ?",
                     (nueva if nueva else None, tid))
        conn.commit()
        conn.close()

        # Actualizar lista en memoria
        tarjetas = [(t[0], t[1], nueva if nueva else None) if t[0] == tid else t
                    for t in tarjetas]
        print(f"  {C.GREEN}✓ Guardado.{C.RESET}")


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Sin argumentos: decidir automáticamente según si hay productos sin categoría
    import sys as _sys
    if len(_sys.argv) == 1:
        _conn = obtener_conexion()
        _cur  = _conn.cursor()
        _cur.execute("SELECT COUNT(*) FROM productos WHERE familia_id IS NULL")
        _sin_cat = _cur.fetchone()[0]
        _conn.close()
        if _sin_cat == 0:
            run_buscar()
            _sys.exit(0)

    parser = argparse.ArgumentParser(
        description="Gestión de categorías de productos Mercadona.",
        epilog="""
Ejemplos:
  python3 categorizar.py              Categoriza productos sin familia; si no hay, abre el buscador
  python3 categorizar.py --lista      Lista todos los productos agrupados por familia
  python3 categorizar.py --buscar     Busca y edita la categoría de cualquier producto
  python3 categorizar.py --tarjetas   Gestiona las etiquetas de las tarjetas de pago

Controles en modo normal:
  número  Asigna esa familia    s  Salta    u  Deshace el último    q  Sale
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--lista",    action="store_true", help="Lista todos los productos agrupados por familia")
    group.add_argument("--buscar",   action="store_true", help="Busca y edita cualquier producto directamente")
    group.add_argument("--tarjetas", action="store_true", help="Gestiona las etiquetas de las tarjetas de pago")
    args = parser.parse_args()

    if args.lista:
        run_lista()
    elif args.buscar:
        run_buscar()
    elif args.tarjetas:
        run_tarjetas()
    else:
        run_categorizar()
