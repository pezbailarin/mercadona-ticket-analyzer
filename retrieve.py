#!/usr/bin/env python3
import imaplib
import re
import email
import os
import argparse
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Configuración ──────────────────────────────────────────────
IMAP_HOST    = os.getenv("IMAP_HOST",    "imap.gmail.com")
IMAP_PORT    = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDR   = os.getenv("EMAIL_ADDR")
APP_PASSWORD = os.getenv("APP_PASSWORD")
SENDER       = "ticket_digital@mail.mercadona.com"
SAVE_DIR     = Path(os.getenv("SAVE_DIR")).expanduser()
# Carpeta IMAP donde buscar — varía según idioma de Gmail:
#   ES: [Google Mail]/Todos   EN: [Gmail]/All Mail
IMAP_FOLDER  = os.getenv("IMAP_FOLDER", "[Google Mail]/Todos")
# ───────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def listar_carpetas():
    """Lista todas las carpetas IMAP disponibles en la cuenta."""
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as mail:
        mail.login(EMAIL_ADDR, APP_PASSWORD)
        _, carpetas = mail.list()
    cuenta = EMAIL_ADDR or "la cuenta"
    print("\nCarpetas disponibles en " + cuenta + ":\n")
    for item in carpetas:
        partes = item.decode().split('"')
        nombre = partes[-2] if len(partes) >= 2 else item.decode()
        print("  " + nombre)
    print()
    print("Copia el nombre exacto en IMAP_FOLDER del .env")


def clean_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._- ").strip()


def download_attachments(dias: int | None = None, todos: bool = False):
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as mail:
        mail.login(EMAIL_ADDR, APP_PASSWORD)
        mail.select(f'"{IMAP_FOLDER}"')

        # Construir criterio de búsqueda IMAP.
        # Buscamos por remitente oficial Y también sin filtro de remitente
        # para capturar tickets reenviados por otras personas.
        # En ambos casos validamos que el adjunto tenga nombre de ticket Mercadona.
        criterios = []
        if todos:
            # Busca en toda la bandeja sin filtro de remitente.
            # Puede tardar si hay muchos correos.
            if dias is not None:
                desde = (datetime.now() - timedelta(days=dias)).strftime("%d-%b-%Y")
                criterios.append(f'SINCE {desde}')
                log.info(f"Buscando en toda la bandeja los últimos {dias} días (desde {desde})...")
            else:
                criterios.append('ALL')
                log.info("Buscando en toda la bandeja sin filtro — puede tardar...")
        elif dias is not None:
            desde = (datetime.now() - timedelta(days=dias)).strftime("%d-%b-%Y")
            criterios.append(f'FROM "{SENDER}" SINCE {desde}')
            criterios.append(f'SINCE {desde} NOT FROM "{SENDER}"')
            log.info(f"Buscando correos de los últimos {dias} días (desde {desde})...")
        else:
            # Sin rango de fechas: solo remitente oficial.
            # Para incluir reenviados usa --dias N o --todos.
            criterios.append(f'FROM "{SENDER}"')
            log.info("Buscando todos los correos del remitente oficial...")
            log.info("  (Para incluir reenviados: retrieve.py --dias N o --todos)")

        # Recoger IDs únicos de ambas búsquedas
        ids_vistos = set()
        todos_ids  = []
        for criterio in criterios:
            _, msg_ids = mail.search(None, criterio)
            for mid in msg_ids[0].split():
                if mid not in ids_vistos:
                    ids_vistos.add(mid)
                    todos_ids.append(mid)

        log.info(f"Correos a revisar: {len(todos_ids)}")
        guardados = 0

        for msg_id in todos_ids:
            try:
                _, data = mail.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
            except Exception as e:
                log.warning(f"  No se pudo descargar el mensaje {msg_id.decode()}: {e} — saltando")
                continue

            # Fecha para prefijo en nombre de archivo
            date_str = msg.get("Date", "")[:16].replace(",", "").replace(" ", "_")

            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None:
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                # Decodificar nombre si está codificado
                decoded, enc = decode_header(filename)[0]
                if isinstance(decoded, bytes):
                    filename = decoded.decode(enc or "utf-8")

                # Validar que el adjunto parece un ticket de Mercadona
                # Formato esperado: "20260221 Mercadona 42,26 €.pdf"
                if not re.search(r'\d{8}.*Mercadona.*\.pdf', filename, re.IGNORECASE):
                    continue

                filename = f"{date_str}_{clean_filename(filename)}"
                filepath = SAVE_DIR / filename

                if filepath.exists():
                    log.info(f"  Ya existe, saltando: {filename}")
                    continue

                filepath.write_bytes(part.get_payload(decode=True))
                log.info(f"  Guardado: {filename}")
                guardados += 1

        log.info(f"PDFs nuevos descargados: {guardados}")
        try:
            mail.logout()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Descarga los tickets PDF de Mercadona desde Gmail.",
        epilog="""
Ejemplos:
  python3 retrieve.py            Descarga todos los tickets del remitente oficial
  python3 retrieve.py 30         Descarga los del remitente + reenviados de los últimos 30 días
  python3 retrieve.py 7          Descarga los del remitente + reenviados de la última semana
  python3 retrieve.py --todos    Busca en toda la bandeja (sin filtro de remitente)
  python3 retrieve.py --todos 7  Toda la bandeja pero solo los últimos 7 días
  python3 retrieve.py --carpetas Lista las carpetas IMAP disponibles
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "dias", nargs="?", type=int, default=None,
        help="Número de días hacia atrás a buscar (por defecto: todos)"
    )
    parser.add_argument(
        "--todos", action="store_true",
        help="Busca en toda la bandeja sin filtrar por remitente (incluye reenviados)"
    )
    parser.add_argument(
        "--carpetas", action="store_true",
        help="Lista las carpetas IMAP disponibles y sale"
    )
    args = parser.parse_args()
    if args.carpetas:
        listar_carpetas()
    else:
        download_attachments(dias=args.dias, todos=args.todos)
