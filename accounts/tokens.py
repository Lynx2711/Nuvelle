import hashlib

from django.contrib.auth import get_user_model
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

User = get_user_model()

EMAIL_VERIFICATION_SALT = 'nuvelle-email-verification-v1'
PASSWORD_RESET_SALT = 'nuvelle-password-reset-v1'


def _get_password_hash_digest(user) -> str:
    return hashlib.sha256(user.password.encode('utf-8')).hexdigest()[:16]


def generate_email_verification_token(user) -> str:
    """Generate a cryptographic signed token for email verification (valid 24h)."""
    signer = TimestampSigner(salt=EMAIL_VERIFICATION_SALT)
    return signer.sign(str(user.pk))


def verify_email_verification_token(token: str, max_age: int = 86400):
    """Verify email verification token. Returns user if valid, else None."""
    signer = TimestampSigner(salt=EMAIL_VERIFICATION_SALT)
    try:
        user_id = signer.unsign(token, max_age=max_age)
        return User.objects.get(pk=user_id)
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        return None


def generate_password_reset_token(user) -> str:
    """Generate a signed token for password reset (valid 1h). Embeds password hash digest."""
    signer = TimestampSigner(salt=PASSWORD_RESET_SALT)
    digest = _get_password_hash_digest(user)
    payload = f"{user.pk}:{digest}"
    return signer.sign(payload)


def verify_password_reset_token(token: str, max_age: int = 3600):
    """Verify password reset token. Invalids when password has changed or token expired."""
    signer = TimestampSigner(salt=PASSWORD_RESET_SALT)
    try:
        payload = signer.unsign(token, max_age=max_age)
        parts = payload.split(':', 1)
        if len(parts) != 2:
            return None
        user_id, digest = parts
        user = User.objects.get(pk=user_id)
        if _get_password_hash_digest(user) != digest:
            return None
        return user
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        return None
