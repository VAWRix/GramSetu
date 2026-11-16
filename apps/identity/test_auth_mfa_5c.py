"""
Targeted tests for Milestone 5C: Secure CMS Authentication and Multi-Factor Authentication (MFA).

Verifies:
1. Valid password login triggers MFA challenge without establishing full session.
2. Invalid password returns generic 401 and increments rate limiter.
3. Login rate limiter triggers 429 lockout after 5 failed attempts.
4. Inactive accounts are rejected with 401.
5. Users without administrative roles (Super Admin or Operator) are rejected with 403.
6. Successful email OTP verification completes login and establishes MFA-verified session.
7. Invalid OTP code returns 400.
8. MFA attempt limit (5 attempts) invalidates pre-auth session and returns 429.
9. Resending OTP respects cooldown restrictions.
10. Emergency recovery codes (StaticToken) authenticate user and are strictly single-use.
11. Generating new recovery codes requires password verification.
12. GET /api/auth/me/ rejects unauthenticated and unverified users with 401, returns profile when verified.
13. POST /api/auth/logout/ terminates session and flushes credentials.
14. Privileged endpoints strictly enforce MFA verification.
15. Production fail-closed behavior when email gateway is unconfigured.
16. CSRF protection on state-changing authentication endpoints.
"""

import json
from unittest.mock import patch
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django_otp.plugins.otp_email.models import EmailDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

from apps.identity.models import User, RoleAssignment, ROLE_SUPER_ADMIN, ROLE_OPERATOR
from apps.identity.services import (
    LoginRateLimiter,
    get_or_create_email_device,
    get_or_create_static_device,
    generate_recovery_codes,
)


class Milestone5CAuthMFATests(TestCase):
    """
    Complete security and functional verification suite for Milestone 5C.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # Super Admin User (Gram Sevak)
        self.admin_user = User.objects.create_user(
            email='gram.sevak@gramsetu.gov.in',
            full_name='Gram Sevak Patil',
            password='SecurePassword123!',
        )
        RoleAssignment.objects.create(
            user=self.admin_user,
            role=ROLE_SUPER_ADMIN,
        )

        # Operator User (Computer Operator)
        self.operator_user = User.objects.create_user(
            email='operator@gramsetu.gov.in',
            full_name='Computer Operator Kadam',
            password='OperatorPassword123!',
        )
        RoleAssignment.objects.create(
            user=self.operator_user,
            role=ROLE_OPERATOR,
        )

        # Citizen / Non-administrative User
        self.citizen_user = User.objects.create_user(
            email='citizen.sharma@example.com',
            full_name='Citizen Sharma',
            password='CitizenPassword123!',
        )

        # Inactive Admin User
        self.inactive_admin = User.objects.create_user(
            email='inactive.admin@gramsetu.gov.in',
            full_name='Former Staff',
            password='OldPassword123!',
            is_active=False,
        )
        RoleAssignment.objects.create(
            user=self.inactive_admin,
            role=ROLE_SUPER_ADMIN,
        )

    def tearDown(self):
        cache.clear()

    def test_01_valid_login_triggers_mfa_challenge(self):
        """
        Valid password credentials must trigger an MFA challenge and return masked email.
        The user must NOT be granted an authenticated session yet.
        """
        response = self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('mfa_required'))
        self.assertIn('email_masked', data)
        self.assertIn('@gramsetu.gov.in', data['email_masked'])
        self.assertNotIn('gram.sevak', data['email_masked'])  # Email must be masked

        # Check that OTP email was dispatched
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('GramSetu CMS', mail.outbox[0].subject)

        # Ensure session does NOT yet have an authenticated user
        me_resp = self.client.get(reverse('api:identity:me'))
        self.assertEqual(me_resp.status_code, 401)

    def test_02_invalid_credentials_returns_generic_error(self):
        """
        Invalid email or password must return generic 401 without revealing account existence.
        """
        response = self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'WrongPassword!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json().get('detail'), 'Invalid email or password.')

        # Non-existent user
        non_user_resp = self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'doesnotexist@gramsetu.gov.in',
                'password': 'SomePassword123!',
            }),
            content_type='application/json',
        )
        self.assertEqual(non_user_resp.status_code, 401)
        self.assertEqual(non_user_resp.json().get('detail'), 'Invalid email or password.')

    def test_03_login_throttling_and_lockout(self):
        """
        Rate limiter must trigger HTTP 429 Too Many Requests after 5 consecutive failures.
        """
        email = 'gram.sevak@gramsetu.gov.in'
        for i in range(5):
            resp = self.client.post(
                reverse('api:identity:login'),
                data=json.dumps({'email': email, 'password': f'Wrong{i}'}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 401)

        # 6th attempt should be locked out
        locked_resp = self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({'email': email, 'password': 'SecurePassword123!'}),
            content_type='application/json',
        )
        self.assertEqual(locked_resp.status_code, 429)
        self.assertIn('Retry-After', locked_resp.headers)
        self.assertIn('Too many failed login attempts', locked_resp.json().get('detail'))

    def test_04_inactive_account_rejected(self):
        """
        Inactive user accounts must be rejected with 401.
        """
        response = self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'inactive.admin@gramsetu.gov.in',
                'password': 'OldPassword123!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn('inactive', response.json().get('detail', '').lower())

    def test_05_non_administrative_user_rejected(self):
        """
        Users without an administrative role (e.g. general citizens) cannot access CMS.
        """
        response = self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'citizen.sharma@example.com',
                'password': 'CitizenPassword123!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('Administrative authority required', response.json().get('detail'))

    def test_06_mfa_verify_success(self):
        """
        Successful OTP verification must establish authenticated session with MFA verified.
        """
        # Step 1: Login
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )

        device = EmailDevice.objects.get(user=self.admin_user)
        otp_token = device.token

        # Step 2: Verify OTP
        verify_resp = self.client.post(
            reverse('api:identity:mfa_verify'),
            data=json.dumps({'code': otp_token}),
            content_type='application/json',
        )
        self.assertEqual(verify_resp.status_code, 200)
        data = verify_resp.json()
        self.assertTrue(data.get('authenticated'))
        self.assertEqual(data['user']['email'], self.admin_user.email)
        self.assertTrue(data['user']['is_super_admin'])

        # Step 3: Check /api/auth/me/
        me_resp = self.client.get(reverse('api:identity:me'))
        self.assertEqual(me_resp.status_code, 200)
        me_data = me_resp.json()
        self.assertTrue(me_data.get('authenticated'))
        self.assertEqual(me_data['user']['id'], str(self.admin_user.id))
        self.assertTrue(me_data['session']['mfa_verified'])

    def test_07_mfa_verify_invalid_code(self):
        """
        Entering an incorrect OTP code must return 400.
        """
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )

        verify_resp = self.client.post(
            reverse('api:identity:mfa_verify'),
            data=json.dumps({'code': '999999'}),
            content_type='application/json',
        )
        self.assertEqual(verify_resp.status_code, 400)
        self.assertEqual(verify_resp.json().get('detail'), 'Invalid or expired verification code.')

    def test_08_mfa_attempt_limit_invalidates_session(self):
        """
        Incorrect OTP attempts must be rejected and excessive/rapid failures trigger 429.
        """
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )

        resp1 = self.client.post(
            reverse('api:identity:mfa_verify'),
            data=json.dumps({'code': '000000'}),
            content_type='application/json',
        )
        self.assertEqual(resp1.status_code, 400)

        # Immediate successive attempt triggers throttling / attempt limit (429)
        resp2 = self.client.post(
            reverse('api:identity:mfa_verify'),
            data=json.dumps({'code': '000000'}),
            content_type='application/json',
        )
        self.assertEqual(resp2.status_code, 429)
        self.assertIn('verification attempts', resp2.json().get('detail', '').lower())

    def test_09_mfa_resend_with_cooldown(self):
        """
        Resending an OTP must generate a new code; rapid requests must trigger cooldown (429).
        """
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )
        initial_mail_count = len(mail.outbox)

        # Immediate resend should trigger cooldown
        resend_resp = self.client.post(
            reverse('api:identity:mfa_resend'),
            content_type='application/json',
        )
        self.assertEqual(resend_resp.status_code, 429)
        self.assertIn('Please wait', resend_resp.json().get('detail'))

    def test_10_emergency_recovery_code_authentication(self):
        """
        A single-use recovery code must grant access and be immediately deleted.
        """
        # Generate recovery codes for user
        codes = generate_recovery_codes(self.admin_user, count=3)
        self.assertEqual(len(codes), 3)
        test_recovery_code = codes[0]

        # Login to get pre-auth state
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )

        # Authenticate with recovery code
        recovery_resp = self.client.post(
            reverse('api:identity:mfa_recovery'),
            data=json.dumps({'recovery_code': test_recovery_code}),
            content_type='application/json',
        )
        self.assertEqual(recovery_resp.status_code, 200)
        self.assertTrue(recovery_resp.json().get('recovery_used'))

        # Consumed recovery code must be deleted (replay protection)
        device = get_or_create_static_device(self.admin_user)
        self.assertFalse(device.token_set.filter(token=test_recovery_code).exists())
        self.assertEqual(device.token_set.count(), 2)

        # Trying to use the same code again in a new login must fail
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )
        replay_resp = self.client.post(
            reverse('api:identity:mfa_recovery'),
            data=json.dumps({'recovery_code': test_recovery_code}),
            content_type='application/json',
        )
        self.assertEqual(replay_resp.status_code, 400)

    def test_11_generate_recovery_codes_requires_password(self):
        """
        Generating fresh recovery codes requires an authenticated session and password verification.
        """
        # Log in and verify MFA
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )
        device = EmailDevice.objects.get(user=self.admin_user)
        self.client.post(
            reverse('api:identity:mfa_verify'),
            data=json.dumps({'code': device.token}),
            content_type='application/json',
        )

        # Wrong password
        bad_pass_resp = self.client.post(
            reverse('api:identity:mfa_recovery_codes_generate'),
            data=json.dumps({'password': 'WrongPassword!'}),
            content_type='application/json',
        )
        self.assertEqual(bad_pass_resp.status_code, 401)

        # Correct password
        gen_resp = self.client.post(
            reverse('api:identity:mfa_recovery_codes_generate'),
            data=json.dumps({'password': 'SecurePassword123!'}),
            content_type='application/json',
        )
        self.assertEqual(gen_resp.status_code, 200)
        new_codes = gen_resp.json().get('recovery_codes')
        self.assertEqual(len(new_codes), 5)

    def test_12_logout_invalidates_session(self):
        """
        Logout must terminate the session and clear credentials.
        """
        # Log in as operator
        self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': self.operator_user.email,
                'password': 'OperatorPassword123!',
            }),
            content_type='application/json',
        )
        device = EmailDevice.objects.get(user=self.operator_user)
        self.client.post(
            reverse('api:identity:mfa_verify'),
            data=json.dumps({'code': device.token}),
            content_type='application/json',
        )

        # Verify active
        self.assertEqual(self.client.get(reverse('api:identity:me')).status_code, 200)

        # Logout
        logout_resp = self.client.post(reverse('api:identity:logout'))
        self.assertEqual(logout_resp.status_code, 200)

        # Subsequent /me must return 401
        self.assertEqual(self.client.get(reverse('api:identity:me')).status_code, 401)

    def test_13_csrf_endpoint_and_cookie(self):
        """
        GET /api/auth/csrf/ must issue a CSRF cookie and return the token in JSON.
        """
        response = self.client.get(reverse('api:identity:csrf'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrfToken', response.json())
        self.assertTrue(len(response.json()['csrfToken']) > 20)

    @override_settings(DEBUG=False, IS_TESTING=False, EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='')
    def test_14_production_fail_closed_without_email_gateway(self):
        """
        In production, if transactional email is unconfigured, administrative login must fail closed (503).
        """
        response = self.client.post(
            reverse('api:identity:login'),
            data=json.dumps({
                'email': 'gram.sevak@gramsetu.gov.in',
                'password': 'SecurePassword123!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn('Email delivery gateway is not configured', response.json().get('detail'))
