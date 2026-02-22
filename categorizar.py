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

# ── Auto-categorización ─────────────────────────────────────────

REGLAS_AUTOCATEGORIA = [

    # ----- 15. Comidas preparadas -----
    # Va primero para que "PIZZA", "ARROZ AL HORNO", "GAZPACHO", etc.
    # no sean capturados por reglas más genéricas de otras familias.
    (["BENTO", "SALMOREJO", "GAZPACHO", "TORTILLA PATATA", "POLLO TERIYAKI",
      "FABADA", "ENSALADILLA", "CALLOS", "COCIDO", "CROQUETA", "PASTA C/POLLO",
      "ARROZ AL HORNO", "ARROZ HORNO", "LS ARROZ", "LS P PIZZA",
      "PIZZA FORMAGGI", "PIZZA JAMON", "PIZZA MEDITT", "PIZZA PROSCIUTTO",
      "PIZZA MARGAR", "PIZZA CUATRO", "PIZZA BARBAR", "PIZZA ATUN",
      "PIZZA CAMPES", "COULANT", "CARROT CAKE", "OREJA PRECO",
      "CALAMAR SALSA", "CALAMARES TINTA", "CHILI CON CARNE",
      "CALDO COCIDO", "CALDO POLLO", "CALDO PESCADO", "CALDO VERDUR",
      "ALITAS POLLO ASADAS", "SANGRE HERVIDA", "TSATSIKI",
      "MOUSSE FINAS", "PATÉ", "TRADICIONAL", "ALAS PARTIDAS"], 15),

    # ----- 1. Frutas y verduras -----
    (["AGUACATE", "AJO", "AJOS", "ALBARICOQUE", "ALCACHOFA", "ALMENDRA",
      "APIO", "ARÁNDANO", "BANANA", "BATATA", "BREVAS", "BROCOLI", "BROCOLI",
      "CALABACIN", "CARDO", "CEBOLLA", "CEBOLLINO", "CEBOLLITAS", "CHAMPIÑON",
      "CIRUELA", "COGOLLOS", "COLIFLOR", "DATIL", "ENDIBIA",
      "ESPÁRRAGO", "ESPARRAGO", "ESP VERDE", "ESP. CORTO",
      "ESPINACA", "FRAMBUESA", "FRESÓN", "FRESA ",
      "HABAS BABY", "HIGO", "JUDÍA", "JUDIA", "KAKI", "KIWI",
      "LIMON ", "LIMÓN ", "MANDARINA", "MANGO ", "MANZANA",
      "MAÍZ COCIDO", "MELOCOT", "MELON", "MELÓN",
      "MIX DE SETAS", "MORA ", "NARANJA", "NECTARINA",
      "NUEZ NATURAL", "NUEZ TROCEADA", "ANACARDO", "CACAHUETE",
      "OREJONES", "PARAGUAYO", "PASAS SULTAN", "PASAS ",
      "PATATA", "PEPINO", "PERA ", "PIMIENTO ROJO", "PIMIENTO TRICO",
      "PIMIENTO TIRAS", "PIMIENTO FREIR", "PIMIENTO CHORICERO",
      "PIMIENTO SEMIPI", "PI. CALABAZA", "CASTAÑAS",
      "PLATANO", "PLÁTANO", "PUERRO", "RABANITOS", "REMOLACHA",
      "REPOLLO", "ROJA ACIDULCE", "SANDÍA", "SETA", "SALTEADO",
      "T.CHERRY", "TOMATE CHERRY RAMA", "TOMATE CANARIO", "TOMATE ROSA",
      "TOMATE ENSALADA", "TOMATE RAMA", "TOMATE PERA TARR",
      "UVA", "ZANAHORIA", "CANÓNIGOS", "CANONIGOS", "RUCULA",
      "BERENJENA", "ALBAHACA", "HIERBABUENA", "ROMERO", "TOMILLO",
      "ORÉGANO", "DUO CANONIGOS", "3 VEGETALES", "CEBOLLINO",
      "RABANITOS", "MIX DE SETAS", "CHAMPIÑÓN", "ALCACHOFA GRANDE",
      "PIMIENTA NEGRA GRANO", "FRESA", "LIMON", "MORA", "MANGO",
      "PAJARITAS VEGETALES", "PIP CALABAZA AGUASAL", "TOMATE PERA"], 1),

    # ----- 2. Carne y charcutería -----
    (["POLLO", "PECHUGA", "MUSLO", "CONTRAMUSLO", "CUARTO TRASERO",
      "FILETE", "TERNERA", "CERDO", "CORDERO", "LOMO", "COSTILLA",
      "COSTILLEJA", "CHULETA", "HAMBURGUESA", "BURGER", "SALCHICHA",
      "CHORIZO", "JAMON", "JAMÓN", "MORTADELA", "FUET", "BACON",
      "TACO BACON", "PANCETA", "PAVO ", "CONEJO", "PATO ", "MAGRET",
      "ENTRECOT", "SOLOMILLO", "SECRETO", "ESCALOPIN ",
      "CARRILLADA", "LONGANIZA", "STICKS LONGANIZA", "TAQUITOS CHORIZO",
      "MAXI YORK", "CINTAS DE BACON", "MORCILLA",
      "ARREGLO PAELLA", "ARREGLO COCIDO", "MINI BURGER", "MAXI HAMBURGUESA",
      "CABEZA CERDO", "PALETILLA", "ALAS PICANTES",
      "LS POLLO", "PACK-4 SALCH", "SALCHICHAS", "PECHUGA PAV",
      "JAMON PAVO", "CERDO TACOS", "CHULETAS MIXTAS",
      "CH. PALO", "BURGER M VA", "BURGER VACUN",
      "RULITO CABRA", "MINI BURGER MIXTA"], 2),

    # ----- 3. Pescado y marisco -----
    (["SALMON", "SALMÓN", "ATÚN", "ATUN ", "MERLUZA", "BACALAO", "BACALADILLA",
      "DORADA", "LUBINA", "TRUCHA", "SARDINA", "SARDINILLA", "CABALLA",
      "ANCHOA", "GAMBA", "LANGOSTINO", "MEJILLON", "MEJILLÓN", "BERBERECHO",
      "CALAMAR", "PULPO", "SEPIA", "GALERA", "PESCADO", "MARISCO",
      "ESCALOPIN SALM", "RODAJA SALM", "FILETE LUBINA", "FILETE GALLINETA",
      "FLTE BACALAO", "PORCION MERL", "PATA PULPO", "PATAS DE PULPO",
      "PULPO COCIDO", "PALITOS SURIMI", "SURIMI",
      "FTE ANCHOA", "ANCHOA OLIVA", "SARDINAS OLIVA", "SARDINAS ANCHO",
      "SARDINILLA RE", "MEJ. CHILE", "CALAMARES",
      "COCKTAIL MEZCLA", "COCKTAIL RODEO", "COCKTAIL CRUNCHY"], 3),

    # ----- 4. Lácteos y huevos -----
    (["LECHE ENTERA", "LECHE SEMI", "LECHE S/LACT", "LECHE P6",
      "YOGUR", "YOGURT", "YOG.", "GRIEGO", "QUESO", "MANTEQUILLA",
      "NATA PARA", "NATA ", "HUEVO", "HUEVOS",
      "KEFIR", "CUAJADA", "REQUESON", "REQUESÓN", "RICOTTA",
      "MOZZARELLA", "BRIE", "CAMEMBERT", "NATILLA", "FLAN",
      "BATIDO", "PETIT ", "LCASEI", "GELLY", "RULITO",
      "BEBIDA AVENA", "Q RALLADO", "Q BURGOS", "Q SEMI", "Q VIEJO",
      "Q. AÑEJO", "PERLAS MOZZ", "GRANA PADANO RALLADO",
      "6 HUEVOS", "12 HUEVOS", "18 HUEVOS",
      "ARROZ CON LECHE", "COPA CHOCOLATE",
      "MOZZARELLA FRESCA", "QUESO FRESCO", "QUESO CAMEMBERT",
      "QUESO SANDWICH", "QUESO LONCHAS OVEJA",
      "GRIEGO AZUCAR", "MINI RELLENOS DE LEC",
      "MOUSSE FINAS HIERBAS"], 4),

    # ----- 5. Pan y bollería -----
    (["PAN DE ESPIGA", "PAN DE PUEBLO", "PAN H BRIOCHE", "PAN HOT DOG",
      "PAN VIENA", "PAN BLANCO", "PAN ACEITE", "PAN RALLADO",
      "PAN TOSTADO", "BARRA DE PAN", "BAGUETTE", "BOCADILLO",
      "PANECILLO", "PANEC.", "PULGUITAS", "ROSQUILLA",
      "BERLINA CACAO", "MINI BOCADOS", "MONA BAÑADA",
      "MAGDALENA", "BIZCOCHO", "GALLETA", "CRACKERS", "REGAÑAS",
      "TORTILLA AVENA", "TORTILLAS MEX", "MASA EMPANADA", "EMPANADA",
      "ANITINES", "TOSTADITAS", "MINI TOSTAS", "MINI BISCOTTE",
      "BAGEL", "MINI SALADAS", "PICOS CAMPERO", "PALITOS ACEITUNAS",
      "TORTITA CAMPESTRE", "HARINA", "IMPULSOR", "MUFFIN CHOCO",
      "DORAYAKI", "MEDIALUNAS", "GALL DIGESTIVE", "GALL.BAÑADA",
      "COOKIES CHOCO", "BARRITAS CHIPS", "GALLETA RELIEVE",
      "PALMERITAS", "MINI RELLENO LECHE", "MINI CARITA CACAO",
      "30% INTEGRAL", "T. 100%INTEG", "100% INTEGRAL",
      "MINI BOCADOS", "PAN VIENA REDONDO", "3 BOCADILLOS",
      "5 BOCADILLOS"], 5),

    # ----- 6. Conservas y legumbres -----
    (["LENTEJA", "GARBANZO", "ALUBIA", "JUDION",
      "ATUN CLARO", "FTES ATÚN", "SARDINAS OLIVA",
      "TOMATE TRITURADO", "TOMATE TROCEADO",
      "HUMMUS", "ALTRAMUZ", "ACEITUNA SIN HUESO", "ACEITUNA S/HUESO",
      "A. NEGRAS S/HUESO", "PEPINILLO", "BANDERILLAS",
      "MEJILLONES ESCABECHE", "PIMIENTO ASADO",
      "FRITADA", "PISTO", "REMOLACHA EN TIRAS", "TOM.RECETA",
      "PIPARRA", "ALCAPARRAS", "CHUCRUT", "PICADILLO",
      "ESPÁRRAGO CORTO", "ESP. CORTO MEDIO", "ESPARRAGO MEDIANO",
      "SARDINA AHUMADA", "SARDINA OLIVA", "SARDINILLA RE. SAL",
      "FTE ANCHOA OLIVA", "ANCHOA OLIVA PACK",
      "TOMATE SECO", "BERBERECHOS"], 6),

    # ----- 7. Pasta, arroz y cereales -----
    (["SPAGHETTI", "ESPAGUETI", "MACARRON", "TALLARÍN", "LASAÑA",
      "NOODLES", "FIDEO CABELLO", "PENNE",
      "ARROZ BOMBA", "ARROZ BASMATI", "ARROZ REDONDO", "COUS COUS",
      "QUINOA", "AVENA MOLIDA", "MUESLI", "CEREAL RELL",
      "FRESA ARÁNDANOS AVEN", "CACAO INSTANT",
      "MAIZ PALOMITAS", "MAÍZ PALOMITAS"], 7),

    # ----- 8. Aceites, salsas y condimentos -----
    (["ACEITE GIRASOL", "ACEITE OLIVA", "VINAGRE BALSAM", "VINAGRE ",
      "MAYONESA", "KETCHUP", "MOSTAZA",
      "SALSA DE SOJA", "SALSA MEXICANA", "TOMATE FRITO",
      "AZUCAR", "AZÚCAR", "NATA PARA COCINAR", "LECHE DE COCO",
      "HARINA DE TRIGO", "PAN RALLADO", "IMPULSOR",
      "PIMIENTO CHORICERO", "ORÉGANO", "PIMIENTA NEGRA",
      "ALCAPARRAS", "TOMATE SECO", "TOMATE PERA TARRINA"], 8),

    # ----- 9. Snacks y dulces -----
    (["PAT. CLASS", "PATATAS SERRANO", "PATATA PAJA", "PATATAS ALLIOLI",
      "PATATAS LISAS", "NACHOS", "PALOMITAS",
      "CHICLE ORIGINAL", "CHICLE HIERBABUENA", "BOTE CHICLE",
      "DIVERXUXES", "CUQUIS", "GOLOSINAS MIX", "GOLOSINA FRESI",
      "BANDERILLAS DULCES", "MINI PEANUT CUPS",
      "SNACK PIPAS", "PIPA GIGANTE", "SNACK CALABAZA",
      "COCKTAIL GALL SALADA",
      "MERMELADA", "MINI BOMBONES", "SURTIDO DULCES", "SURTIDO TURR",
      "SURTIDO APER", "TARTA ABUELA", "COPA CHOCOLATE",
      "RED VELVET", "CREMA AVELLANA", "CREMA 100% CACAHUETE",
      "MINI CONO NATA", "COOKIE DOUGH", "MINI SANDWICH COOKIE",
      "BOMBITAS DE MAIZ",
      "LONGANIZA APERIT", "FUET ESPETEC", "TAQUITOS CHOR",
      "STICKS LONGANIZA", "BARRITA MANGO",
      "PALITO FRUTOS", "ANACARDO NATURAL", "NUEZ TROCEADA",
      "CASTAÑAS PELADAS",
      "ARROZ CON LECHE", "NATILLA C/GALLETA", "PETIT SABORES",
      "DORAYAKI HACEND", "MINI RELLENO LECHE", "MINI CARITA CACAO",
      "MUFFIN CHOCO", "BERLINA CACAO", "MEDIALUNAS",
      "GALL.BAÑADA CHOCOBLA", "GALL DIGESTIVE CHOCO",
      "COOKIES CHOCO", "BARRITAS CHIPS", "GALLETA RELIEVE",
      "PALMERITAS", "MINI BOCADOS", "PATÉ SUAVE",
      "GARFITOS", "TORTITAS ARROZ"], 9),

    # ----- 10. Bebidas -----
    (["AGUA MINERAL", "AGUA DESTILADA", "AGUA FUERTE",
      "AGUA MINERAL PACK", "AGUA MINERAL 1L", "AGUA SIN GAS",
      "BRONCHALES", "ZUMO", "REFRESCO", "GASEOSA",
      "CERVEZA", "CERV ", "C 0,0 TOSTADA", "CERVEZA TOSTADA",
      "CERV TOSTADA", "CERV PACK",
      "VINO RIOJA", "RIOJA CRIANZA", "CAMPO BORJA", "FINO MORILES",
      "CAFÉ GRANO", "CAP. EXTRAFORTE", "GRANO EXTRA",
      "ICE TEA", "ISOTÓNICO", "ISOTÓNICA", "ISO LIMÓN",
      "LIMON EXPRIMIDO", "PACK 4X500 COLA", "BEBIDA AVENA",
      "COCA COLA", "COLA ZERO", "CORTES GAS", "HORCHATA",
      "CACAO INSTANT", "BEBER FRESA", "LECHE DE AVENA",
      "ZUMO DE PIÑA", "ZUMO MANZANA", "ZUMO PIÑA REFRIG"], 10),

    # ----- 11. Congelados -----
    (["GUISANTES MUY TIERNO", "HABITAS MUY TIERNAS", "HIELO CUBITO",
      "HELADO BROWNIE", "MINI SANDWICH COOKIE", "COOKIE DOUGH",
      "FIGURITAS MERLUZA", "HELADO FRESA", "HELADO LIMA",
      "HELADO MOCHI", "MINI CONO NATA",
      "PALOMITAS SAL PACK", "MINI 6"], 11),

    # ----- 12. Droguería y limpieza -----
    (["DETERGENTE", "SUAVIZANTE", "LAVAVAJILL", "FRIEGASUELOS",
      "BAYETA", "ESTROPAJO", "ROLLO HOGAR", "PAPEL ALUMINIO",
      "PAPEL VEGETAL", "FILM TRANSP",
      "BOLSA BASURA", "BOLSA PLASTICO", "CÁPSULA ROPA", "CAPSULA ROPA",
      "GEL WC", "LIMPIADOR", "LEJIA", "LEJÍA", "AMONIACO",
      "LIMPIAHORNOS", "QUITAGRASA", "LIMPIAMAQUINAS",
      "CRISTALES MULTIUSOS", "TOALLITAS ANTIT",
      "VARITAS DIF", "RECAMBIO LIQUIDO",
      "COMP.NORMAL C/A", "COMP.NOCHE C/A", "COM.NORMAL C/A",
      "FOSFOROS", "32 PASTILLAS ENCENDI",
      "40 B.CIERRA", "SAL LAVAVAJILLAS",
      "CEPILLO LAVAR", "GUANTE RESIS", "DISCOS DESM",
      "LIMPIADOR DESINFECT", "PLATO GRANDE"], 12),

    # ----- 13. Higiene y cuidado personal -----
    (["CHAMPU", "CHAMPÚ", "GEL DERMO", "GEL DUCHA", "JABÓN", "JABON",
      "DESODORANTE", "DEO ROLL", "CREMA HIDRAT",
      "PASTA DENTAL", "COLGATE", "CEPILLO DENT", "MAQUINILLA",
      "COMPRESAS", "TAMPÓN", "COLONIA", "HIDRATANTE", "PROTECTOR",
      "HIGIENICO DOBLE", "PAPEL HIGIÉNICO", "PAPEL HIGIENICO",
      "ARCOS DENTALES", "2 EN 1 WHITE",
      "STICK ANTIROZADURAS", "DEO ROLL-ON INV",
      "TOALL. DESODOR", "DISCOS DESM REDONDO"], 13),

    # ----- 14. Otras -----
    (["BASE PIZZA FAMILIAR", "CARBÓN VEGETAL", "PARKING",
      "FOSFOROS MADERA"], 14),
]


def sugerir_categorias():
    """
    Aplica las reglas de auto-categorización a los productos sin familia.
    Devuelve lista de dicts con sugerencias (sin modificar la BD).
    """
    sin_familia = cargar_productos_sin_familia()
    sugerencias = []

    conn = obtener_conexion()
    cursor = conn.cursor()

    for producto in sin_familia:
        desc = producto["descripcion"].upper()
        for palabras_clave, familia_id in REGLAS_AUTOCATEGORIA:
            if any(kw.upper() in desc for kw in palabras_clave):
                cursor.execute("SELECT Descripcion FROM Familias WHERE Fam_id = ?", (familia_id,))
                row = cursor.fetchone()
                if row:
                    sugerencias.append({
                        "producto_id":    producto["id"],
                        "descripcion":    producto["descripcion"],
                        "familia_id":     familia_id,
                        "familia_nombre": row[0]
                    })
                break  # primera regla que encaja

    conn.close()
    return sugerencias


def aplicar_autocategorizacion():
    """
    Aplica las sugerencias de auto-categorización directamente en la BD.
    Solo actúa sobre productos que aún no tienen familia asignada.
    """
    sugerencias = sugerir_categorias()
    if not sugerencias:
        print("ℹ️  No hay productos sin familia que encajen con las reglas.")
        return

    conn = obtener_conexion()
    cursor = conn.cursor()

    for s in sugerencias:
        cursor.execute(
            "UPDATE productos SET familia_id = ? WHERE id = ? AND familia_id IS NULL",
            (s["familia_id"], s["producto_id"])
        )
        print(f"  ✅ {s['descripcion']:<40} → {s['familia_nombre']}")

    conn.commit()
    conn.close()
    print(f"\n{len(sugerencias)} productos categorizados automáticamente.")


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
  python3 categorizar.py --auto       Aplica auto-categorización a productos sin familia

Controles en modo normal:
  número  Asigna esa familia    s  Salta    u  Deshace el último    q  Sale
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--lista",    action="store_true", help="Lista todos los productos agrupados por familia")
    group.add_argument("--buscar",   action="store_true", help="Busca y edita cualquier producto directamente")
    group.add_argument("--tarjetas", action="store_true", help="Gestiona las etiquetas de las tarjetas de pago")
    group.add_argument("--auto",     action="store_true", help="Aplica auto-categorización a productos sin familia y sale")
    args = parser.parse_args()

    if args.lista:
        run_lista()
    elif args.buscar:
        run_buscar()
    elif args.tarjetas:
        run_tarjetas()
    elif args.auto:
        print("🔍 Aplicando auto-categorización...\n")
        aplicar_autocategorizacion()
    else:
        run_categorizar()
