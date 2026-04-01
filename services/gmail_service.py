import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import html
import re
import sys
import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    print("Este script requiere Python 3.11+ para usar tomllib.")
    sys.exit(1)

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
FROM_FILTER = "no-reply@plaud.ai"
SECRETS_FILE = "secrets.toml"


def load_secrets(path: str = SECRETS_FILE) -> tuple[str, str]:
    """Carga las credenciales de Gmail desde env o secrets.toml"""
    # Primero intentar desde variables de entorno (para producción)
    user_email = os.environ.get("GMAIL_USER", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")

    if user_email and app_password:
        if len(app_password) != 16:
            raise ValueError("La GMAIL_APP_PASSWORD debe tener 16 caracteres sin espacios.")
        return user_email, app_password

    # Fallback a secrets.toml (para desarrollo local)
    secrets_path = Path(path)

    if not secrets_path.exists():
        raise FileNotFoundError(
            f"No existe el archivo {path}. Créalo en la raíz del proyecto o configura GMAIL_USER y GMAIL_APP_PASSWORD."
        )

    with open(secrets_path, "rb") as f:
        data = tomllib.load(f)

    user_email = data.get("email", {}).get("user", "").strip()
    app_password = data.get("gmail", {}).get("app_password", "").strip().replace(" ", "")

    if not user_email:
        raise ValueError("Falta GMAIL_USER en env o [email].user en secrets.toml")

    if not app_password:
        raise ValueError("Falta GMAIL_APP_PASSWORD en env o [gmail].app_password en secrets.toml")

    if len(app_password) != 16:
        raise ValueError(
            "La App Password debe tener 16 caracteres sin espacios. "
            "Revísala en secrets.toml o GMAIL_APP_PASSWORD."
        )

    return user_email, app_password


def decode_mime_words(value: str) -> str:
    """Decodifica palabras MIME en el encabezado del email"""
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for text, enc in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(enc or "utf-8", errors="ignore"))
        else:
            decoded.append(text)
    return "".join(decoded)


def html_to_text(html_content: str) -> str:
    """Convierte HTML a texto plano"""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_content)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<.*?>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_body(msg) -> str:
    """Extrae el cuerpo del email en texto plano"""
    if msg.is_multipart():
        plain_parts = []
        html_parts = []

        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in content_disposition.lower():
                continue

            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="ignore")
            except Exception:
                continue

            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)

        if plain_parts:
            return "\n".join(plain_parts).strip()

        if html_parts:
            return html_to_text("\n".join(html_parts)).strip()

        return ""

    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""

    charset = msg.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="ignore")

    if msg.get_content_type() == "text/html":
        return html_to_text(text)

    return text.strip()


def extract_attachments(msg) -> list:
    """Extrae los nombres de los archivos adjuntos del email"""
    attachments = []
    
    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if "attachment" in content_disposition.lower():
                filename = part.get_filename()
                if filename:
                    attachments.append(filename)
    
    return attachments


def fetch_recent_plaud_emails(user_email: str, app_password: str, limit: int = 10) -> list:
    """Obtiene los correos recientes del remitente PLAUD"""
    emails_data = []
    
    print(f"Conectando a {IMAP_SERVER}:{IMAP_PORT} ...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)

    print("Intentando login IMAP ...")
    mail.login(user_email, app_password)

    status, _ = mail.select("INBOX")
    if status != "OK":
        mail.logout()
        raise RuntimeError("No se pudo abrir INBOX.")

    status, data = mail.search(None, f'(FROM "{FROM_FILTER}")')
    if status != "OK":
        mail.logout()
        raise RuntimeError("No se pudo ejecutar la busqueda IMAP.")

    message_ids = data[0].split()
    if not message_ids:
        print("No se encontraron correos de PLAUD.")
        mail.logout()
        return []

    print(f"Se encontraron {len(message_ids)} correos de PLAUD.\n")

    recent_ids = list(reversed(message_ids[-limit:]))

    for msg_id in recent_ids:
        status, msg_data = mail.fetch(msg_id, "(RFC822)")
        if status != "OK":
            print(f"No se pudo leer el mensaje {msg_id.decode()}.")
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_mime_words(msg.get("Subject", ""))
        sender = decode_mime_words(msg.get("From", ""))
        date_raw = msg.get("Date", "")

        try:
            date_parsed = parsedate_to_datetime(date_raw).isoformat()
        except Exception:
            date_parsed = date_raw

        body = extract_body(msg)
        attachments = extract_attachments(msg)

        email_data = {
            "id": msg_id.decode(),
            "from": sender,
            "date": date_parsed,
            "subject": subject,
            "body": body[:4000] if body else "[sin cuerpo legible]",
            "attachments": attachments
        }
        
        emails_data.append(email_data)

    mail.logout()
    return emails_data


def get_email_by_id(user_email: str, app_password: str, msg_id: str) -> dict:
    """Obtiene un email específico por ID"""
    print(f"Conectando a {IMAP_SERVER}:{IMAP_PORT} ...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)

    print("Intentando login IMAP ...")
    mail.login(user_email, app_password)

    status, _ = mail.select("INBOX")
    if status != "OK":
        mail.logout()
        raise RuntimeError("No se pudo abrir INBOX.")

    status, msg_data = mail.fetch(msg_id.encode(), "(RFC822)")
    if status != "OK":
        mail.logout()
        raise RuntimeError(f"No se pudo leer el mensaje {msg_id}.")

    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    subject = decode_mime_words(msg.get("Subject", ""))
    sender = decode_mime_words(msg.get("From", ""))
    date_raw = msg.get("Date", "")

    try:
        date_parsed = parsedate_to_datetime(date_raw).isoformat()
    except Exception:
        date_parsed = date_raw

    body = extract_body(msg)
    attachments = extract_attachments(msg)

    email_data = {
        "id": msg_id,
        "from": sender,
        "date": date_parsed,
        "subject": subject,
        "body": body,
        "attachments": attachments
    }

    mail.logout()
    return email_data
