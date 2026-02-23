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

# OAuth2: ruta al credentials.json descargado de Google Cloud Console.
# Si está definido, se usa OAuth2. Si no, se usa APP_PASSWORD.
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
# Ruta donde se guarda el token OAuth entre sesiones (se renueva automáticamente).
OAUTH_TOKEN = os.getenv("OAUTH_TOKEN", str(Path(__file__).parent / "token.json"))
# ───────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

SCOPES = ["https://mail.google.com/"]


# ── Autenticación ──────────────────────────────────────────────

def _oauth_token() -> str:
    """
    Devuelve un access token OAuth2 válido.
    Si existe token.json y no ha caducado, lo renueva automáticamente.
    Si no existe, abre el navegador para autorizar la app (solo la primera vez).
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise SystemExit(
            "❌ Faltan dependencias para OAuth2.\n"
            "   Ejecuta: pip install google-auth-oauthlib google-auth-httplib2"
        )

    creds = None
    token_path = Path(OAUTH_TOKEN)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("🔄 Renovando token OAuth2...")
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS, SCOPES)
            # Detectar si hay display disponible (escritorio vs SSH)
            import sys
            headless = not sys.stdout.isatty() or os.getenv("DISPLAY") is None and os.getenv("WAYLAND_DISPLAY") is None
            if headless:
                # Modo OOB: Google muestra el código en el navegador en lugar de
                # redirigir a localhost (que no es accesible desde SSH).
                flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
                auth_url, _ = flow.authorization_url(prompt="consent")
                print("\n🌐 Abre esta URL en tu navegador y autoriza el acceso:")
                print("\n" + auth_url + "\n")
                code = input("Pega aquí el código que aparece en el navegador: ").strip()
                flow.fetch_token(code=code)
                creds = flow.credentials
            else:
                log.info("🌐 Abriendo navegador para autorizar acceso a Gmail...")
                creds = flow.run_local_server(port=0)
            log.info("✅ Autorización completada.")

        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds.token


def _conectar_imap() -> imaplib.IMAP4_SSL:
    """
    Abre y devuelve una conexión IMAP autenticada.
    Usa OAuth2 si GOOGLE_CREDENTIALS está configurado, App Password si no.
    """
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)

    if GOOGLE_CREDENTIALS:
        log.info("🔐 Autenticando con OAuth2...")
        token = _oauth_token()
        auth_string = f"user={EMAIL_ADDR}\x01auth=Bearer {token}\x01\x01"
        mail.authenticate("XOAUTH2", lambda x: auth_string)
    else:
        if not APP_PASSWORD:
            raise SystemExit(
                "❌ No hay método de autenticación configurado.\n"
                "   Define APP_PASSWORD o GOOGLE_CREDENTIALS en el .env"
            )
        mail.login(EMAIL_ADDR, APP_PASSWORD)

    return mail


# ── Funciones principales ──────────────────────────────────────

def listar_carpetas():
    """Lista todas las carpetas IMAP disponibles en la cuenta."""
    mail = _conectar_imap()
    _, carpetas = mail.list()
    try:
        mail.logout()
    except Exception:
        pass

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

    mail = _conectar_imap()
    mail.select(f'"{IMAP_FOLDER}"')

    criterios = []
    if todos:
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
        criterios.append(f'FROM "{SENDER}"')
        log.info("Buscando todos los correos del remitente oficial...")
        log.info("  (Para incluir reenviados: retrieve.py --dias N o --todos)")

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

        date_str = msg.get("Date", "")[:16].replace(",", "").replace(" ", "_")

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            decoded, enc = decode_header(filename)[0]
            if isinstance(decoded, bytes):
                filename = decoded.decode(enc or "utf-8")

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
    modo = "OAuth2" if GOOGLE_CREDENTIALS else "App Password"
    parser = argparse.ArgumentParser(
        description=f"Descarga los tickets PDF de Mercadona desde Gmail. (Modo: {modo})",
        epilog="""
Ejemplos:
  python3 retrieve.py            Descarga todos los tickets del remitente oficial
  python3 retrieve.py 30         Enviados por Mercadona en los últimos 30 días
  python3 retrieve.py 7          Enviados por Mercadona en los últimos 7 días
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
