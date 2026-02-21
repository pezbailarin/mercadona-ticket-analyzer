import re
import pdfplumber


def leer_pdf(ruta_pdf):
    """Lee un PDF página a página y devuelve todo el texto como string."""
    texto_completo = ""
    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            texto_completo += pagina.extract_text() + "\n"
    return texto_completo


# Regex compilados una sola vez para mayor eficiencia
_RE_FECHA_HORA  = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")
_RE_FACTURA     = re.compile(r"FACTURA SIMPLIFICADA:\s+([0-9\-]+)")
_RE_TOTAL       = re.compile(r"TOTAL\s+\(€\)\s+(\d+,\d+)")
_RE_TARJETA     = re.compile(r"\*\*\*\*\s+\*\*\*\*\s+\*\*\*\*\s+(\d{4})")
_RE_TIENDA      = re.compile(r"MERCADONA.*\n(.*)")
_RE_CP          = re.compile(r"\b(\d{5})\b")
_RE_PESO        = re.compile(r"^([\d,]+)\s+kg\s+([\d,]+)\s+€/kg\s+([\d,]+)$")
_RE_PROD_NORMAL = re.compile(r"^(\d+)\s+(.+)$")


def _parsear_linea_peso(linea_texto):
    """
    Intenta parsear una línea de detalle de peso.
    Devuelve (kg, precio_kg, importe) si encaja, o None si no es una línea de peso.
    """
    m = _RE_PESO.match(linea_texto.strip())
    if not m:
        return None
    return (
        float(m.group(1).replace(",", ".")),
        float(m.group(2).replace(",", ".")),
        float(m.group(3).replace(",", "."))
    )


def parsear_ticket(texto):
    """
    Extrae los datos relevantes de un ticket de Mercadona en texto plano.

    Devuelve un dict con las claves:
        datetime, numero_ticket, total, ultimos4, tienda, codigo_postal, lineas

    Cada elemento de 'lineas' contiene:
        descripcion, cantidad, precio_unitario, importe, es_peso
        - es_peso=True  → cantidad en kg, precio_unitario en €/kg
        - es_peso=False → cantidad en unidades, precio_unitario en €/unidad
    """
    datos = {}

    # ========================
    # DATOS DE CABECERA
    # ========================

    # Fecha y hora: DD/MM/YYYY HH:MM → ISO 8601 YYYY-MM-DD HH:MM
    m = _RE_FECHA_HORA.search(texto)
    if m:
        dia, mes, anio = m.group(1).split("/")
        datos["datetime"] = f"{anio}-{mes}-{dia} {m.group(2)}"

    # Número de factura simplificada
    m = _RE_FACTURA.search(texto)
    if m:
        datos["numero_ticket"] = m.group(1)

    # Total de la compra en euros
    m = _RE_TOTAL.search(texto)
    if m:
        datos["total"] = float(m.group(1).replace(",", "."))

    # Últimos 4 dígitos de la tarjeta con la que se pagó
    m = _RE_TARJETA.search(texto)
    if m:
        datos["ultimos4"] = int(m.group(1))

    # Dirección de la tienda (línea inmediatamente después de "MERCADONA, S.A. ...")
    m = _RE_TIENDA.search(texto)
    if m:
        datos["tienda"] = m.group(1).strip().replace(",", "")

    # Código postal: primeros 5 dígitos consecutivos en la cabecera del ticket
    # Formato esperado: "12005 Castelló de la Plana"
    m = _RE_CP.search(texto[:200])
    if m:
        datos["codigo_postal"] = m.group(1)

    # ========================
    # BLOQUE DE PRODUCTOS
    # ========================

    lineas = []
    lineas_texto = texto.splitlines()
    dentro_productos = False
    i = 0

    while i < len(lineas_texto):
        linea = lineas_texto[i].strip()

        # Inicio del bloque: encabezado de la tabla de productos
        if "Descripción P. Unit Importe" in linea:
            dentro_productos = True
            i += 1
            continue

        # Fin del bloque al llegar al total
        if "TOTAL (€)" in linea:
            break

        if dentro_productos and linea:

            siguiente = lineas_texto[i + 1].strip() if i + 1 < len(lineas_texto) else ""
            peso_siguiente = _parsear_linea_peso(siguiente)

            m_normal = _RE_PROD_NORMAL.match(linea)

            if m_normal:
                # ------------------------------------------------------------------
                # CASO A: línea con cantidad entera delante
                # ------------------------------------------------------------------
                cantidad = int(m_normal.group(1))
                resto = m_normal.group(2).strip()
                partes = resto.split()

                if cantidad > 1:
                    # Múltiples unidades: "N descripcion precio_unit importe"
                    # Ejemplo: "3 LECHE ENTERA 0,97 2,91"
                    if len(partes) >= 2 and "," in partes[-1]:
                        try:
                            importe     = float(partes[-1].replace(",", "."))
                            precio_unit = float(partes[-2].replace(",", "."))
                            descripcion = " ".join(partes[:-2])
                            lineas.append({
                                "descripcion":     descripcion,
                                "cantidad":        cantidad,
                                "precio_unitario": precio_unit,
                                "importe":         importe,
                                "es_peso":         False
                            })
                        except ValueError:
                            pass

                else:
                    # Cantidad == 1: puede ser normal o a peso
                    if peso_siguiente:
                        # Producto a peso con "1" delante
                        # Ejemplo: "1 PATATA" + "0,802 kg 1,90 €/kg 1,52"
                        kg, precio_kg, importe = peso_siguiente
                        lineas.append({
                            "descripcion":     resto,
                            "cantidad":        kg,
                            "precio_unitario": precio_kg,
                            "importe":         importe,
                            "es_peso":         True
                        })
                        i += 1  # saltar la línea de peso ya procesada

                    elif "," in partes[-1]:
                        # Producto normal cantidad 1: "1 descripcion importe"
                        # Ejemplo: "1 PAPEL HIGIÉNICO 4 CA 3,55"
                        try:
                            importe     = float(partes[-1].replace(",", "."))
                            descripcion = " ".join(partes[:-1])
                            lineas.append({
                                "descripcion":     descripcion,
                                "cantidad":        1,
                                "precio_unitario": importe,
                                "importe":         importe,
                                "es_peso":         False
                            })
                        except ValueError:
                            pass

            else:
                # ------------------------------------------------------------------
                # CASO B: línea sin cantidad entera delante (no empieza por dígito)
                # Puede ser:
                #   - Cabecera de sección (ej: "PESCADO") → siguiente NO es línea de peso
                #   - Producto a peso sin "1" (ej: "GALERAS") → siguiente SÍ es línea de peso
                # La distinción es automática: solo actuamos si hay línea de peso.
                # ------------------------------------------------------------------
                if peso_siguiente:
                    kg, precio_kg, importe = peso_siguiente
                    lineas.append({
                        "descripcion":     linea,
                        "cantidad":        kg,
                        "precio_unitario": precio_kg,
                        "importe":         importe,
                        "es_peso":         True
                    })
                    i += 1  # saltar la línea de peso ya procesada
                # Si no hay línea de peso a continuación → cabecera de sección, se ignora

        i += 1

    datos["lineas"] = lineas
    return datos
