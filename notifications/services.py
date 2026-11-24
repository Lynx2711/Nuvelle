import logging
import time
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from .models import AuditLog, Notification

logger = logging.getLogger(__name__)


def send_email_with_retry(
    subject: str,
    message: str,
    recipient_list: list[str],
    max_retries: int = 3,
    html_message: str | None = None,
) -> bool:
    """
    Sends email with retry mechanism up to max_retries (3 times).
    Uses console backend in dev, and configured SMTP backend in prod.
    """
    if not recipient_list:
        return False

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@nuvelle.edu')

    for attempt in range(1, max_retries + 1):
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=False,
            )
            logger.info("Email '%s' sent successfully to %s on attempt %d", subject, recipient_list, attempt)
            return True
        except Exception as exc:
            logger.warning(
                "Attempt %d/%d to send email '%s' to %s failed: %s",
                attempt,
                max_retries,
                subject,
                recipient_list,
                str(exc),
            )
            if attempt < max_retries:
                time.sleep(0.5 * attempt)  # Brief backoff between retries

    logger.error("Failed to send email '%s' to %s after %d retries.", subject, recipient_list, max_retries)
    return False


def send_notification(
    user: Any,
    message: str,
    link: str = '',
    send_email: bool = False,
    email_subject: str | None = None,
    email_body: str | None = None,
) -> Notification:
    """
    Unified notification service used across all modules.
    Creates an in-app Notification record atomically, and optionally dispatches
    an email for important milestone events with retry support.
    """
    with transaction.atomic():
        notification = Notification.objects.create(
            user=user,
            message=message,
            link=link,
        )

    if send_email and getattr(user, 'email', None):
        subject = email_subject or f"[Nuvelle] {message[:60]}"
        body = email_body or f"Hello {user.get_full_name() or user.email},\n\n{message}\n\nView details: {link or 'https://nuvelle.local'}\n\n-- Nuvelle Team"
        send_email_with_retry(
            subject=subject,
            message=body,
            recipient_list=[user.email],
            max_retries=3,
        )

    return notification


def create_audit_log(
    user: Any | None,
    action: str,
    object_type: str,
    object_id: str | int,
) -> AuditLog:
    """
    Records an entry in the system AuditLog for compliance and traceability.
    """
    return AuditLog.objects.create(
        user=user if getattr(user, 'is_authenticated', False) else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
    )


def mark_notification_as_read(notification_id: int, user: Any) -> bool:
    """Marks a single notification as read for the user."""
    updated = Notification.objects.filter(id=notification_id, user=user).update(is_read=True)
    return updated > 0


def mark_all_notifications_as_read(user: Any) -> int:
    """Marks all unread notifications as read for the user."""
    return Notification.objects.filter(user=user, is_read=False).update(is_read=True)


def get_unread_notifications_count(user: Any) -> int:
    """Returns unread notification count for user."""
    if not user or not user.is_authenticated:
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()
