import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from app.database.config import settings

def send_email(to: str, subject: str, html: str, text: str | None = None):
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT or 465
    user = settings.SMTP_USER
    password = settings.SMTP_PASS
    sender = settings.SMTP_FROM or user
    sender_name = settings.SMTP_FROM_NAME or "Healthcare App"
    if not host or not user or not password or not sender:
        raise RuntimeError("SMTP settings not configured")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    try:
        domain = sender.split("@")[1]
        msg["Message-ID"] = make_msgid(domain=domain)
    except Exception:
        msg["Message-ID"] = make_msgid()
    msg["Reply-To"] = sender
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Auto-Response-Suppress"] = "All"
    if text:
        msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    if port == 465:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(user, password)
            server.send_message(msg, sender, [to])
    else:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg, sender, [to])
