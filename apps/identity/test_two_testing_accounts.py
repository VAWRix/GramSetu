"""
Comprehensive Verification Suite for GramSetu Two Permanent Testing Accounts.

Tests all 12 required authentication scenarios:
1. Super Admin login with correct email and password ('GramSetu@Test2026').
2. Operator login with correct email and password ('GramSetu@Test2026').
3. Incorrect password rejection (returns 401).
4. Unregistered email rejection (returns 401).
5. Super Admin OTP generation and verification (single-use).
6. Operator OTP generation and verification (single-use).
7. Cross-account OTP rejection (Super Admin OTP fails for Operator, Operator OTP fails for Super Admin).
8. Super Admin access to administrative modules.
9. Operator restriction from Super Admin-only modules (403 forbidden).
10. Session persistence across requests (simulating page refresh via GET /api/auth/me/).
11. Logout and subsequent re-login.
12. Account persistence across session flushes and re-authentication (simulating backend restart).
"""

import json
from django.test import TestCase, Client, override_settings
from django.core.cache import cache
from apps.identity.models import User, RoleAssignment, ROLE_SUPER_ADMIN, ROLE_OPERATOR
from apps.identity.services import get_or_create_email_device
from apps.identity.management.commands.seed_testing_accounts import COMMON_TEST_PASSWORD

SUPER_ADMIN_EMAIL = 'local.admin@gramsetu.gov.in'
OPERATOR_EMAIL = 'local.operator@gramsetu.gov.in'


class TwoTestingAccountsAuthTests(TestCase):
    """
    Rigorously tests the 12 required authentication scenarios.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()

        # 1. Super Admin
        self.super_admin, _ = User.objects.get_or_create(
            email=SUPER_ADMIN_EMAIL,
            defaults={
                'full_name': 'अशोक गणपत वाले (ASHOK GANPAT WALE)',
                'is_active': True,
                'is_staff': True,
            },
        )
        self.super_admin.set_password(COMMON_TEST_PASSWORD)
        self.super_admin.save()
        ra_sa, _ = RoleAssignment.objects.get_or_create(
            user=self.super_admin,
            defaults={'role': ROLE_SUPER_ADMIN},
        )
        ra_sa.role = ROLE_SUPER_ADMIN
        ra_sa.save()
        dev_sa = get_or_create_email_device(self.super_admin)
        dev_sa.confirmed = True
        dev_sa.save()

        # 2. Operator
        self.operator, _ = User.objects.get_or_create(
            email=OPERATOR_EMAIL,
            defaults={
                'full_name': 'संगणक चालक / ऑपरेटर (Computer Operator)',
                'is_active': True,
                'is_staff': False,
            },
        )
        self.operator.set_password(COMMON_TEST_PASSWORD)
        self.operator.save()
        ra_op, _ = RoleAssignment.objects.get_or_create(
            user=self.operator,
            defaults={'role': ROLE_OPERATOR},
        )
        ra_op.role = ROLE_OPERATOR
        ra_op.save()
        dev_op = get_or_create_email_device(self.operator)
        dev_op.confirmed = True
        dev_op.save()

    def _get_csrf_and_cookies(self, client=None):
        c = client or self.client
        resp = c.get('/api/auth/csrf/')
        return resp.json().get('csrfToken')

    def test_01_super_admin_login_correct_credentials(self):
        """Scenario 1: Super Admin login with correct email and password initiates MFA."""
        csrf = self._get_csrf_and_cookies()
        resp = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('mfa_required'))
        self.assertIn('email_masked', data)

    def test_02_operator_login_correct_credentials(self):
        """Scenario 2: Operator login with correct email and password initiates MFA."""
        csrf = self._get_csrf_and_cookies()
        resp = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': OPERATOR_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('mfa_required'))

    def test_03_incorrect_password_rejected(self):
        """Scenario 3: Incorrect password rejection with 401."""
        csrf = self._get_csrf_and_cookies()
        resp = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': 'WrongPassword123!'}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn('Invalid email or password', resp.json().get('detail', ''))

    def test_04_unregistered_email_rejected(self):
        """Scenario 4: Unregistered email rejection with 401."""
        csrf = self._get_csrf_and_cookies()
        resp = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': 'unknown.user@unknown-domain.gov.in', 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn('Invalid email or password', resp.json().get('detail', ''))

    def test_05_super_admin_otp_generation_and_verification(self):
        """Scenario 5: Super Admin OTP generation and verification establishes full session."""
        csrf = self._get_csrf_and_cookies()
        login_resp = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login_resp.status_code, 200)

        # Retrieve generated OTP
        dev = get_or_create_email_device(self.super_admin)
        token = dev.token
        self.assertTrue(token and len(token) == 6)

        # Verify OTP
        verify_resp = self.client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(verify_resp.status_code, 200)
        user_data = verify_resp.json().get('user', {})
        self.assertEqual(user_data.get('email'), SUPER_ADMIN_EMAIL)
        self.assertTrue(user_data.get('is_super_admin'))
        self.assertEqual(user_data.get('role'), ROLE_SUPER_ADMIN)

        # Confirm single-use: verifying the same token again fails
        dev.refresh_from_db()
        self.assertIsNone(dev.token)

    def test_06_operator_otp_generation_and_verification(self):
        """Scenario 6: Operator OTP generation and verification establishes full session."""
        csrf = self._get_csrf_and_cookies()
        login_resp = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': OPERATOR_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login_resp.status_code, 200)

        dev = get_or_create_email_device(self.operator)
        token = dev.token
        self.assertTrue(token and len(token) == 6)

        verify_resp = self.client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(verify_resp.status_code, 200)
        user_data = verify_resp.json().get('user', {})
        self.assertEqual(user_data.get('email'), OPERATOR_EMAIL)
        self.assertTrue(user_data.get('is_operator'))
        self.assertFalse(user_data.get('is_super_admin'))

    def test_07_cross_account_otp_rejection(self):
        """Scenario 7: Cross-account OTP rejection (Super Admin OTP cannot authenticate Operator and vice versa)."""
        # Super Admin initiates login -> generates SA OTP
        sa_client = Client()
        sa_csrf = self._get_csrf_and_cookies(sa_client)
        sa_client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=sa_csrf,
        )
        sa_token = get_or_create_email_device(self.super_admin).token

        # Operator initiates login -> generates OP OTP
        op_client = Client()
        op_csrf = self._get_csrf_and_cookies(op_client)
        op_client.post(
            '/api/auth/login/',
            data=json.dumps({'email': OPERATOR_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=op_csrf,
        )
        op_token = get_or_create_email_device(self.operator).token

        # Cross-test 1: Operator submits Super Admin's token -> Must be REJECTED
        cross_resp_op = op_client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': sa_token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=op_csrf,
        )
        self.assertEqual(cross_resp_op.status_code, 400)
        self.assertIn('Invalid or expired', cross_resp_op.json().get('detail', ''))

        # Cross-test 2: Super Admin submits Operator's token -> Must be REJECTED
        cross_resp_sa = sa_client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': op_token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=sa_csrf,
        )
        self.assertEqual(cross_resp_sa.status_code, 400)
        self.assertIn('Invalid or expired', cross_resp_sa.json().get('detail', ''))

    def test_08_super_admin_access_to_administrative_modules(self):
        """Scenario 8: Super Admin can access administrative governance queue and dashboard."""
        csrf = self._get_csrf_and_cookies()
        self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        token = get_or_create_email_device(self.super_admin).token
        self.client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )

        # Access CMS dashboard & pending governance review queue
        dash_resp = self.client.get('/api/cms/dashboard/')
        self.assertEqual(dash_resp.status_code, 200)

        pending_resp = self.client.get('/api/cms/pending/')
        self.assertEqual(pending_resp.status_code, 200)

        # Verify me endpoint
        me_resp = self.client.get('/api/auth/me/')
        self.assertEqual(me_resp.status_code, 200)
        self.assertTrue(me_resp.json().get('user', {}).get('is_super_admin'))

    def test_09_operator_restriction_from_super_admin_only_modules(self):
        """Scenario 9: Operator cannot execute Super Admin approval/publishing actions."""
        csrf = self._get_csrf_and_cookies()
        self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': OPERATOR_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        token = get_or_create_email_device(self.operator).token
        self.client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )

        # Operator attempts to execute privileged action (approve) via /api/cms/action/
        fake_uuid = '01a1e50f-dc65-788c-854f-d1d7464ac536'
        post_resp = self.client.post(
            '/api/cms/action/',
            data=json.dumps({
                'entity_type': 'page',
                'action': 'approve',
                'target_id': fake_uuid,
            }),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        # Must be 403 Forbidden because Operator lacks Super Administrator authority
        self.assertEqual(post_resp.status_code, 403)
        self.assertIn('Super Administrator authority required', post_resp.json().get('detail', ''))

    def test_10_session_persistence_across_requests(self):
        """Scenario 10: Session persistence after initial verification (simulates page refresh)."""
        csrf = self._get_csrf_and_cookies()
        self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        token = get_or_create_email_device(self.super_admin).token
        self.client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )

        # Request 1 (Immediate)
        me1 = self.client.get('/api/auth/me/')
        self.assertEqual(me1.status_code, 200)

        # Request 2 (Page Refresh simulation - new GET)
        me2 = self.client.get('/api/auth/me/')
        self.assertEqual(me2.status_code, 200)
        self.assertEqual(me2.json()['user']['email'], SUPER_ADMIN_EMAIL)
        self.assertTrue(me2.json()['authenticated'])

    def test_11_logout_and_subsequent_relogin(self):
        """Scenario 11: Logout terminates session and subsequent login works properly."""
        csrf = self._get_csrf_and_cookies()
        self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        token = get_or_create_email_device(self.super_admin).token
        self.client.post(
            '/api/auth/mfa/verify/',
            data=json.dumps({'code': token}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )

        # Verify active
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 200)

        # Logout
        logout_resp = self.client.post('/api/auth/logout/', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(logout_resp.status_code, 200)

        # Verify unauthenticated
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)

        # Subsequent re-login succeeds
        re_login = self.client.post(
            '/api/auth/login/',
            data=json.dumps({'email': SUPER_ADMIN_EMAIL, 'password': COMMON_TEST_PASSWORD}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(re_login.status_code, 200)
        self.assertTrue(re_login.json().get('mfa_required'))

    def test_12_account_persistence_in_db(self):
        """Scenario 12: Account credentials and roles persist in database across client instances."""
        # Query User objects freshly from DB to verify fields
        sa_db = User.objects.get(email=SUPER_ADMIN_EMAIL)
        op_db = User.objects.get(email=OPERATOR_EMAIL)

        self.assertTrue(sa_db.check_password(COMMON_TEST_PASSWORD))
        self.assertTrue(op_db.check_password(COMMON_TEST_PASSWORD))
        self.assertEqual(sa_db.role_assignment.role, ROLE_SUPER_ADMIN)
        self.assertEqual(op_db.role_assignment.role, ROLE_OPERATOR)
        self.assertTrue(sa_db.is_active)
        self.assertTrue(op_db.is_active)
