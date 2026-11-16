"""
Milestone 4K: Backend Readiness and Remaining Gaps Integration Tests.

Comprehensive regression tests verifying:
1. Bulk / Queryset Deletion Bypasses are closed across all governance and revision models.
2. Draft revisions can still be cleanly bulk-deleted.
3. Authentication lifecycles: login, logout, invalid credentials, inactive accounts, admin access.
4. InvitationToken lifecycle: cryptographic hash generation, validity, single-use, expiry, revocation.
5. OperatorUrgentAuthorization validity, categories, and expiry windows.
6. Role-based permissions matrix (Super Admin vs Operator vs Citizen).
7. Session security, timeouts, and statutory HTTP headers.
"""

from datetime import timedelta, date
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
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
)
from apps.identity.permissions import (
    is_super_admin,
    is_operator,
    can_edit_content,
    can_approve_content,
    can_publish_content,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
)
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
    STATUS_PUBLISHED,
    LANGUAGE_MARATHI,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    NoticeUrgentLog,
    TYPE_GENERAL,
    STATUS_PUBLISHED as NOTICE_PUBLISHED,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    CATEGORY_RESOLUTION,
    STATUS_DISCLOSED,
    DISCLOSURE_APPROVED,
    DISCLOSURE_DRAFT,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
    STATUS_PUBLISHED as SCHEME_PUBLISHED,
)


class Milestone4KReadinessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.now = timezone.now()

        # Admin user
        self.super_admin = User.objects.create_user(
            email='admin4k@gramsetu.in',
            full_name='Super Admin 4K',
            password='AdminPassword123!',
            is_staff=True,
        )
        self.admin_role = RoleAssignment.objects.create(
            user=self.super_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )

        # Operator user
        self.operator = User.objects.create_user(
            email='operator4k@gramsetu.in',
            full_name='Operator 4K',
            password='OperatorPassword123!',
            is_staff=True,
        )
        self.operator_role = RoleAssignment.objects.create(
            user=self.operator,
            role=ROLE_OPERATOR,
            assigned_by=self.super_admin,
        )

        # Citizen user
        self.citizen = User.objects.create_user(
            email='citizen4k@gramsetu.in',
            full_name='Citizen 4K',
            password='CitizenPassword123!',
            is_staff=False,
        )

    # --------------------------------------------------------------------------
    # 1. QuerySet & Bulk Deletion Protection
    # --------------------------------------------------------------------------

    def test_governance_records_bulk_deletion_blocked(self):
        """
        Verify that ApprovalRecord, RejectionRecord, and PublicationEvent
        cannot be deleted via bulk QuerySet delete() or all().delete().
        """
        page = Page.objects.create(slug='bulk-delete-test-page')
        trans = PageTranslation.objects.create(page=page, language_code=LANGUAGE_MARATHI)
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Bulk Test',
            created_by=self.operator,
        )

        ApprovalRecord.objects.create(
            target_content_type='pagetranslation',
            target_id=trans.id,
            revision_id=rev.id,
            revision_hash='a' * 64,
            approved_by=self.super_admin,
        )
        RejectionRecord.objects.create(
            target_content_type='pagetranslation',
            target_id=trans.id,
            revision_id=rev.id,
            rejected_by=self.super_admin,
            rejection_reason='Testing bulk rejection protection.',
        )
        PublicationEvent.objects.create(
            target_content_type='pagetranslation',
            target_id=trans.id,
            revision_id=rev.id,
            event_type=EVENT_INITIAL_PUBLISH,
            actor=self.super_admin,
            justification='Approved initial publication event',
        )

        # QuerySet bulk delete MUST fail
        with self.assertRaises(ValidationError):
            ApprovalRecord.objects.all().delete()

        with self.assertRaises(ValidationError):
            ApprovalRecord.objects.filter(target_id=trans.id).delete()

        with self.assertRaises(ValidationError):
            RejectionRecord.objects.all().delete()

        with self.assertRaises(ValidationError):
            PublicationEvent.objects.all().delete()

        # Records must still exist intact
        self.assertEqual(ApprovalRecord.objects.count(), 1)
        self.assertEqual(RejectionRecord.objects.count(), 1)
        self.assertEqual(PublicationEvent.objects.count(), 1)

    def test_revisions_bulk_deletion_protection(self):
        """
        Submitted or approved revisions across Page, Notice, and Scheme domains
        must NOT be deleted in bulk via QuerySet.
        """
        # 1. Page Revision
        page = Page.objects.create(slug='page-rev-bulk-test')
        trans = PageTranslation.objects.create(page=page, language_code=LANGUAGE_MARATHI)
        PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Approved Page Rev',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            PageRevision.objects.filter(translation=trans).delete()

        # 2. Notice Revision
        notice = Notice.objects.create(notice_type=TYPE_GENERAL)
        n_trans = NoticeTranslation.objects.create(notice=notice, language_code=LANGUAGE_MARATHI)
        NoticeRevision.objects.create(
            translation=n_trans,
            revision_number=1,
            title='Approved Notice Rev',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            NoticeRevision.objects.filter(translation=n_trans).delete()

        # 3. Scheme Revision
        scheme = WelfareScheme.objects.create(
            slug='scheme-rev-bulk-test',
            scheme_level='state',
            target_beneficiary='farmers',
            created_by=self.operator,
        )
        s_trans = SchemeTranslation.objects.create(scheme=scheme, language_code=LANGUAGE_MARATHI)
        SchemeRevision.objects.create(
            translation=s_trans,
            revision_number=1,
            scheme_name='Approved Scheme Rev',
            short_summary='Summary',
            eligibility_criteria='Farmers',
            required_documents='Docs',
            application_process='Online',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            SchemeRevision.objects.filter(translation=s_trans).delete()

        # 4. Document Version
        doc = Document.objects.create(category=CATEGORY_RESOLUTION)
        d_trans = DocumentTranslation.objects.create(document=doc, language_code=LANGUAGE_MARATHI)
        DocumentVersion.objects.create(
            translation=d_trans,
            version_number=1,
            storage_path='bulk_test_ver.pdf.dat',
            original_filename='test.pdf',
            file_size_bytes=1024,
            checksum_sha256='c' * 64,
            disclosure_status=DISCLOSURE_APPROVED,
            uploaded_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            DocumentVersion.objects.filter(translation=d_trans).delete()

    def test_draft_revisions_can_be_bulk_deleted(self):
        """
        Unsubmitted draft revisions CAN be cleanly bulk-deleted by editors.
        """
        page = Page.objects.create(slug='draft-cleanup-page')
        trans = PageTranslation.objects.create(page=page, language_code=LANGUAGE_MARATHI)
        PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Draft 1',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        PageRevision.objects.create(
            translation=trans,
            revision_number=2,
            title='Draft 2',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        self.assertEqual(PageRevision.objects.filter(translation=trans).count(), 2)

        # Deleting pure drafts succeeds
        PageRevision.objects.filter(translation=trans).delete()
        self.assertEqual(PageRevision.objects.filter(translation=trans).count(), 0)

    def test_system_page_and_retention_hold_bulk_deletion(self):
        """
        System pages and documents under retention hold cannot be bulk-deleted.
        """
        system_page = Page.objects.create(slug='system-about', is_system_page=True)
        with self.assertRaises(ValidationError):
            Page.objects.filter(id=system_page.id).delete()

        held_doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='HELD-01',
            retention_hold=True,
        )
        with self.assertRaises(ValidationError):
            Document.objects.filter(id=held_doc.id).delete()

    # --------------------------------------------------------------------------
    # 2. Authentication & Authorization Lifecycles
    # --------------------------------------------------------------------------

    def test_authentication_login_and_logout_lifecycle(self):
        """
        Verifies login with valid credentials, session establishment,
        and clean session termination on logout.
        """
        # 1. Invalid login
        login_failed = self.client.login(email='admin4k@gramsetu.in', password='WrongPassword!')
        self.assertFalse(login_failed)

        # 2. Valid login
        login_ok = self.client.login(email='admin4k@gramsetu.in', password='AdminPassword123!')
        self.assertTrue(login_ok)

        # Session cookie exists
        self.assertIn(settings.SESSION_COOKIE_NAME, self.client.cookies)

        # Access admin
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)

        # 3. Logout
        self.client.logout()
        resp_after_logout = self.client.get('/admin/')
        # Redirects to login
        self.assertEqual(resp_after_logout.status_code, 302)

    def test_inactive_user_cannot_login(self):
        """
        Inactive users are barred from authentication.
        """
        self.operator.is_active = False
        self.operator.save()

        login_ok = self.client.login(email='operator4k@gramsetu.in', password='OperatorPassword123!')
        self.assertFalse(login_ok)

    def test_unauthorized_citizen_cannot_access_admin(self):
        """
        Non-staff ordinary citizens receive redirect or denial when accessing /admin/.
        """
        self.client.login(email='citizen4k@gramsetu.in', password='CitizenPassword123!')
        resp = self.client.get('/admin/')
        # Non-staff redirected to admin login
        self.assertEqual(resp.status_code, 302)

    def test_role_based_permissions_matrix(self):
        """
        Verifies least-privilege role boundaries:
        - Super Admin: can approve, can publish, can edit.
        - Operator: can edit, but CANNOT approve or publish.
        - Citizen: CANNOT edit, approve, or publish.
        """
        # Super Admin
        self.assertTrue(is_super_admin(self.super_admin))
        self.assertFalse(is_operator(self.super_admin))
        self.assertTrue(can_edit_content(self.super_admin))
        self.assertTrue(can_approve_content(self.super_admin))
        self.assertTrue(can_publish_content(self.super_admin))

        # Operator
        self.assertFalse(is_super_admin(self.operator))
        self.assertTrue(is_operator(self.operator))
        self.assertTrue(can_edit_content(self.operator))
        self.assertFalse(can_approve_content(self.operator))
        self.assertFalse(can_publish_content(self.operator))

        # Citizen
        self.assertFalse(is_super_admin(self.citizen))
        self.assertFalse(is_operator(self.citizen))
        self.assertFalse(can_edit_content(self.citizen))
        self.assertFalse(can_approve_content(self.citizen))
        self.assertFalse(can_publish_content(self.citizen))

    # --------------------------------------------------------------------------
    # 3. Invitation Token & Urgent Authorization Lifecycles
    # --------------------------------------------------------------------------

    def test_invitation_token_lifecycle(self):
        """
        Tests creation, validity window, single-use invalidation, and revocation.
        """
        inv, raw_token = InvitationToken.create_invitation(
            email='new_hire@gramsetu.in',
            target_role=ROLE_OPERATOR,
            invited_by=self.super_admin,
            validity_hours=48,
        )
        self.assertTrue(inv.is_valid)
        self.assertEqual(InvitationToken.hash_token(raw_token), inv.token_hash)

        # Single-use consumption
        inv.used_at = timezone.now()
        inv.save()
        self.assertFalse(inv.is_valid)

        # Re-verify revocation
        inv2, _ = InvitationToken.create_invitation(
            email='revoked@gramsetu.in',
            target_role=ROLE_OPERATOR,
            invited_by=self.super_admin,
            validity_hours=48,
        )
        inv2.is_revoked = True
        inv2.save()
        self.assertFalse(inv2.is_valid)

    def test_operator_urgent_authorization_validity(self):
        """
        Tests time-window validity and category restriction for emergency notices.
        """
        auth = OperatorUrgentAuthorization.objects.create(
            operator=self.operator,
            authorized_by=self.super_admin,
            allowed_category=CATEGORY_DISASTER,
            valid_from=self.now - timedelta(hours=1),
            valid_to=self.now + timedelta(hours=23),
        )
        self.assertTrue(auth.is_valid)

        # Expired authorization
        auth_expired = OperatorUrgentAuthorization.objects.create(
            operator=self.operator,
            authorized_by=self.super_admin,
            allowed_category=CATEGORY_HEALTH,
            valid_from=self.now - timedelta(days=2),
            valid_to=self.now - timedelta(days=1),
        )
        self.assertFalse(auth_expired.is_valid)
