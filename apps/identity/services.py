"""
Authentication and Multi-Factor Authentication (MFA) services for GramSetu platform.

Enforces:
- Login throttling / rate limiting by client IP and email.
- Multi-Factor Authentication (MFA) via email OTP using django-otp.
- Single-use, short-lived verification codes with attempt limit and cooldown.
- Emergency recovery codes (StaticDevice / StaticToken).
- Production fail-closed policy when email delivery is not configured.
- Safe audit logging without logging credentials, OTP tokens, or secrets.
"""

import logging
from typing import Optional, Tuple, List
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django_otp.plugins.otp_email.models import EmailDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
import secrets

logger = logging.getLogger('gramsetu.auth')


def get_client_ip(request) -> str:
    """
    Extracts client IP address safely from request headers or REMOTE_ADDR.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip or '127.0.0.1'


def mask_email(email: str) -> str:
    """
    Masks email address for display in API responses without revealing full address.
    Example: 'vishal.patil@example.com' -> 'v***l@example.com'
    """
    if not email or '@' not in email:
        return '***'
    user_part, domain_part = email.split('@', 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + '***'
    else:
        masked_user = user_part[0] + '***' + user_part[-1]
    return f"{masked_user}@{domain_part}"


def is_email_service_configured() -> bool:
    """
    Evaluates whether transactional email delivery is configured.
    In production (DEBUG=False, IS_TESTING=False), requires non-empty EMAIL_HOST,
    EMAIL_HOST_USER, and EMAIL_HOST_PASSWORD, and non-console/locmem backend.
    """
    if settings.DEBUG or getattr(settings, 'IS_TESTING', False):
        return True

    backend = getattr(settings, 'EMAIL_BACKEND', '')
    if any(k in backend.lower() for k in ('console', 'locmem', 'dummy', 'filebased')):
        return False

    host = getattr(settings, 'EMAIL_HOST', '')
    user = getattr(settings, 'EMAIL_HOST_USER', '')
    pwd = getattr(settings, 'EMAIL_HOST_PASSWORD', '')
    return bool(host and user and pwd)


class LoginRateLimiter:
    """
    Throttles failed authentication attempts per (client_ip, email) pair.
    Prevents brute-force credential stuffing without enabling trivial DoS
    against entire accounts from arbitrary external IP addresses.
    """
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_DURATION_SECONDS = 900  # 15 minutes

    @classmethod
    def get_cache_key(cls, ip: str, email: str) -> str:
        norm_email = email.strip().lower()
        return f"gramsetu:auth:login_fails:{ip}:{norm_email}"

    @classmethod
    def is_locked_out(cls, ip: str, email: str) -> bool:
        key = cls.get_cache_key(ip, email)
        attempts = cache.get(key, 0)
        return attempts >= cls.MAX_FAILED_ATTEMPTS

    @classmethod
    def record_failure(cls, ip: str, email: str) -> int:
        key = cls.get_cache_key(ip, email)
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, cls.LOCKOUT_DURATION_SECONDS)
        logger.warning(
            "Failed login attempt %d/%d for email '%s' from IP %s",
            attempts, cls.MAX_FAILED_ATTEMPTS, mask_email(email), ip,
        )
        return attempts

    @classmethod
    def reset(cls, ip: str, email: str):
        key = cls.get_cache_key(ip, email)
        cache.delete(key)


def get_or_create_email_device(user) -> EmailDevice:
    """
    Retrieves or initializes the default EmailDevice for an administrative user.
    """
    device, created = EmailDevice.objects.get_or_create(
        user=user,
        name='default',
        defaults={'confirmed': True, 'email': user.email},
    )
    if not device.confirmed or device.email != user.email:
        device.confirmed = True
        device.email = user.email
        device.save(update_fields=['confirmed', 'email'])
    return device


def get_or_create_static_device(user) -> StaticDevice:
    """
    Retrieves or initializes the default StaticDevice (backup recovery codes) for an administrative user.
    """
    device, created = StaticDevice.objects.get_or_create(
        user=user,
        name='recovery',
        defaults={'confirmed': True},
    )
    if not device.confirmed:
        device.confirmed = True
        device.save(update_fields=['confirmed'])
    return device


def generate_recovery_codes(user, count: int = 5) -> List[str]:
    """
    Generates a fresh set of single-use recovery codes for the user's StaticDevice.
    Previous unused recovery codes for this device are purged.
    Returns the list of raw plaintext tokens to be displayed once to the user.
    """
    device = get_or_create_static_device(user)
    # Invalidate previous tokens
    device.token_set.all().delete()

    raw_codes = []
    for _ in range(count):
        # 10-character cryptographically random code
        code = secrets.token_hex(5).upper()  # 10 chars, e.g. 'A1B2C3D4E5'
        StaticToken.objects.create(device=device, token=code)
        raw_codes.append(code)

    logger.info("Generated %d new emergency recovery codes for user %s", count, user.id)
    return raw_codes
