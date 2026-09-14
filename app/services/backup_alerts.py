"""Backup failure/missed-cycle notifications through configured providers."""
from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict, token: str = "") -> None:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=15) as response:
        if not 200 <= getattr(response, "status", 200) < 300:
            raise RuntimeError(f"notification_http_{response.status}")


def send_backup_alert(subject: str, message: str) -> dict[str, str]:
    """Send configured email/WhatsApp alerts independently; one provider cannot block another."""
    sent: list[str] = []
    failures: list[str] = []
    if settings.backup_alert_email_to.strip() and settings.email_api_url.strip() and settings.email_api_key.strip():
        try:
            _post_json(settings.email_api_url, {"to": settings.backup_alert_email_to.strip(), "subject": subject, "body": message, "from": settings.email_from or "MetroCRM"}, settings.email_api_key)
            sent.append("email")
        except (HTTPError, URLError, RuntimeError, OSError) as exc:
            failures.append(f"email:{exc}")
            logger.exception("MetroCRM backup email alert failed")
    if settings.backup_alert_whatsapp_to.strip() and settings.whatsapp_api_url.strip() and settings.whatsapp_access_token.strip():
        try:
            payload = {"to": settings.backup_alert_whatsapp_to.strip(), "message": f"{subject}\n{message}"}
            if settings.whatsapp_phone_number_id.strip():
                payload["phone_number_id"] = settings.whatsapp_phone_number_id.strip()
            _post_json(settings.whatsapp_api_url, payload, settings.whatsapp_access_token)
            sent.append("whatsapp")
        except (HTTPError, URLError, RuntimeError, OSError) as exc:
            failures.append(f"whatsapp:{exc}")
            logger.exception("MetroCRM backup WhatsApp alert failed")
    if settings.backup_alert_webhook_url.strip():
        try:
            _post_json(settings.backup_alert_webhook_url, {"event": "metrocrm_backup_alert", "subject": subject, "message": message, "severity": "critical"}, settings.backup_alert_webhook_token)
            sent.append("webhook")
        except (HTTPError, URLError, RuntimeError, OSError) as exc:
            failures.append(f"webhook:{exc}")
            logger.exception("MetroCRM backup webhook alert failed")
    return {"sent": ",".join(sent) or "none", "failed": ",".join(failures) or "none"}


def notify_backup_failure(result: dict[str, object] | None, reason: str = "backup_failed") -> dict[str, str]:
    result = result or {}
    status = str(result.get("status", "failed"))
    failed = result.get("failed_destinations") or []
    subject = f"MetroCRM BACKUP ALERT: {status.upper()}"
    message = f"Reason: {reason}\nStatus: {status}\nFailed destinations: {', '.join(map(str, failed)) or 'none reported'}\nTime: {result.get('date', 'unknown')} {result.get('label', '')}\nAction: automatic retry is enabled."
    return send_backup_alert(subject, message)
