"""
Authentication and MFA URL routing for GramSetu platform.
"""

from django.urls import path
from apps.identity.views import (
    login_view,
    mfa_verify_view,
    mfa_resend_view,
    mfa_recovery_view,
    mfa_status_view,
    mfa_recovery_codes_generate_view,
    me_view,
    logout_view,
    csrf_view,
)

app_name = 'identity'

urlpatterns = [
    path('login/', login_view, name='login'),
    path('mfa/verify/', mfa_verify_view, name='mfa_verify'),
    path('mfa/resend/', mfa_resend_view, name='mfa_resend'),
    path('mfa/recovery/', mfa_recovery_view, name='mfa_recovery'),
    path('mfa/status/', mfa_status_view, name='mfa_status'),
    path('mfa/recovery-codes/generate/', mfa_recovery_codes_generate_view, name='mfa_recovery_codes_generate'),
    path('me/', me_view, name='me'),
    path('logout/', logout_view, name='logout'),
    path('csrf/', csrf_view, name='csrf'),
]
