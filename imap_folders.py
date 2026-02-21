#!/usr/bin/env python3
"""
imap_folders.py — Lista las carpetas disponibles en tu cuenta de Gmail via IMAP.

Útil para encontrar el valor correcto de IMAP_FOLDER según el idioma de tu cuenta.

Uso:
    python3 imap_folders.py
"""

import imaplib
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

IMAP_HOST    = os.getenv("IMAP_HOST",    "imap.gmail.com")
IMAP_PORT    = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDR   = os.getenv("EMAIL_ADDR")
APP_PASSWORD = os.getenv("APP_PASSWORD")

if not EMAIL_ADDR or not APP_PASSWORD:
    print("❌ EMAIL_ADDR y APP_PASSWORD deben estar definidos en el .env")
    raise SystemExit(1)

print(f"\nConectando a {IMAP_HOST} como {EMAIL_ADDR}...\n")

with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as mail:
    mail.login(EMAIL_ADDR, APP_PASSWORD)
    _, carpetas = mail.list()

print("Carpetas disponibles:\n")
for c in carpetas:
    # Formato: (\HasNoChildren) "/" "Nombre"
    partes = c.decode().split('"')
    nombre = partes[-2] if len(partes) >= 2 else c.decode()
    print(f"  {nombre}")

print()
print('Copia el nombre exacto de la carpeta "Todos" o "All Mail" en IMAP_FOLDER del .env')
