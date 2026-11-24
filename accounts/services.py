import logging
import math

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .tokens import generate_email_verification_token, generate_password_reset_token

logger = logging.getLogger(__name__)
User = get_user_model()


def send_verification_email(user, request=None) -> bool:
    """Generate signed verification token and email link to user."""
    token = generate_email_verification_token(user)
    path = reverse('accounts:verify_email', kwargs={'token': token})

    if request:
        verify_url = request.build_absolute_uri(path)
    else:
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
        verify_url = f"{site_url}{path}"

    subject = "Verify your Nuvelle account"
    message = (
        f"Hello {user.first_name or user.email},\n\n"
        f"Thank you for registering on Nuvelle. Please verify your email by clicking the link below:\n\n"
        f"{verify_url}\n\n"
        f"This link will expire in 24 hours.\n\n"
        f"Best regards,\nThe Nuvelle Team"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.exception("Failed to send verification email to %s: %s", user.email, exc)
        return False


def send_password_reset_email(user, request=None) -> bool:
    """Generate signed reset token and email password reset link to user."""
    token = generate_password_reset_token(user)
    path = reverse('accounts:password_reset_confirm', kwargs={'token': token})

    if request:
        reset_url = request.build_absolute_uri(path)
    else:
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
        reset_url = f"{site_url}{path}"

    subject = "Reset your Nuvelle password"
    message = (
        f"Hello {user.first_name or user.email},\n\n"
        f"We received a request to reset your password for your Nuvelle account.\n"
        f"Click the link below to set a new password:\n\n"
        f"{reset_url}\n\n"
        f"This link will expire in 1 hour.\n"
        f"If you did not request a password reset, you can safely ignore this email.\n\n"
        f"Best regards,\nThe Nuvelle Team"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.exception("Failed to send password reset email to %s: %s", user.email, exc)
        return False


def authenticate_user_with_lockout(request, email, password):
    """
    Authenticate user with 5-attempt limit and 15-minute lockout.
    Returns tuple: (user, status_code, message)
    Status codes:
      - 'SUCCESS': authenticated
      - 'LOCKED': account currently locked
      - 'JUST_LOCKED': locked on this 5th attempt
      - 'FAILED': incorrect credentials (shows attempts remaining)
      - 'NOT_FOUND': no account with this email
    """
    email = email.strip().lower()
    user = User.objects.filter(email=email).first()

    if not user:
        return None, 'NOT_FOUND', 'No account found with this email address.'

    now = timezone.now()

    # Check if currently locked
    if user.locked_until and user.locked_until > now:
        mins_left = math.ceil((user.locked_until - now).total_seconds() / 60)
        return (
            None,
            'LOCKED',
            f'Account is temporarily locked due to 5 failed attempts. Please try again in {mins_left} minute(s).'
        )

    # Attempt standard authentication
    auth_user = authenticate(request, username=email, password=password)

    if auth_user is not None:
        user.reset_failed_logins()
        return auth_user, 'SUCCESS', 'Authentication successful.'
    else:
        user.register_failed_login()
        if user.is_locked:
            return (
                None,
                'JUST_LOCKED',
                'Account locked for 15 minutes due to 5 consecutive failed login attempts.'
            )
        attempts_left = max(0, 5 - user.failed_login_attempts)
        return (
            None,
            'FAILED',
            f'Invalid credentials. {attempts_left} attempt(s) remaining before temporary lockout.'
        )
