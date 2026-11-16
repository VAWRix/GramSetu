"""
Role-based permission helpers for GramSetu platform.

Enforces least-privilege administrative access based on approved RoleAssignment:
- Super Administrator: full governance authority (approval, rejection, publication, rollback, withdrawal).
- Operator: content authoring authority (draft pages, translations, revisions, and submit for review).
- Separation of duties: authors can NEVER approve their own revisions.
"""

from apps.identity.models import ROLE_SUPER_ADMIN, ROLE_OPERATOR


def is_super_admin(user) -> bool:
    """
    Returns True if user is an authenticated Super Administrator or CLI superuser.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if hasattr(user, 'role_assignment') and user.role_assignment.role == ROLE_SUPER_ADMIN:
        return True
    return False


def is_operator(user) -> bool:
    """
    Returns True if user is an authenticated Operator.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if hasattr(user, 'role_assignment') and user.role_assignment.role == ROLE_OPERATOR:
        return True
    return False


def can_edit_content(user) -> bool:
    """
    Returns True if user is permitted to create or edit draft pages, translations, or revisions.
    """
    return is_super_admin(user) or is_operator(user)


def can_approve_content(user) -> bool:
    """
    Returns True if user has Super Administrator authority to approve or reject submitted content.
    """
    return is_super_admin(user)


def can_publish_content(user) -> bool:
    """
    Returns True if user has Super Administrator authority to publish, schedule, or withdraw content.
    """
    return is_super_admin(user)


def user_has_verified_mfa(request, user) -> bool:
    """
    Checks if an authenticated user has satisfied the multi-factor authentication requirement.
    Uses django_otp's is_verified() or session verification flag.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    is_verified = getattr(user, 'is_verified', None)
    if callable(is_verified) and is_verified():
        return True
    return bool(request.session.get('mfa_verified', False))


def require_cms_auth(view_func):
    """
    Decorator enforcing:
    1. User is authenticated and active
    2. User has an administrative role (Super Administrator or Operator)
    3. User has completed MFA verification (no password-only bypass)
    """
    from functools import wraps
    from django.http import JsonResponse

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user or not user.is_authenticated:
            return JsonResponse({'detail': 'Authentication required.'}, status=401)
        if not user.is_active:
            return JsonResponse({'detail': 'Account is inactive.'}, status=401)
        if not user_has_verified_mfa(request, user):
            return JsonResponse({'detail': 'Multi-factor authentication (MFA) verification required.'}, status=401)
        if not (is_super_admin(user) or is_operator(user)):
            return JsonResponse({'detail': 'Administrative authority required.'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def require_super_admin(view_func):
    """
    Decorator enforcing Super Administrator authority with verified MFA.
    """
    from functools import wraps
    from django.http import JsonResponse

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if not user or not user.is_authenticated:
            return JsonResponse({'detail': 'Authentication required.'}, status=401)
        if not user.is_active:
            return JsonResponse({'detail': 'Account is inactive.'}, status=401)
        if not user_has_verified_mfa(request, user):
            return JsonResponse({'detail': 'Multi-factor authentication (MFA) verification required.'}, status=401)
        if not is_super_admin(user):
            return JsonResponse({'detail': 'Super Administrator authority required.'}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped_view

