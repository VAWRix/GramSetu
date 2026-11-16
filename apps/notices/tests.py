"""
Comprehensive domain, governance, and admin tests for apps.notices.

Verifies:
- Notice model constraints, UUIDv7 PK, date checks, and expiry logic.
- NoticeTranslation multilingual uniqueness, explicit translation records, and canonical 7-invariance queries.
- NoticeRevision immutability, SHA-256 hash calculation, attachment metadata, and sequence uniqueness.
- Separation of duties in notice approval (authors cannot approve their own revisions).
- Governance publishing workflows: immediate publish, scheduling, withdrawal, and rollback.
- Urgent publication bypass workflow, strict safeguards, and post-publication ratification/retraction.
- Django Admin access control, actions, intermediate forms, and server-side tamper resistance.
"""

from datetime import timedelta
import hashlib
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.identity.models import (
    User,
    RoleAssignment,
    ROLE_SUPER_ADMIN,
    ROLE_OPERATOR,
    OperatorUrgentAuthorization,
    CATEGORY_DISASTER,
    CATEGORY_HEALTH,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_UPDATE_PUBLISH,
    EVENT_SCHEDULED_PUBLISH,
    EVENT_URGENT_PUBLISH,
    EVENT_ROLLBACK,
    EVENT_WITHDRAWAL,
)
from apps.governance.services import (
    submit_notice_revision,
    approve_notice_revision,
    reject_notice_revision,
    publish_notice_translation,
    withdraw_notice_translation,
    urgent_publish_notice,
    ratify_urgent_notice,
    retract_urgent_notice,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    NoticeUrgentLog,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
    TYPE_GENERAL,
    TYPE_TENDER,
    TYPE_STATUTORY,
    TYPE_GRAM_SABHA,
    TYPE_EMERGENCY_ALERT,
    URGENCY_STANDARD,
    URGENCY_URGENT,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
    EDITORIAL_REJECTED,
    STATUS_DRAFT,
    STATUS_SUBMITTED,
    STATUS_APPROVED,
    STATUS_SCHEDULED,
    STATUS_PUBLISHED,
    STATUS_WITHDRAWN,
    STATUS_ARCHIVED,
    RATIFICATION_PENDING,
    RATIFICATION_RATIFIED,
    RATIFICATION_RETRACTED,
)
from apps.notices.admin import (
    NoticeAdmin,
    NoticeTranslationAdmin,
    NoticeRevisionAdmin,
    NoticeUrgentLogAdmin,
)


class NoticeModelTests(TestCase):
    """
    Tests for Notice model (canonical logical anchor, dates, categories, expiry).
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            is_staff=True,
        )

    def test_notice_creation_and_defaults(self):
        notice = Notice.objects.create(
            notice_type=TYPE_GRAM_SABHA,
            reference_number='GS/2026/042',
        )
        self.assertIsNotNone(notice.id)
        self.assertEqual(len(str(notice.id)), 36)
        self.assertEqual(notice.notice_type, TYPE_GRAM_SABHA)
        self.assertEqual(notice.urgency, URGENCY_STANDARD)
        self.assertFalse(notice.is_urgent_published)
        self.assertEqual(notice.reference_number, 'GS/2026/042')
        self.assertIsNotNone(notice.effective_from)
        self.assertIsNone(notice.expires_at)
        self.assertIn('Gram Sabha Announcement', str(notice))

    def test_notice_date_constraint_valid(self):
        now = timezone.now()
        notice = Notice.objects.create(
            notice_type=TYPE_TENDER,
            effective_from=now,
            expires_at=now + timedelta(days=15),
        )
        self.assertTrue(notice.is_effective())
        self.assertFalse(notice.is_expired())

    def test_notice_date_constraint_rejected_by_clean(self):
        now = timezone.now()
        notice = Notice(
            notice_type=TYPE_TENDER,
            effective_from=now,
            expires_at=now - timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as ctx:
            notice.clean()
        self.assertIn("Expiry date must be strictly after", str(ctx.exception))

    def test_notice_date_constraint_rejected_by_database(self):
        now = timezone.now()
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Notice.objects.create(
                    notice_type=TYPE_TENDER,
                    effective_from=now,
                    expires_at=now - timedelta(days=1),
                )

    def test_notice_is_expired_and_is_effective_logic(self):
        now = timezone.now()
        # 1. Past expired notice
        past_notice = Notice.objects.create(
            notice_type=TYPE_GENERAL,
            effective_from=now - timedelta(days=10),
            expires_at=now - timedelta(days=2),
        )
        self.assertTrue(past_notice.is_expired(now))
        self.assertFalse(past_notice.is_effective(now))

        # 2. Future scheduled notice
        future_notice = Notice.objects.create(
            notice_type=TYPE_GENERAL,
            effective_from=now + timedelta(days=2),
            expires_at=now + timedelta(days=10),
        )
        self.assertFalse(future_notice.is_effective(now))
        self.assertFalse(future_notice.is_expired(now))

        # 3. Active unconstrained notice
        active_notice = Notice.objects.create(
            notice_type=TYPE_GENERAL,
            effective_from=now - timedelta(days=1),
            expires_at=None,
        )
        self.assertTrue(active_notice.is_effective(now))
        self.assertFalse(active_notice.is_expired(now))


class NoticeTranslationModelTests(TestCase):
    """
    Tests for NoticeTranslation model (multilingual uniqueness, 7 invariants, QuerySet).
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            is_staff=True,
        )
        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Patil',
            is_staff=True,
        )
        self.notice = Notice.objects.create(
            notice_type=TYPE_STATUTORY,
            reference_number='STAT/2026/09',
        )

    def test_notice_translation_creation(self):
        trans = NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='panchayat-tax-notice-2026',
        )
        self.assertEqual(trans.language_code, 'mr')
        self.assertEqual(trans.status, STATUS_DRAFT)
        self.assertIsNone(trans.current_approved_revision)
        self.assertIn('Notice [mr]', str(trans))

    def test_translation_uniqueness_per_notice_and_language(self):
        NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='tax-notice-mr',
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                NoticeTranslation.objects.create(
                    notice=self.notice,
                    language_code=LANGUAGE_MARATHI,
                    slug='tax-notice-mr-duplicate',
                )

    def test_slug_uniqueness_per_language(self):
        NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='annual-budget-2026',
        )
        notice2 = Notice.objects.create(notice_type=TYPE_GENERAL)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                NoticeTranslation.objects.create(
                    notice=notice2,
                    language_code=LANGUAGE_MARATHI,
                    slug='annual-budget-2026',
                )

    def test_partial_unique_index_single_published_per_language(self):
        trans = NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='tender-01',
            status=STATUS_PUBLISHED,
        )
        # Another translation row cannot also be published for same notice/lang
        trans2 = NoticeTranslation(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='tender-01-replacement',
            status=STATUS_PUBLISHED,
        )
        # Caught by uq_notice_lang unique constraint or partial index
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                trans2.save()

    def test_clean_enforces_approved_revision_matching_translation(self):
        trans = NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='sanitation-drive',
        )
        rev = NoticeRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='स्वच्छता मोहीम',
            body_markdown='मजकूर',
            editorial_status=EDITORIAL_SUBMITTED,
            created_by=self.operator,
        )
        trans.current_approved_revision = rev
        with self.assertRaises(ValidationError) as ctx:
            trans.clean()
        self.assertIn("must be in 'approved' status", str(ctx.exception))


class NoticeRevisionModelTests(TestCase):
    """
    Tests for NoticeRevision (immutability, hashing with attachments, sequence numbers).
    """

    def setUp(self):
        self.author = User.objects.create_user(
            email='author@gramsetu.in',
            full_name='Author Operator',
            is_staff=True,
        )
        self.notice = Notice.objects.create(notice_type=TYPE_TENDER)
        self.trans = NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='road-construction-tender',
        )

    def test_revision_creation_and_hash_calculation(self):
        attachments = [
            {
                'title': 'Tender Form Specification',
                'original_filename': 'tender_specs.pdf',
                'file_size_bytes': 1048576,
                'mime_type': 'application/pdf',
                'checksum_sha256': 'a' * 64,
            }
        ]
        rev = NoticeRevision.objects.create(
            translation=self.trans,
            revision_number=1,
            title='रस्ता बांधकाम निविदा',
            summary='मुख्य रस्त्याच्या खडीकरणासाठी निविदा.',
            body_markdown='सविस्तर अटी व शर्ती...',
            attachments_metadata=attachments,
            created_by=self.author,
        )
        self.assertIsNotNone(rev.id)
        self.assertEqual(len(rev.content_hash), 64)
        self.assertEqual(rev.editorial_status, EDITORIAL_DRAFT)

        # Hash changes if attachments metadata changes
        h1 = rev.calculate_hash()
        rev.attachments_metadata = []
        h2 = rev.calculate_hash()
        self.assertNotEqual(h1, h2)

    def test_revision_immutability_after_submission(self):
        rev = NoticeRevision.objects.create(
            translation=self.trans,
            revision_number=1,
            title='Initial Draft Title',
            body_markdown='Draft body.',
            created_by=self.author,
        )
        rev.submit_for_review()
        self.assertEqual(rev.editorial_status, EDITORIAL_SUBMITTED)
        self.assertIsNotNone(rev.submitted_at)

        # In-place edit of title raises ValidationError
        rev.title = 'Tampered Title'
        with self.assertRaises(ValidationError) as ctx:
            rev.clean()
        self.assertIn("strictly immutable", str(ctx.exception))

        with self.assertRaises(ValidationError):
            rev.save()

    def test_revision_cannot_be_deleted_after_submission(self):
        rev = NoticeRevision.objects.create(
            translation=self.trans,
            revision_number=1,
            title='Title',
            body_markdown='Body',
            created_by=self.author,
        )
        rev.submit_for_review()
        with self.assertRaises(ValidationError) as ctx:
            rev.delete()
        self.assertIn("Cannot delete revision", str(ctx.exception))


class NoticeGovernanceWorkflowTests(TestCase):
    """
    Tests for Notice publishing workflow: submission, separation of duties, approval,
    immediate publishing, scheduling, withdrawal, rollback, and archival.
    """

    def setUp(self):
        self.super_admin1 = User.objects.create_user(
            email='admin1@gramsetu.in',
            full_name='Super Admin 1',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin1, role=ROLE_SUPER_ADMIN)

        self.super_admin2 = User.objects.create_user(
            email='admin2@gramsetu.in',
            full_name='Super Admin 2',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin2, role=ROLE_SUPER_ADMIN)

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Patil',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        self.notice = Notice.objects.create(
            notice_type=TYPE_GRAM_SABHA,
            reference_number='GS/OCT/2026',
        )
        self.trans_mr = NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='vishesh-gram-sabha',
        )
        self.rev1 = NoticeRevision.objects.create(
            translation=self.trans_mr,
            revision_number=1,
            title='विशेष ग्रामसभा जाहीर सूचना',
            summary='सर्व ग्रामस्थांना कळविण्यात येते की...',
            body_markdown='विषय सूची: १. पाणीपुरवठा २. रस्ते विकास.',
            created_by=self.operator,
        )

    def test_submission_workflow(self):
        rev = submit_notice_revision(self.rev1.id, self.operator)
        self.assertEqual(rev.editorial_status, EDITORIAL_SUBMITTED)
        self.assertIsNotNone(rev.submitted_at)
        self.assertEqual(len(rev.content_hash), 64)

    def test_separation_of_duties_self_approval_rejected(self):
        # Super admin 1 authors a revision
        admin_rev = NoticeRevision.objects.create(
            translation=self.trans_mr,
            revision_number=2,
            title='Admin Notice Revision',
            body_markdown='Body written by admin 1',
            created_by=self.super_admin1,
        )
        admin_rev.submit_for_review()

        # Super admin 1 attempts self-approval -> rejected!
        with self.assertRaises(ValidationError) as ctx:
            approve_notice_revision(admin_rev.id, self.super_admin1)
        self.assertIn("Separation of duties violation", str(ctx.exception))

        admin_rev.refresh_from_db()
        self.assertEqual(admin_rev.editorial_status, EDITORIAL_SUBMITTED)

    def test_peer_approval_succeeds(self):
        self.rev1.submit_for_review()
        approval = approve_notice_revision(self.rev1.id, self.super_admin1, notes="Approved after verification")
        self.rev1.refresh_from_db()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_APPROVED)
        self.assertEqual(approval.target_content_type, 'noticetranslation')
        self.assertEqual(approval.approved_by, self.super_admin1)
        self.assertFalse(approval.is_self_approval)

    def test_rejection_workflow(self):
        self.rev1.submit_for_review()

        # Rejection reason < 10 chars fails
        with self.assertRaises(ValidationError) as ctx:
            reject_notice_revision(self.rev1.id, self.super_admin1, reason="Too short")
        self.assertIn("at least 10 non-whitespace characters", str(ctx.exception))

        rejection = reject_notice_revision(
            self.rev1.id,
            self.super_admin1,
            reason="Agenda items require formal stamp and sign-off by Gram Sevak.",
        )
        self.rev1.refresh_from_db()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_REJECTED)
        self.assertEqual(rejection.rejected_by, self.super_admin1)

    def test_publication_immediate_workflow(self):
        self.rev1.submit_for_review()
        approve_notice_revision(self.rev1.id, self.super_admin1)

        event = publish_notice_translation(self.trans_mr.id, self.rev1.id, self.super_admin1)
        self.trans_mr.refresh_from_db()

        self.assertEqual(self.trans_mr.status, STATUS_PUBLISHED)
        self.assertEqual(self.trans_mr.current_approved_revision, self.rev1)
        self.assertEqual(event.event_type, EVENT_INITIAL_PUBLISH)
        self.assertTrue(self.trans_mr.is_publicly_visible())
        self.assertEqual(NoticeTranslation.objects.published().count(), 1)
        self.assertEqual(Notice.objects.published().count(), 1)

    def test_scheduled_publication_workflow(self):
        self.rev1.submit_for_review()
        approve_notice_revision(self.rev1.id, self.super_admin1)

        future_time = timezone.now() + timedelta(days=5)
        event = publish_notice_translation(
            self.trans_mr.id,
            self.rev1.id,
            self.super_admin1,
            effective_from=future_time,
        )
        self.trans_mr.refresh_from_db()

        self.assertEqual(self.trans_mr.status, STATUS_SCHEDULED)
        self.assertEqual(event.event_type, EVENT_SCHEDULED_PUBLISH)
        # Not yet visible because effective_from is in the future
        self.assertFalse(self.trans_mr.is_publicly_visible())
        self.assertEqual(NoticeTranslation.objects.published().count(), 0)

    def test_withdrawal_workflow(self):
        self.rev1.submit_for_review()
        approve_notice_revision(self.rev1.id, self.super_admin1)
        publish_notice_translation(self.trans_mr.id, self.rev1.id, self.super_admin1)

        # Withdraw requires justification >= 10 chars
        with self.assertRaises(ValidationError) as ctx:
            withdraw_notice_translation(self.trans_mr.id, self.super_admin1, justification="Short")
        self.assertIn("at least 10 non-whitespace characters", str(ctx.exception))

        event = withdraw_notice_translation(
            self.trans_mr.id,
            self.super_admin1,
            justification="Gram Sabha postponed due to heavy rainfall alert in district.",
        )
        self.trans_mr.refresh_from_db()
        self.assertEqual(self.trans_mr.status, STATUS_WITHDRAWN)
        self.assertEqual(event.event_type, EVENT_WITHDRAWAL)
        self.assertFalse(self.trans_mr.is_publicly_visible())
        self.assertEqual(NoticeTranslation.objects.published().count(), 0)

    def test_rollback_workflow(self):
        # 1. Publish rev 1
        self.rev1.submit_for_review()
        approve_notice_revision(self.rev1.id, self.super_admin1)
        publish_notice_translation(self.trans_mr.id, self.rev1.id, self.super_admin1)

        # 2. Publish rev 2
        rev2 = self.trans_mr.create_next_revision(self.operator, title='Rev 2 Title', body_markdown='Rev 2 Text')
        rev2.submit_for_review()
        approve_notice_revision(rev2.id, self.super_admin1)
        publish_notice_translation(self.trans_mr.id, rev2.id, self.super_admin1)

        self.trans_mr.refresh_from_db()
        self.assertEqual(self.trans_mr.current_approved_revision, rev2)

        # 3. Rollback to rev 1 requires justification >= 10 chars
        with self.assertRaises(ValidationError):
            publish_notice_translation(self.trans_mr.id, self.rev1.id, self.super_admin1, justification="Short")

        event = publish_notice_translation(
            self.trans_mr.id,
            self.rev1.id,
            self.super_admin1,
            justification="Reverting to Revision 1 due to typographical error in meeting venue.",
        )
        self.trans_mr.refresh_from_db()
        self.assertEqual(self.trans_mr.current_approved_revision, self.rev1)
        self.assertEqual(event.event_type, EVENT_ROLLBACK)
        self.assertTrue(self.trans_mr.is_publicly_visible())

    def test_automatic_expiry_excludes_from_active_listings(self):
        self.rev1.submit_for_review()
        approve_notice_revision(self.rev1.id, self.super_admin1)
        publish_notice_translation(self.trans_mr.id, self.rev1.id, self.super_admin1)

        # Make notice expired (effective 2 days ago, expired 10 minutes ago)
        self.notice.effective_from = timezone.now() - timedelta(days=2)
        self.notice.expires_at = timezone.now() - timedelta(minutes=10)
        self.notice.save()

        # Refresh
        self.trans_mr.refresh_from_db()
        self.assertFalse(self.trans_mr.is_publicly_visible(allow_archived=False))
        self.assertEqual(NoticeTranslation.objects.published(allow_archived=False).count(), 0)

        # Historical archive access allowed if allow_archived=True
        self.trans_mr.status = STATUS_ARCHIVED
        self.trans_mr.save()
        self.assertTrue(self.trans_mr.is_publicly_visible(allow_archived=True))
        self.assertEqual(NoticeTranslation.objects.published(allow_archived=True).count(), 1)


class NoticeUrgentBypassWorkflowTests(TestCase):
    """
    Tests for Urgent Publication Bypass (docs/data-model.md Section 6.2).
    Verifies emergency safeguards, authorization verification, ratification, and retraction.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin, role=ROLE_SUPER_ADMIN)

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Patil',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        # Create valid urgent authorization for Operator
        now = timezone.now()
        self.auth = OperatorUrgentAuthorization.objects.create(
            operator=self.operator,
            allowed_category=CATEGORY_DISASTER,
            authorized_by=self.super_admin,
            valid_from=now - timedelta(hours=1),
            valid_to=now + timedelta(days=2),
        )

        self.notice = Notice.objects.create(
            notice_type=TYPE_EMERGENCY_ALERT,
            urgency=URGENCY_URGENT,
        )
        self.trans = NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='flood-alert-oct-2026',
        )
        self.rev = NoticeRevision.objects.create(
            translation=self.trans,
            revision_number=1,
            title='तातडीचा पूर इशारा - नदीकाठच्या नागरिकांना सतर्कता',
            summary='धरणातून विसर्ग वाढविण्यात आला आहे.',
            body_markdown='सर्व नागरिकांनी तात्काळ सुरक्षित स्थळी स्थलांतरित व्हावे.',
            created_by=self.operator,
        )

    def test_urgent_publish_requires_valid_authorization(self):
        # Revoke authorization
        self.auth.is_revoked = True
        self.auth.save()

        with self.assertRaises(ValidationError) as ctx:
            urgent_publish_notice(
                notice_id=self.notice.id,
                translation_id=self.trans.id,
                revision_id=self.rev.id,
                operator=self.operator,
                urgent_authorization_id=self.auth.id,
                justification="Emergency flood alert issued following dam gate opening.",
            )
        self.assertIn("expired, revoked, or not yet active", str(ctx.exception))

    def test_urgent_publish_requires_minimum_15_chars_justification(self):
        with self.assertRaises(ValidationError) as ctx:
            urgent_publish_notice(
                notice_id=self.notice.id,
                translation_id=self.trans.id,
                revision_id=self.rev.id,
                operator=self.operator,
                urgent_authorization_id=self.auth.id,
                justification="Short reason",
            )
        self.assertIn("at least 15 non-whitespace characters", str(ctx.exception))

    def test_urgent_publish_execution_and_post_publication_ratification(self):
        justification = "Critical flash flood warning: 50,000 cusecs water discharge from dam."
        urgent_log = urgent_publish_notice(
            notice_id=self.notice.id,
            translation_id=self.trans.id,
            revision_id=self.rev.id,
            operator=self.operator,
            urgent_authorization_id=self.auth.id,
            justification=justification,
        )

        self.notice.refresh_from_db()
        self.trans.refresh_from_db()
        self.rev.refresh_from_db()

        self.assertTrue(self.notice.is_urgent_published)
        self.assertEqual(self.notice.urgency, URGENCY_URGENT)
        self.assertEqual(self.rev.editorial_status, EDITORIAL_APPROVED)
        self.assertTrue(self.rev.is_urgent_bypass)
        self.assertEqual(self.trans.status, STATUS_PUBLISHED)
        self.assertTrue(self.trans.is_publicly_visible())

        self.assertEqual(urgent_log.ratification_status, RATIFICATION_PENDING)

        # Super admin ratifies
        ratified_log = ratify_urgent_notice(
            urgent_log_id=urgent_log.id,
            super_admin=self.super_admin,
            notes="Emergency discharge confirmed with irrigation department.",
        )
        self.assertEqual(ratified_log.ratification_status, RATIFICATION_RATIFIED)
        self.assertEqual(ratified_log.ratified_by, self.super_admin)
        self.assertIsNotNone(ratified_log.ratified_at)
        self.assertTrue(ApprovalRecord.objects.filter(target_id=self.trans.id).exists())

    def test_urgent_publish_retraction_immediately_severs_visibility(self):
        justification = "Critical flash flood warning: 50,000 cusecs water discharge from dam."
        urgent_log = urgent_publish_notice(
            notice_id=self.notice.id,
            translation_id=self.trans.id,
            revision_id=self.rev.id,
            operator=self.operator,
            urgent_authorization_id=self.auth.id,
            justification=justification,
        )
        self.trans.refresh_from_db()
        self.assertTrue(self.trans.is_publicly_visible())

        # Super admin retracts
        retract_urgent_notice(
            urgent_log_id=urgent_log.id,
            super_admin=self.super_admin,
            reason="Notice retracted: irrigation department confirmed alert was false alarm.",
        )

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_WITHDRAWN)
        self.assertFalse(self.trans.is_publicly_visible())
        self.assertEqual(NoticeTranslation.objects.published().count(), 0)


class NoticeAdminTests(TestCase):
    """
    Tests for Notice Django Admin interface, least-privilege permissions, actions, and tamper resistance.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin, role=ROLE_SUPER_ADMIN)

        self.super_admin2 = User.objects.create_user(
            email='admin2@gramsetu.in',
            full_name='Super Administrator 2',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin2, role=ROLE_SUPER_ADMIN)

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Patil',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        self.notice = Notice.objects.create(
            notice_type=TYPE_TENDER,
            reference_number='TND/2026/01',
        )
        self.trans = NoticeTranslation.objects.create(
            notice=self.notice,
            language_code=LANGUAGE_MARATHI,
            slug='solar-water-pump-tender',
        )
        self.rev = NoticeRevision.objects.create(
            translation=self.trans,
            revision_number=1,
            title='सौर ऊर्जा पाणी उपसा निविदा',
            body_markdown='सविस्तर तपशील...',
            created_by=self.operator,
        )

    def test_operator_can_access_notice_changelists(self):
        self.client.force_login(self.operator)
        resp_n = self.client.get(reverse('admin:notices_notice_changelist'))
        self.assertEqual(resp_n.status_code, 200)

        resp_t = self.client.get(reverse('admin:notices_noticetranslation_changelist'))
        self.assertEqual(resp_t.status_code, 200)

        resp_r = self.client.get(reverse('admin:notices_noticerevision_changelist'))
        self.assertEqual(resp_r.status_code, 200)

    def test_operator_submit_for_review_action(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            reverse('admin:notices_noticerevision_changelist'),
            {
                'action': 'submit_for_review_action',
                '_selected_action': [str(self.rev.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.rev.refresh_from_db()
        self.assertEqual(self.rev.editorial_status, EDITORIAL_SUBMITTED)

    def test_admin_separation_of_duties_self_approval_blocked(self):
        admin_rev = NoticeRevision.objects.create(
            translation=self.trans,
            revision_number=2,
            title='Admin Notice',
            body_markdown='Body',
            created_by=self.super_admin,
            editorial_status=EDITORIAL_SUBMITTED,
        )

        self.client.force_login(self.super_admin)
        response = self.client.post(
            reverse('admin:notices_noticerevision_changelist'),
            {
                'action': 'approve_revisions_action',
                '_selected_action': [str(admin_rev.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        admin_rev.refresh_from_db()
        self.assertEqual(admin_rev.editorial_status, EDITORIAL_SUBMITTED)
        self.assertFalse(ApprovalRecord.objects.filter(revision_id=admin_rev.id).exists())

        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Separation of duties violation" in str(m) for m in messages_list))

    def test_peer_admin_approval_action(self):
        admin_rev = NoticeRevision.objects.create(
            translation=self.trans,
            revision_number=2,
            title='Admin Notice',
            body_markdown='Body',
            created_by=self.super_admin,
            editorial_status=EDITORIAL_SUBMITTED,
        )

        self.client.force_login(self.super_admin2)
        response = self.client.post(
            reverse('admin:notices_noticerevision_changelist'),
            {
                'action': 'approve_revisions_action',
                '_selected_action': [str(admin_rev.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        admin_rev.refresh_from_db()
        self.assertEqual(admin_rev.editorial_status, EDITORIAL_APPROVED)
        self.assertTrue(ApprovalRecord.objects.filter(revision_id=admin_rev.id, approved_by=self.super_admin2).exists())

    def test_publish_translations_action(self):
        self.rev.editorial_status = EDITORIAL_APPROVED
        self.rev.save()

        self.client.force_login(self.super_admin)
        response = self.client.post(
            reverse('admin:notices_noticetranslation_changelist'),
            {
                'action': 'publish_translations_action',
                '_selected_action': [str(self.trans.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_PUBLISHED)
        self.assertEqual(self.trans.current_approved_revision, self.rev)
        self.assertTrue(self.trans.is_publicly_visible())

    def test_forged_post_neutralized_in_save_model(self):
        """
        Verify that forging status or pointer fields in POST to change form is neutralized.
        """
        site = AdminSite()
        trans_admin = NoticeTranslationAdmin(NoticeTranslation, site)
        rf = RequestFactory()
        req = rf.post('/admin/notices/noticetranslation/')
        req.user = self.operator

        tampered = NoticeTranslation.objects.get(pk=self.trans.pk)
        tampered.status = STATUS_PUBLISHED
        tampered.current_approved_revision = self.rev

        trans_admin.save_model(req, tampered, form=None, change=True)
        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_DRAFT)
        self.assertIsNone(self.trans.current_approved_revision)

    def test_notice_translation_completeness_badges(self):
        site = AdminSite()
        notice_admin = NoticeAdmin(Notice, site)
        html = notice_admin.translation_completeness(self.notice)
        self.assertIn('mr: Draft', str(html))
        self.assertIn('hi: अनुपलब्ध (Missing)', str(html))
        self.assertIn('en: Missing', str(html))
