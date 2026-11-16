"""
Secure Authentication and Multi-Factor Authentication (MFA) API views for GramSetu CMS.

Implements:
- POST /api/auth/login/
- POST /api/auth/mfa/verify/
- POST /api/auth/mfa/resend/
- POST /api/auth/mfa/recovery/
- GET  /api/auth/mfa/status/
- POST /api/auth/mfa/recovery-codes/generate/
- GET  /api/auth/me/
- POST /api/auth/logout/
- GET  /api/auth/csrf/

Adheres strictly to security specifications:
- HttpOnly session cookies with 30-minute inactivity timeout.
- Deliberate CORS and trusted origin verification.
- Mandatory MFA for all administrative roles (Super Administrator and Operator).
- Single-use, short-lived verification codes with attempt limit and cooldown.
- Production fail-closed policy when email delivery is not configured.
- Zero logging of credentials, OTP tokens, or secrets.
"""

import json
import logging
from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
import django_otp

from apps.identity.models import User, ROLE_SUPER_ADMIN, ROLE_OPERATOR
from apps.identity.permissions import (
    is_super_admin,
    is_operator,
    user_has_verified_mfa,
    require_cms_auth,
)
from apps.identity.services import (
    get_client_ip,
    mask_email,
    is_email_service_configured,
    LoginRateLimiter,
    get_or_create_email_device,
    get_or_create_static_device,
    generate_recovery_codes,
)

logger = logging.getLogger('gramsetu.auth')


def _parse_json_body(request):
    """
    Safely parses incoming JSON request body.
    Returns (data, error_response).
    """
    try:
        if not request.body:
            return {}, None
        data = json.loads(request.body.decode('utf-8'))
        if not isinstance(data, dict):
            return None, JsonResponse({'detail': 'Invalid JSON structure; expected an object.'}, status=400)
        return data, None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({'detail': 'Malformed JSON payload.'}, status=400)


@ensure_csrf_cookie
@require_POST
def login_view(request):
    """
    Primary administrative login endpoint.
    Validates email/password credentials, checks role, and initiates mandatory MFA challenge.
    Does NOT establish a privileged session until MFA is verified.
    """
    client_ip = get_client_ip(request)
    data, err = _parse_json_body(request)
    if err:
        return err

    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return JsonResponse({'detail': 'Both email and password are required.'}, status=400)

    # Standardize common development aliases to canonical testing accounts
    EMAIL_ALIASES = {
        'admin@gramsetu.gov.in': 'local.admin@gramsetu.gov.in',
        'gram.sevak@gramsetu.gov.in': 'local.admin@gramsetu.gov.in',
        'gramsevak@gramsetu.gov.in': 'local.admin@gramsetu.gov.in',
        'superadmin@gramsetu.gov.in': 'local.admin@gramsetu.gov.in',
        'operator@gramsetu.gov.in': 'local.operator@gramsetu.gov.in',
    }
    canonical_email = EMAIL_ALIASES.get(email, email)

    # Brute-force throttling check
    if LoginRateLimiter.is_locked_out(client_ip, canonical_email):
        logger.warning("Throttled login attempt for '%s' from IP %s", mask_email(canonical_email), client_ip)
        resp = JsonResponse(
            {'detail': 'Too many failed login attempts. Please try again in 15 minutes.'},
            status=429,
        )
        resp['Retry-After'] = str(LoginRateLimiter.LOCKOUT_DURATION_SECONDS)
        return resp

    # Authenticate credentials
    user = authenticate(request, email=canonical_email, password=password)

    if user is None:
        try:
            possible_user = User.objects.get(email=canonical_email)
            if not possible_user.is_active and possible_user.check_password(password):
                logger.warning("Login rejected for inactive account '%s' from IP %s", mask_email(canonical_email), client_ip)
                return JsonResponse({'detail': 'Account is inactive or disabled.'}, status=401)
        except User.DoesNotExist:
            pass
        LoginRateLimiter.record_failure(client_ip, canonical_email)
        return JsonResponse({'detail': 'Invalid email or password.'}, status=401)

    if not user.is_active:
        logger.warning("Login rejected for inactive account '%s' from IP %s", mask_email(email), client_ip)
        return JsonResponse({'detail': 'Account is inactive or disabled.'}, status=401)

    # Role enforcement: Only authorized administrative roles can access CMS
    if not (is_super_admin(user) or is_operator(user)):
        logger.warning("Login rejected for non-administrative user %s from IP %s", user.id, client_ip)
        return JsonResponse({'detail': 'Access denied: Administrative authority required.'}, status=403)

    # Production Fail-Closed Rule for Email Delivery
    if not is_email_service_configured():
        logger.critical(
            "FAIL-CLOSED: Transactional email delivery service is unconfigured in production. "
            "Refusing administrative login for %s.",
            user.id,
        )
        return JsonResponse(
            {'detail': 'Administrative authentication is unavailable: Email delivery gateway is not configured.'},
            status=503,
        )

    # Reset login failure counter on valid password
    LoginRateLimiter.reset(client_ip, email)

    # Retrieve or create Email OTP device
    device = get_or_create_email_device(user)

    # Generate and deliver single-use email OTP challenge
    try:
        device.generate_challenge()
    except Exception as exc:
        logger.error("Failed to generate/deliver email OTP challenge for user %s: %s", user.id, exc)
        return JsonResponse({'detail': 'Failed to deliver verification code. Please try again.'}, status=500)

    # Establish temporary pre-auth session state
    request.session.flush()
    request.session['pre_auth_user_id'] = str(user.id)
    request.session['pre_auth_timestamp'] = timezone.now().timestamp()
    request.session['pre_auth_attempts'] = 0

    logger.info("Initiated MFA challenge for administrative user %s from IP %s", user.id, client_ip)

    return JsonResponse({
        'mfa_required': True,
        'email_masked': mask_email(user.email),
        'message': 'A 6-digit verification code has been sent to your registered email address.',
        'expires_in_seconds': getattr(settings, 'OTP_EMAIL_TOKEN_VALIDITY', 300),
    })


@ensure_csrf_cookie
@require_POST
def mfa_verify_view(request):
    """
    Verifies the email OTP code and establishes an authenticated, MFA-verified session.
    """
    client_ip = get_client_ip(request)
    data, err = _parse_json_body(request)
    if err:
        return err

    user_id = request.session.get('pre_auth_user_id')
    pre_auth_ts = request.session.get('pre_auth_timestamp')

    if not user_id or not pre_auth_ts:
        return JsonResponse({'detail': 'No pending MFA session. Please log in first.'}, status=400)

    # Session timeout check (max 10 minutes from password verification)
    if timezone.now().timestamp() - pre_auth_ts > 600:
        request.session.flush()
        return JsonResponse({'detail': 'MFA session has expired. Please log in again.'}, status=400)

    # Enforce attempt limits (max 5 incorrect code attempts per challenge)
    attempts = request.session.get('pre_auth_attempts', 0) + 1
    request.session['pre_auth_attempts'] = attempts

    if attempts > 5:
        request.session.flush()
        logger.warning("Excessive MFA attempts for user %s from IP %s. Session invalidated.", user_id, client_ip)
        return JsonResponse({'detail': 'Maximum verification attempts exceeded. Please log in again.'}, status=429)

    code = (data.get('code') or '').strip()
    if not code:
        return JsonResponse({'detail': 'Verification code is required.'}, status=400)

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except (User.DoesNotExist, ValidationError):
        request.session.flush()
        return JsonResponse({'detail': 'User account not found.'}, status=400)

    device = get_or_create_email_device(user)

    # Check device-level throttling
    verify_allowed, _ = device.verify_is_allowed()
    if not verify_allowed:
        return JsonResponse({'detail': 'Too many failed verification attempts. Please request a new code.'}, status=429)

    # Verify single-use token
    if not device.verify_token(code):
        logger.warning("Invalid OTP attempt (%d/5) for user %s from IP %s", attempts, user.id, client_ip)
        return JsonResponse({'detail': 'Invalid or expired verification code.'}, status=400)

    # Successful Verification: Establish full session
    request.session.flush()
    auth_login(request, user)
    django_otp.login(request, device)
    request.session['mfa_verified'] = True
    request.session['mfa_verified_at'] = timezone.now().isoformat()
    request.session.cycle_key()

    logger.info("MFA verification successful for user %s (%s) from IP %s", user.id, user.email, client_ip)

    role_name = getattr(getattr(user, 'role_assignment', None), 'role', None)
    role_display = getattr(getattr(user, 'role_assignment', None), 'get_role_display', lambda: 'Staff')()

    return JsonResponse({
        'authenticated': True,
        'user': {
            'id': str(user.id),
            'email': user.email,
            'full_name': user.full_name,
            'role': role_name,
            'role_display': role_display,
            'is_super_admin': is_super_admin(user),
            'is_operator': is_operator(user),
        },
    })


@ensure_csrf_cookie
@require_POST
def mfa_resend_view(request):
    """
    Resends an active email verification code subject to cooldown constraints.
    """
    client_ip = get_client_ip(request)
    user_id = request.session.get('pre_auth_user_id')
    if not user_id:
        return JsonResponse({'detail': 'No pending MFA session. Please log in first.'}, status=400)

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except (User.DoesNotExist, ValidationError):
        request.session.flush()
        return JsonResponse({'detail': 'User account not found.'}, status=400)

    device = get_or_create_email_device(user)

    # Enforce cooldown check (e.g. 60 seconds between resends)
    generate_allowed, _ = device.generate_is_allowed()
    if not generate_allowed:
        return JsonResponse({'detail': 'Please wait before requesting another verification code.'}, status=429)

    try:
        device.generate_challenge()
    except Exception as exc:
        logger.error("Failed to resend email OTP challenge for user %s: %s", user.id, exc)
        return JsonResponse({'detail': 'Failed to deliver verification code. Please try again.'}, status=500)

    # Reset attempts for new challenge
    request.session['pre_auth_attempts'] = 0
    request.session['pre_auth_timestamp'] = timezone.now().timestamp()

    logger.info("Resent MFA challenge for user %s from IP %s", user.id, client_ip)

    return JsonResponse({
        'message': 'A new verification code has been sent to your registered email address.',
        'expires_in_seconds': getattr(settings, 'OTP_EMAIL_TOKEN_VALIDITY', 300),
    })


@ensure_csrf_cookie
@require_POST
def mfa_recovery_view(request):
    """
    Emergency account recovery using a single-use backup recovery code (StaticDevice).
    """
    client_ip = get_client_ip(request)
    data, err = _parse_json_body(request)
    if err:
        return err

    user_id = request.session.get('pre_auth_user_id')
    if not user_id:
        return JsonResponse({'detail': 'No pending MFA session. Please log in first.'}, status=400)

    recovery_code = (data.get('recovery_code') or '').strip().upper()
    if not recovery_code:
        return JsonResponse({'detail': 'Recovery code is required.'}, status=400)

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except (User.DoesNotExist, ValidationError):
        request.session.flush()
        return JsonResponse({'detail': 'User account not found.'}, status=400)

    device = get_or_create_static_device(user)

    # Verify recovery code
    if not device.verify_token(recovery_code):
        logger.warning("Invalid recovery code attempt for user %s from IP %s", user.id, client_ip)
        return JsonResponse({'detail': 'Invalid or previously consumed recovery code.'}, status=400)

    # Establish full session via recovery
    request.session.flush()
    auth_login(request, user)
    django_otp.login(request, device)
    request.session['mfa_verified'] = True
    request.session['mfa_recovery_used'] = True
    request.session.cycle_key()

    logger.critical("AUDIT: User %s (%s) accessed CMS using emergency recovery code from IP %s", user.id, user.email, client_ip)

    role_name = getattr(getattr(user, 'role_assignment', None), 'role', None)
    role_display = getattr(getattr(user, 'role_assignment', None), 'get_role_display', lambda: 'Staff')()

    return JsonResponse({
        'authenticated': True,
        'recovery_used': True,
        'user': {
            'id': str(user.id),
            'email': user.email,
            'full_name': user.full_name,
            'role': role_name,
            'role_display': role_display,
            'is_super_admin': is_super_admin(user),
            'is_operator': is_operator(user),
        },
    })


@require_GET
@require_cms_auth
def mfa_status_view(request):
    """
    Returns MFA enrollment status and count of remaining recovery codes for the current user.
    """
    user = request.user
    static_device = get_or_create_static_device(user)
    codes_remaining = static_device.token_set.count()

    return JsonResponse({
        'email_otp_enrolled': True,
        'email_masked': mask_email(user.email),
        'recovery_codes_count': codes_remaining,
    })


@ensure_csrf_cookie
@require_POST
@require_cms_auth
def mfa_recovery_codes_generate_view(request):
    """
    Generates a new set of emergency recovery codes.
    Requires password re-authentication to prevent unauthorized generation.
    """
    data, err = _parse_json_body(request)
    if err:
        return err

    password = data.get('password') or ''
    if not request.user.check_password(password):
        return JsonResponse({'detail': 'Password confirmation failed.'}, status=401)

    codes = generate_recovery_codes(request.user, count=5)
    return JsonResponse({
        'recovery_codes': codes,
        'warning': 'Store these recovery codes in a secure location. They are single-use and will not be displayed again.',
    })


@require_GET
def me_view(request):
    """
    Session verification endpoint.
    Checks that request is authenticated, active, and MFA-verified.
    Returns 401 if unauthenticated or if MFA verification is incomplete.
    """
    user = request.user
    if not user or not user.is_authenticated:
        return JsonResponse({'detail': 'Authentication required.'}, status=401)

    if not user.is_active:
        return JsonResponse({'detail': 'Account is inactive.'}, status=401)

    if not user_has_verified_mfa(request, user):
        return JsonResponse({'detail': 'MFA verification required.'}, status=401)

    if not (is_super_admin(user) or is_operator(user)):
        return JsonResponse({'detail': 'Administrative authority required.'}, status=403)

    role_name = getattr(getattr(user, 'role_assignment', None), 'role', None)
    role_display = getattr(getattr(user, 'role_assignment', None), 'get_role_display', lambda: 'Staff')()

    return JsonResponse({
        'authenticated': True,
        'user': {
            'id': str(user.id),
            'email': user.email,
            'full_name': user.full_name,
            'role': role_name,
            'role_display': role_display,
            'is_super_admin': is_super_admin(user),
            'is_operator': is_operator(user),
        },
        'session': {
            'expires_in_seconds': request.session.get_expiry_age(),
            'mfa_verified': True,
        },
        'csrfToken': get_token(request),
    })


@ensure_csrf_cookie
@require_POST
def logout_view(request):
    """
    Terminates the administrative CMS session and flushes session state.
    """
    client_ip = get_client_ip(request)
    if request.user.is_authenticated:
        logger.info("User %s logged out from IP %s", request.user.id, client_ip)

    auth_logout(request)
    request.session.flush()

    return JsonResponse({'detail': 'Successfully logged out.'})


@ensure_csrf_cookie
@require_GET
def csrf_view(request):
    """
    Issues a CSRF cookie and returns the token in the JSON body.
    Allows frontend clients to obtain the CSRF token without needing JavaScript cookie access.
    """
    return JsonResponse({'csrfToken': get_token(request)})
