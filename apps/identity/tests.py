"""
Unit tests for apps.identity models and constraints.
"""

from datetime import timedelta
import hashlib
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import timezone
from apps.identity.models import (
    User,
    RoleAssignment,
    InvitationToken,
    OperatorUrgentAuthorization,
    ROLE_SUPER_ADMIN,
    ROLE_OPERATOR,
    CATEGORY_DISASTER,
    CATEGORY_HEALTH,
    CATEGORY_WATER,
    CATEGORY_WEATHER,
)


class UserModelTests(SimpleTestCase):
    """
    Unit tests for custom User model logic and normalization.
    """

    def test_user_creation_and_email_normalization(self):
        user = User(
            email='Test.User@GramPanchayat.gov.in',
            full_name='Ramesh Patil',
        )
        user.clean()
        self.assertEqual(user.email, 'test.user@grampanchayat.gov.in')
        self.assertEqual(str(user), 'Ramesh Patil (test.user@grampanchayat.gov.in)')

    def test_password_hashing(self):
        user = User(email='operator@gramsetu.in', full_name='Sunita Deshmukh')
        user.set_password('Secr3t!P@ssw0rd')
        self.assertTrue(user.check_password('Secr3t!P@ssw0rd'))
        self.assertFalse(user.check_password('WrongPassword'))
        # Ensure password is not stored in plaintext
        self.assertNotEqual(user.password, 'Secr3t!P@ssw0rd')
        self.assertTrue(user.password.startswith('pbkdf2_sha256$'))

    def test_user_defaults_prevent_accidental_privilege_escalation(self):
        user = User(email='operator@gramsetu.in', full_name='Suresh Pawar')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff, "New users must not have staff privileges by default.")
        self.assertFalse(user.is_superuser, "New users must not have superuser privileges by default.")

    def test_manager_missing_email_raises_error(self):
        with self.assertRaisesMessage(ValueError, "The Email field must be set."):
            User.objects.create_user(email='', full_name='Test User')

    def test_manager_missing_full_name_raises_error(self):
        with self.assertRaisesMessage(ValueError, "The Full Name field must be set."):
            User.objects.create_user(email='test@example.com', full_name='')


class RoleAssignmentTests(SimpleTestCase):
    """
    Tests for RoleAssignment business logic and separation of concerns.
    """

    def test_role_properties(self):
        user = User(email='admin@gramsetu.in', full_name='Gram Sevak')
        admin_role = RoleAssignment(user=user, role=ROLE_SUPER_ADMIN)
        self.assertTrue(admin_role.is_super_admin)
        self.assertFalse(admin_role.is_operator)
        self.assertIn('Super Administrator', str(admin_role))

        op_role = RoleAssignment(user=user, role=ROLE_OPERATOR)
        self.assertFalse(op_role.is_super_admin)
        self.assertTrue(op_role.is_operator)
        self.assertIn('Operator', str(op_role))

    def test_business_roles_distinct_from_django_superuser(self):
        """
        Verify that having a Super Administrator business role does not implicitly
        give Django superuser status or vice versa.
        """
        user = User(email='officer@gramsetu.in', full_name='Gram Sevak', is_superuser=False)
        role = RoleAssignment(user=user, role=ROLE_SUPER_ADMIN)
        self.assertTrue(role.is_super_admin)
        self.assertFalse(user.is_superuser)


class InvitationTokenTests(SimpleTestCase):
    """
    Tests for InvitationToken generation, hash storage, and expiry semantics.
    """

    def test_invitation_token_hash_and_validity(self):
        admin = User(email='admin@gramsetu.in', full_name='Admin User')
        now = timezone.now()
        raw_token = 'secret_invitation_token_12345'
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

        token = InvitationToken(
            email='new.operator@gramsetu.in',
            target_role=ROLE_OPERATOR,
            token_hash=token_hash,
            invited_by=admin,
            expires_at=now + timedelta(hours=48),
        )

        self.assertTrue(token.is_valid)

        # Token is invalid if revoked
        token.is_revoked = True
        self.assertFalse(token.is_valid)
        token.is_revoked = False

        # Token is invalid if already used
        token.used_at = now
        self.assertFalse(token.is_valid)
        token.used_at = None

        # Token is invalid if expired
        token.expires_at = now - timedelta(hours=1)
        self.assertFalse(token.is_valid)


class OperatorUrgentAuthorizationTests(SimpleTestCase):
    """
    Tests for OperatorUrgentAuthorization rules and anti-self-granting validation.
    """

    def test_anti_self_granting_validation(self):
        user_id = '01a14e91-0b97-7c88-997e-fb17b6bad16d'
        auth = OperatorUrgentAuthorization(
            operator_id=user_id,
            authorized_by_id=user_id,
            allowed_category=CATEGORY_DISASTER,
            valid_from=timezone.now(),
            valid_to=timezone.now() + timedelta(days=7),
        )
        with self.assertRaises(ValidationError) as ctx:
            auth.clean()
        self.assertIn("cannot grant urgent authorization to themselves", str(ctx.exception))

    def test_authorization_validity_window(self):
        now = timezone.now()
        auth = OperatorUrgentAuthorization(
            operator_id='01a14e91-0b97-7c88-997e-fb17b6bad16d',
            authorized_by_id='01a14e91-0b97-7c88-997e-fb17b6bad16e',
            allowed_category=CATEGORY_HEALTH,
            valid_from=now - timedelta(days=1),
            valid_to=now + timedelta(days=6),
            is_revoked=False,
        )
        self.assertTrue(auth.is_valid)

        # Expired
        auth.valid_to = now - timedelta(hours=1)
        self.assertFalse(auth.is_valid)

        # Revoked
        auth.valid_to = now + timedelta(days=6)
        auth.is_revoked = True
        self.assertFalse(auth.is_valid)

        # Future
        auth.is_revoked = False
        auth.valid_from = now + timedelta(days=1)
        self.assertFalse(auth.is_valid)
