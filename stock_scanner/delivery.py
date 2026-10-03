"""Mail preparation and TLS SMTP delivery. Configuration stays outside public Git."""
import hashlib
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr

from .storage import atomic_json, read_json


class DeliveryError(RuntimeError):
    pass


def address(name):
    value = os.environ.get(name, "")
    if any(x in value for x in ("\n", "\r")) or not value or parseaddr(value)[1] != value or "@" not in value:
        raise DeliveryError(f"Missing or invalid private environment variable: {name}")
    return value


def prepare(report_path, state, send=False):
    report_path = report_path.resolve()
    if not report_path.is_relative_to(state.resolve()) or report_path.name != "report.md":
        raise DeliveryError("Only a generated private report.md may be delivered")
    companion = report_path.with_name("report.json")
    report = read_json(companion)
    message = EmailMessage()
    message["Subject"] = f"Stock research {'weekly' if 'signals' in report else 'daily'} — {report['data_date']} — {report['status']}"
    message["To"] = address("SCANNER_REPORT_TO")
    message["From"] = address("SMTP_FROM")
    message.set_content(report_path.read_text(encoding="utf-8"), charset="utf-8")
    # Do not attach raw data, source archives, or private authentication metadata.
    digest = hashlib.sha256((str(report_path)+report_path.read_text()).encode()).hexdigest()
    outgoing = state / "outbox"
    outgoing.mkdir(parents=True, exist_ok=True, mode=0o700)
    eml = outgoing / (digest + ".eml")
    fd = os.open(eml, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(message.as_bytes())
    if not send:
        return {"status": "draft", "message_path": str(eml), "recipient_configured": True}
    if os.environ.get("SCANNER_EMAIL_ENABLED") != "1":
        raise DeliveryError("Live delivery is disabled; set SCANNER_EMAIL_ENABLED=1 in the durable scheduler after configuring mail")
    host, user, password = [os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")]
    if not all((host, user, password)):
        raise DeliveryError("Configure SMTP_HOST, SMTP_USER and SMTP_PASSWORD securely in the durable scheduler")
    try:
        port = int(os.environ.get("SMTP_PORT", "465"))
    except ValueError:
        raise DeliveryError("Invalid SMTP_PORT") from None
    if port not in (465, 587):
        raise DeliveryError("Only verified TLS SMTP on port 465 or 587 is supported")
    marker = outgoing / (digest + ".sent.json")
    if marker.exists():
        return {"status": "already_sent", "message_path": str(eml)}
    context = ssl.create_default_context()
    try:
        transport = smtplib.SMTP_SSL(host, port, timeout=30, context=context) if port == 465 else smtplib.SMTP(host, port, timeout=30)
        with transport as smtp:
            if port == 587:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError):
        # Server replies can contain personal addresses or authentication details.
        raise DeliveryError("SMTP delivery failed; no automatic retry and no sensitive server reply logged") from None
    atomic_json(marker, {"sent": True, "report_path": str(report_path)})
    return {"status": "sent", "message_path": str(eml)}
