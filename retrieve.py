#!/usr/bin/env python3

# Este retrieve recupera en función del nombre del adjunto
# y no en función del remitente. 


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
SAVE_DIR     = Path(os.getenv("SAVE_DIR"))
# Carpeta IMAP donde buscar — varía según idioma de Gmail:
#   ES: [Google Mail]/Todos   EN: [Gmail]/All Mail
IMAP_FOLDER  = os.getenv("IMAP_FOLDER", "[Google Mail]/Todos")
# ───────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def clean_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._- ").strip()


def download_attachments(dias: int | None = None):
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as mail:
        mail.login(EMAIL_ADDR, APP_PASSWORD)
        mail.select(f'"{IMAP_FOLDER}"')

        # Construir criterio de búsqueda IMAP.
        # Buscamos por remitente oficial Y también sin filtro de remitente
        # para capturar tickets reenviados por otras personas.
        # En ambos casos validamos que el adjunto tenga nombre de ticket Mercadona.
        criterios = []
        if dias is not None:
            desde = (datetime.now() - timedelta(days=dias)).strftime("%d-%b-%Y")
            criterios.append(f'FROM "{SENDER}" SINCE {desde}')
            criterios.append(f'SINCE {desde}')
            log.info(f"Buscando correos de los últimos {dias} días (desde {desde})...")
        else:
            criterios.append(f'FROM "{SENDER}"')
            criterios.append('ALL')
            log.info("Buscando todos los correos...")

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
            _, data = mail.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Descarga los tickets PDF de Mercadona desde Gmail.",
        epilog="""
Ejemplos:
  python3 retrieve.py            Descarga todos los tickets del remitente
  python3 retrieve.py 30         Descarga solo los de los últimos 30 días
  python3 retrieve.py 7          Descarga solo los de la última semana
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "dias", nargs="?", type=int, default=None,
        help="Número de días hacia atrás a buscar (por defecto: todos)"
    )
    args = parser.parse_args()
    download_attachments(dias=args.dias)
