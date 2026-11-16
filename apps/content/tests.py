"""
Unit and integration tests for apps.content models, constraints, and publication invariants.
"""

from datetime import timedelta
import hashlib
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.contrib.messages import get_messages
from django.contrib.admin.sites import AdminSite
from django.utils import timezone
from apps.identity.models import User, RoleAssignment, ROLE_SUPER_ADMIN, ROLE_OPERATOR
from apps.content.admin import PageAdmin, PageTranslationAdmin, PageRevisionAdmin
from apps.governance.admin import ApprovalRecordAdmin, RejectionRecordAdmin, PublicationEventAdmin
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_UPDATE_PUBLISH,
    EVENT_SCHEDULED_PUBLISH,
    EVENT_ROLLBACK,
    EVENT_WITHDRAWAL,
)
from apps.governance.services import (
    approve_page_revision,
    reject_page_revision,
    publish_page_translation,
    withdraw_page_translation,
)
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
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
)


class PageModelTests(TestCase):
    """
    Tests for Page model (canonical logical anchor).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Admin',
            is_staff=True,
        )

    def test_page_creation_and_uuidv7_pk(self):
        page = Page.objects.create(slug='about-panchayat', display_order=1)
        self.assertIsNotNone(page.id)
        self.assertEqual(len(str(page.id)), 36)
        self.assertEqual(page.slug, 'about-panchayat')
        self.assertFalse(page.is_system_page)
        self.assertEqual(str(page), "Page: about-panchayat")

    def test_system_page_cannot_be_deleted(self):
        page = Page.objects.create(slug='home', is_system_page=True)
        with self.assertRaises(ValidationError) as ctx:
            page.delete()
        self.assertIn("System pages are protected", str(ctx.exception))
        # Verify page still exists in database
        self.assertTrue(Page.objects.filter(id=page.id).exists())

    def test_non_system_page_can_be_deleted(self):
        page = Page.objects.create(slug='custom-page', is_system_page=False)
        page_id = page.id
        page.delete()
        self.assertFalse(Page.objects.filter(id=page_id).exists())

    def test_slug_uniqueness(self):
        Page.objects.create(slug='village-history')
        with self.assertRaises(IntegrityError):
            Page.objects.create(slug='village-history')


class PageTranslationModelTests(TestCase):
    """
    Tests for PageTranslation model (multilingual explicit translation entity).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Patil',
            is_staff=True,
        )
        self.page = Page.objects.create(slug='geography', display_order=5)

    def test_translation_creation_and_devanagari_slug(self):
        trans_mr = PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='भौगोलिक-माहिती',
            status=STATUS_DRAFT,
        )
        self.assertEqual(trans_mr.language_code, 'mr')
        self.assertEqual(trans_mr.localized_slug, 'भौगोलिक-माहिती')
        self.assertEqual(trans_mr.status, STATUS_DRAFT)
        self.assertIn('geography [mr]', str(trans_mr))

    def test_unique_translation_per_language_per_page(self):
        PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='भूगोल-१',
        )
        with self.assertRaises(IntegrityError):
            PageTranslation.objects.create(
                page=self.page,
                language_code=LANGUAGE_MARATHI,
                localized_slug='भूगोल-२',
            )

    def test_unique_localized_slug_per_language(self):
        page2 = Page.objects.create(slug='land-records')
        PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='जमीन-माहिती',
        )
        with self.assertRaises(IntegrityError):
            PageTranslation.objects.create(
                page=page2,
                language_code=LANGUAGE_MARATHI,
                localized_slug='जमीन-माहिती',
            )

    def test_invalid_language_code_rejected_by_db(self):
        with self.assertRaises(IntegrityError):
            PageTranslation.objects.create(
                page=self.page,
                language_code='fr',  # French not allowed
                localized_slug='geographie',
            )

    def test_clean_validates_approved_revision_belongs_to_translation(self):
        page2 = Page.objects.create(slug='page-two')
        trans1 = PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='page-one-mr',
        )
        trans2 = PageTranslation.objects.create(
            page=page2,
            language_code=LANGUAGE_MARATHI,
            localized_slug='page-two-mr',
        )
        rev_of_trans2 = PageRevision.objects.create(
            translation=trans2,
            revision_number=1,
            title='Page Two Title',
            body_markdown='Content',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.user,
        )

        trans1.current_approved_revision = rev_of_trans2
        with self.assertRaises(ValidationError) as ctx:
            trans1.clean()
        self.assertIn("must belong to this translation", str(ctx.exception))

    def test_clean_validates_approved_revision_must_be_approved(self):
        trans = PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='page-draft-rev',
        )
        draft_rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Draft Title',
            body_markdown='Draft content',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.user,
        )
        trans.current_approved_revision = draft_rev
        with self.assertRaises(ValidationError) as ctx:
            trans.clean()
        self.assertIn("must be in 'approved' status", str(ctx.exception))


class PageRevisionModelTests(TestCase):
    """
    Tests for PageRevision model, immutability, and hashing (ADR 0002).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='writer@gramsetu.in',
            full_name='Writer Kulkarni',
            is_staff=True,
        )
        self.page = Page.objects.create(slug='panchayat-history')
        self.translation = PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='इतिहास',
        )

    def test_revision_creation_and_hash_computation(self):
        rev = PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='ग्रामपंचायत इतिहास',
            summary='गावाचा संक्षिप्त इतिहास',
            body_markdown='# इतिहास\n\nआमच्या गावाची स्थापना...',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.user,
        )
        self.assertIsNotNone(rev.id)
        self.assertEqual(len(rev.content_hash), 64)
        self.assertEqual(rev.content_hash, rev.calculate_hash())
        self.assertIn('panchayat-history [rev 1]', str(rev))

    def test_draft_revision_can_be_edited(self):
        rev = PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='Original Draft',
            body_markdown='Initial notes',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.user,
        )
        rev.title = 'Updated Draft Title'
        rev.body_markdown = 'Updated content'
        rev.save()

        rev.refresh_from_db()
        self.assertEqual(rev.title, 'Updated Draft Title')
        self.assertEqual(rev.body_markdown, 'Updated content')

    def test_submitted_revision_becomes_immutable(self):
        rev = PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='Final Draft',
            body_markdown='Ready for review content',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.user,
        )
        rev.submit_for_review()
        self.assertEqual(rev.editorial_status, EDITORIAL_SUBMITTED)
        self.assertIsNotNone(rev.submitted_at)

        # Attempting in-place modification of content fields must raise ValidationError
        rev.title = 'Tampered Title'
        with self.assertRaises(ValidationError) as ctx:
            rev.save()
        self.assertIn("strictly immutable", str(ctx.exception))

        # Re-fetch from DB and confirm unchanged
        rev.refresh_from_db()
        self.assertEqual(rev.title, 'Final Draft')

    def test_approved_revision_is_immutable(self):
        rev = PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='Approved Content',
            body_markdown='Statutory verified text',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.user,
        )
        rev.body_markdown = 'Malicious alteration'
        with self.assertRaises(ValidationError) as ctx:
            rev.save()
        self.assertIn("strictly immutable", str(ctx.exception))

    def test_submitted_or_approved_revision_cannot_be_deleted(self):
        rev = PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='Official Record',
            body_markdown='Important text',
            editorial_status=EDITORIAL_SUBMITTED,
            created_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            rev.delete()
        self.assertIn("Cannot delete revision", str(ctx.exception))

    def test_draft_revision_can_be_deleted(self):
        rev = PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='Scratch Note',
            body_markdown='Draft to discard',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.user,
        )
        rev_id = rev.id
        rev.delete()
        self.assertFalse(PageRevision.objects.filter(id=rev_id).exists())

    def test_branching_new_revision_increments_sequence(self):
        rev1 = PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='Version 1',
            body_markdown='Content 1',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.user,
        )
        rev2 = self.translation.create_next_revision(
            author=self.user,
            title='Version 2 Draft',
        )
        self.assertEqual(rev2.revision_number, 2)
        self.assertEqual(rev2.editorial_status, EDITORIAL_DRAFT)
        self.assertEqual(rev2.title, 'Version 2 Draft')
        self.assertEqual(rev2.body_markdown, 'Content 1')  # Copied from rev 1

    def test_unique_revision_number_per_translation(self):
        PageRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            title='Rev 1',
            body_markdown='Text',
            created_by=self.user,
        )
        with self.assertRaises(IntegrityError):
            PageRevision.objects.create(
                translation=self.translation,
                revision_number=1,
                title='Duplicate Rev 1',
                body_markdown='Text',
                created_by=self.user,
            )


class PublicationVisibilityAndGovernanceTests(TestCase):
    """
    Tests for Publication Invariants (Section 3.3, ADR 0003), ApprovalRecord binding,
    and QuerySet visibility logic.
    """

    def setUp(self):
        self.author = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Pawar',
            is_staff=True,
        )
        self.approver = User.objects.create_user(
            email='gramsevak@gramsetu.in',
            full_name='Gram Sevak Patil',
            is_staff=True,
        )
        self.page = Page.objects.create(slug='about-panchayat', display_order=1)
        self.trans_mr = PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='ग्रामपंचायतीविषयी',
        )
        self.rev1 = PageRevision.objects.create(
            translation=self.trans_mr,
            revision_number=1,
            title='ग्रामपंचायतीविषयी',
            summary='अधिकृत माहिती',
            body_markdown='ग्रामपंचायत स्थापना १९६०...',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.author,
        )

    def test_approval_record_binding_and_hash_integrity(self):
        self.rev1.submit_for_review()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_SUBMITTED)

        # Formally approve via governance service
        approval = approve_page_revision(
            revision_id=self.rev1.id,
            approver=self.approver,
            notes="Statutory information verified.",
        )
        self.assertIsNotNone(approval.id)
        self.assertEqual(approval.revision_hash, self.rev1.content_hash)
        self.assertEqual(approval.approved_by, self.approver)
        self.assertFalse(approval.is_self_approval)

        self.rev1.refresh_from_db()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_APPROVED)

    def test_approval_detects_self_approval(self):
        # When author == approver and explicitly permitted (e.g. emergency CLI)
        self.rev1.submit_for_review()
        approval = approve_page_revision(
            revision_id=self.rev1.id,
            approver=self.author,
            notes="Self-approved urgent update",
            allow_self_approval=True,
        )
        self.assertTrue(approval.is_self_approval)

    def test_self_approval_rejected_by_default(self):
        # Enforces separation of duties by default
        self.rev1.submit_for_review()
        with self.assertRaises(ValidationError) as ctx:
            approve_page_revision(
                revision_id=self.rev1.id,
                approver=self.author,
                notes="Attempted self-approval",
            )
        self.assertIn("Separation of duties violation", str(ctx.exception))

    def test_approval_fails_on_hash_mismatch(self):
        self.rev1.submit_for_review()
        # Simulate tampering directly in DB
        PageRevision.objects.filter(id=self.rev1.id).update(content_hash='0' * 64)
        with self.assertRaises(ValidationError) as ctx:
            approve_page_revision(revision_id=self.rev1.id, approver=self.approver)
        self.assertIn("hash mismatch", str(ctx.exception))

    def test_rejection_workflow_and_mandatory_reason(self):
        self.rev1.submit_for_review()

        # Reject with short reason fails
        with self.assertRaises(ValidationError) as ctx:
            reject_page_revision(self.rev1.id, self.approver, "Too short")
        self.assertIn("at least 10 non-whitespace characters", str(ctx.exception))

        # Reject with valid reason
        rejection = reject_page_revision(
            revision_id=self.rev1.id,
            rejected_by=self.approver,
            reason="Please provide the correct Census 2011 population figures.",
        )
        self.assertIsNotNone(rejection.id)
        self.rev1.refresh_from_db()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_REJECTED)

    def test_canonical_7_publication_invariants(self):
        """
        Tests the 7 publication conditions in docs/data-model.md Section 3.3:
        1. Root Page exists
        2. Translation exists for requested language
        3. current_approved_revision exists and is approved
        4. Status allows visibility
        5. Effective start time reached
        6. Unexpired window
        7. No active withdrawal
        """
        # Initially, translation is draft, no approved revision -> NOT visible
        self.assertFalse(self.trans_mr.is_publicly_visible())
        self.assertEqual(PageTranslation.objects.published().count(), 0)

        # Submit and approve rev1
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.approver)
        self.rev1.refresh_from_db()

        # Still not visible before publication event!
        self.assertFalse(self.trans_mr.is_publicly_visible())

        # Publish immediately
        event = publish_page_translation(
            translation_id=self.trans_mr.id,
            revision_id=self.rev1.id,
            actor=self.approver,
        )
        self.trans_mr.refresh_from_db()
        self.assertEqual(self.trans_mr.status, STATUS_PUBLISHED)
        self.assertEqual(self.trans_mr.current_approved_revision, self.rev1)
        self.assertTrue(self.trans_mr.is_publicly_visible())
        self.assertEqual(PageTranslation.objects.published().count(), 1)
        self.assertEqual(Page.objects.published(language_code=LANGUAGE_MARATHI).count(), 1)

        # Missing English translation is NOT returned (Explicit Translation pattern)
        self.assertEqual(Page.objects.published(language_code=LANGUAGE_ENGLISH).count(), 0)

    def test_scheduled_publication_activates_after_effective_time(self):
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.approver)
        self.rev1.refresh_from_db()

        # Schedule for future: 2 hours from now
        future_time = timezone.now() + timedelta(hours=2)
        publish_page_translation(
            translation_id=self.trans_mr.id,
            revision_id=self.rev1.id,
            actor=self.approver,
            effective_from=future_time,
        )
        self.trans_mr.refresh_from_db()
        self.assertEqual(self.trans_mr.status, STATUS_SCHEDULED)

        # Before effective time: NOT visible
        self.assertFalse(self.trans_mr.is_publicly_visible())
        self.assertEqual(PageTranslation.objects.published().count(), 0)

        # Simulate time passing beyond effective_from in PublicationEvent
        past_time = timezone.now() - timedelta(minutes=5)
        PublicationEvent.objects.filter(id=self.trans_mr.current_publication_event_id).update(
            effective_from=past_time
        )
        self.trans_mr.refresh_from_db()

        # Declarative query-time fallback: visible even if worker has not updated status enum!
        self.assertTrue(self.trans_mr.is_publicly_visible())
        self.assertEqual(PageTranslation.objects.published().count(), 1)

    def test_withdrawal_immediately_severs_visibility(self):
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.approver)
        self.rev1.refresh_from_db()

        publish_page_translation(
            translation_id=self.trans_mr.id,
            revision_id=self.rev1.id,
            actor=self.approver,
        )
        self.trans_mr.refresh_from_db()
        self.assertTrue(self.trans_mr.is_publicly_visible())

        # Withdraw
        withdraw_page_translation(
            translation_id=self.trans_mr.id,
            actor=self.approver,
            justification="Factual correction required due to typographical error.",
        )
        self.trans_mr.refresh_from_db()
        self.assertEqual(self.trans_mr.status, STATUS_WITHDRAWN)
        self.assertFalse(self.trans_mr.is_publicly_visible())
        self.assertEqual(PageTranslation.objects.published().count(), 0)

    def test_rollback_reinstates_previous_revision_with_audit_trail(self):
        # 1. Publish rev 1
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.approver)
        self.rev1.refresh_from_db()
        publish_page_translation(self.trans_mr.id, self.rev1.id, self.approver)

        # 2. Create, submit, approve, and publish rev 2
        rev2 = self.trans_mr.create_next_revision(self.author, title='Title Rev 2', body_markdown='Text Rev 2')
        rev2.submit_for_review()
        approve_page_revision(rev2.id, self.approver)
        rev2.refresh_from_db()
        publish_page_translation(self.trans_mr.id, rev2.id, self.approver)

        self.trans_mr.refresh_from_db()
        self.assertEqual(self.trans_mr.current_approved_revision, rev2)

        # 3. Rollback to rev 1 requires justification >= 10 chars
        with self.assertRaises(ValidationError) as ctx:
            publish_page_translation(
                self.trans_mr.id,
                self.rev1.id,
                self.approver,
                justification="short",
            )
        self.assertIn("at least 10 characters", str(ctx.exception))

        event = publish_page_translation(
            self.trans_mr.id,
            self.rev1.id,
            self.approver,
            justification="Rollback to Revision 1 due to disputed boundary claims in Rev 2.",
        )
        self.trans_mr.refresh_from_db()
        self.assertEqual(event.event_type, EVENT_ROLLBACK)
        self.assertEqual(self.trans_mr.current_approved_revision, self.rev1)
        self.assertTrue(self.trans_mr.is_publicly_visible())

        # Verify historical events are preserved (3 events: initial, update, rollback)
        events = PublicationEvent.objects.filter(target_id=self.trans_mr.id).order_by('created_at')
        self.assertEqual(events.count(), 3)
        self.assertEqual(events[0].event_type, EVENT_INITIAL_PUBLISH)
        self.assertEqual(events[1].event_type, EVENT_UPDATE_PUBLISH)
        self.assertEqual(events[2].event_type, EVENT_ROLLBACK)


class AdminAccessControlTests(TestCase):
    """
    Tests for Django Admin access control and least-privilege role boundaries.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='superadmin@gramsetu.in',
            full_name='Super Administrator',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin, role=ROLE_SUPER_ADMIN)

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Patil',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        self.citizen = User.objects.create_user(
            email='citizen@gramsetu.in',
            full_name='Citizen User',
            password='TestPassword123!',
            is_staff=False,
        )

        self.page = Page.objects.create(slug='about-gram-panchayat', display_order=1)

    def test_anonymous_user_redirected_to_admin_login(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_non_staff_user_denied_admin_access(self):
        self.client.force_login(self.citizen)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_operator_can_access_content_changelists(self):
        self.client.force_login(self.operator)
        resp_page = self.client.get(reverse('admin:content_page_changelist'))
        self.assertEqual(resp_page.status_code, 200)

        resp_trans = self.client.get(reverse('admin:content_pagetranslation_changelist'))
        self.assertEqual(resp_trans.status_code, 200)

        resp_rev = self.client.get(reverse('admin:content_pagerevision_changelist'))
        self.assertEqual(resp_rev.status_code, 200)

    def test_operator_denied_permission_on_identity_models(self):
        from apps.identity.admin import UserAdmin, RoleAssignmentAdmin
        site = AdminSite()
        user_admin = UserAdmin(User, site)
        role_admin = RoleAssignmentAdmin(RoleAssignment, site)

        rf = RequestFactory()
        req = rf.get('/admin/')
        req.user = self.operator

        self.assertFalse(user_admin.has_add_permission(req))
        self.assertFalse(user_admin.has_change_permission(req))
        self.assertFalse(user_admin.has_delete_permission(req))
        self.assertFalse(role_admin.has_add_permission(req))
        self.assertFalse(role_admin.has_change_permission(req))
        self.assertFalse(role_admin.has_delete_permission(req))

    def test_operator_cannot_delete_pages(self):
        site = AdminSite()
        page_admin = PageAdmin(Page, site)
        rf = RequestFactory()
        req = rf.get('/admin/')
        req.user = self.operator

        self.assertFalse(page_admin.has_delete_permission(req, self.page))

        self.client.force_login(self.operator)
        response = self.client.post(reverse('admin:content_page_delete', args=[self.page.pk]), {'post': 'yes'})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Page.objects.filter(id=self.page.id).exists())

    def test_governance_models_are_strictly_read_only_in_admin(self):
        site = AdminSite()
        approval_admin = ApprovalRecordAdmin(ApprovalRecord, site)
        rejection_admin = RejectionRecordAdmin(RejectionRecord, site)
        event_admin = PublicationEventAdmin(PublicationEvent, site)

        rf = RequestFactory()
        req = rf.get('/admin/')
        req.user = self.super_admin

        # Even Super Administrator cannot add, edit, or delete governance records
        for model_admin in (approval_admin, rejection_admin, event_admin):
            self.assertFalse(model_admin.has_add_permission(req))
            self.assertFalse(model_admin.has_change_permission(req))
            self.assertFalse(model_admin.has_delete_permission(req))

        self.client.force_login(self.super_admin)
        resp_add = self.client.get(reverse('admin:governance_approvalrecord_add'))
        self.assertEqual(resp_add.status_code, 403)

        resp_rej_add = self.client.get(reverse('admin:governance_rejectionrecord_add'))
        self.assertEqual(resp_rej_add.status_code, 403)

        resp_ev_add = self.client.get(reverse('admin:governance_publicationevent_add'))
        self.assertEqual(resp_ev_add.status_code, 403)


class AdminGovernanceWorkflowTests(TestCase):
    """
    Tests for end-to-end governance lifecycle actions executed via Django Admin.
    """

    def setUp(self):
        self.super_admin1 = User.objects.create_user(
            email='admin1@gramsetu.in',
            full_name='Super Administrator 1',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin1, role=ROLE_SUPER_ADMIN)

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

        self.page = Page.objects.create(slug='panchayat-schemes', display_order=1)
        self.trans = PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='yojana',
        )
        self.rev1 = PageRevision.objects.create(
            translation=self.trans,
            revision_number=1,
            title='ग्रामपंचायत योजना',
            body_markdown='विविध योजनांची माहिती.',
            created_by=self.operator,
        )

    def test_operator_submits_revision_for_review_action(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'submit_for_review_action',
                '_selected_action': [str(self.rev1.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.rev1.refresh_from_db()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_SUBMITTED)
        self.assertIsNotNone(self.rev1.submitted_at)

    def test_separation_of_duties_self_approval_blocked_in_admin(self):
        # Super admin 1 authors a revision
        admin_rev = PageRevision.objects.create(
            translation=self.trans,
            revision_number=2,
            title='Admin Proposed Revision',
            body_markdown='Content written by superadmin 1',
            created_by=self.super_admin1,
            editorial_status=EDITORIAL_SUBMITTED,
        )

        self.client.force_login(self.super_admin1)
        response = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'approve_revisions_action',
                '_selected_action': [str(admin_rev.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Verify separation of duties prevented self-approval
        admin_rev.refresh_from_db()
        self.assertEqual(admin_rev.editorial_status, EDITORIAL_SUBMITTED)
        self.assertFalse(ApprovalRecord.objects.filter(revision_id=admin_rev.id).exists())

        # Verify error message was presented
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Separation of duties violation" in str(m) for m in messages_list))

    def test_peer_super_admin_approves_revision_action(self):
        admin_rev = PageRevision.objects.create(
            translation=self.trans,
            revision_number=2,
            title='Admin Proposed Revision',
            body_markdown='Content written by superadmin 1',
            created_by=self.super_admin1,
            editorial_status=EDITORIAL_SUBMITTED,
        )

        # Different super admin approves
        self.client.force_login(self.super_admin2)
        response = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'approve_revisions_action',
                '_selected_action': [str(admin_rev.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        admin_rev.refresh_from_db()
        self.assertEqual(admin_rev.editorial_status, EDITORIAL_APPROVED)
        approval = ApprovalRecord.objects.filter(revision_id=admin_rev.id).first()
        self.assertIsNotNone(approval)
        self.assertEqual(approval.approved_by, self.super_admin2)
        self.assertFalse(approval.is_self_approval)

    def test_reject_revision_action_validation_and_execution(self):
        self.rev1.submit_for_review()
        self.rev1.refresh_from_db()

        self.client.force_login(self.super_admin1)

        # 1. Initial POST renders intermediate form
        resp_inter = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'reject_revisions_action',
                '_selected_action': [str(self.rev1.id)],
            },
        )
        self.assertEqual(resp_inter.status_code, 200)
        self.assertContains(resp_inter, 'Reject Submitted Revisions')

        # 2. Short justification (< 10 chars) fails and re-renders form
        resp_short = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'reject_revisions_action',
                '_selected_action': [str(self.rev1.id)],
                'rejection_reason': 'Too short',
                'apply': '1',
            },
        )
        self.assertEqual(resp_short.status_code, 200)
        self.assertContains(resp_short, 'at least 10 non-whitespace characters')
        self.rev1.refresh_from_db()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_SUBMITTED)

        # 3. Valid justification executes rejection
        resp_valid = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'reject_revisions_action',
                '_selected_action': [str(self.rev1.id)],
                'rejection_reason': 'Information requires official verification from Gram Panchayat secretary.',
                'apply': '1',
            },
            follow=True,
        )
        self.assertEqual(resp_valid.status_code, 200)
        self.rev1.refresh_from_db()
        self.assertEqual(self.rev1.editorial_status, EDITORIAL_REJECTED)
        self.assertTrue(RejectionRecord.objects.filter(revision_id=self.rev1.id, rejected_by=self.super_admin1).exists())

    def test_publish_translations_action_immediate(self):
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.super_admin1)
        self.rev1.refresh_from_db()

        self.client.force_login(self.super_admin1)
        response = self.client.post(
            reverse('admin:content_pagetranslation_changelist'),
            {
                'action': 'publish_translations_action',
                '_selected_action': [str(self.trans.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_PUBLISHED)
        self.assertEqual(self.trans.current_approved_revision, self.rev1)
        self.assertTrue(self.trans.is_publicly_visible())
        self.assertTrue(
            PublicationEvent.objects.filter(
                target_id=self.trans.id,
                event_type=EVENT_INITIAL_PUBLISH,
                actor=self.super_admin1,
            ).exists()
        )

    def test_schedule_translations_action(self):
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.super_admin1)
        self.rev1.refresh_from_db()

        self.client.force_login(self.super_admin1)

        # 1. Past datetime rejected
        resp_past = self.client.post(
            reverse('admin:content_pagetranslation_changelist'),
            {
                'action': 'schedule_translations_action',
                '_selected_action': [str(self.trans.id)],
                'effective_from': '2020-01-01T10:00',
                'apply': '1',
            },
        )
        self.assertEqual(resp_past.status_code, 200)
        self.assertContains(resp_past, 'must be in the future')

        # 2. Future datetime succeeds
        future_dt = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')
        resp_future = self.client.post(
            reverse('admin:content_pagetranslation_changelist'),
            {
                'action': 'schedule_translations_action',
                '_selected_action': [str(self.trans.id)],
                'effective_from': future_dt,
                'apply': '1',
            },
            follow=True,
        )
        self.assertEqual(resp_future.status_code, 200)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_SCHEDULED)
        self.assertIsNotNone(self.trans.current_publication_event)
        self.assertIsNotNone(self.trans.current_publication_event.scheduled_for)

    def test_withdraw_translations_action(self):
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.super_admin1)
        publish_page_translation(self.trans.id, self.rev1.id, self.super_admin1)
        self.trans.refresh_from_db()
        self.assertTrue(self.trans.is_publicly_visible())

        self.client.force_login(self.super_admin1)

        # 1. Short justification rejected
        resp_short = self.client.post(
            reverse('admin:content_pagetranslation_changelist'),
            {
                'action': 'withdraw_translations_action',
                '_selected_action': [str(self.trans.id)],
                'justification': 'Withdraw',
                'apply': '1',
            },
        )
        self.assertEqual(resp_short.status_code, 200)
        self.assertContains(resp_short, 'at least 10 non-whitespace characters')

        # 2. Valid justification succeeds
        resp_valid = self.client.post(
            reverse('admin:content_pagetranslation_changelist'),
            {
                'action': 'withdraw_translations_action',
                '_selected_action': [str(self.trans.id)],
                'justification': 'Emergency withdrawal ordered by Gram Panchayat administrator.',
                'apply': '1',
            },
            follow=True,
        )
        self.assertEqual(resp_valid.status_code, 200)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_WITHDRAWN)
        self.assertFalse(self.trans.is_publicly_visible())
        self.assertTrue(
            PublicationEvent.objects.filter(
                target_id=self.trans.id,
                event_type=EVENT_WITHDRAWAL,
                actor=self.super_admin1,
            ).exists()
        )

    def test_rollback_to_this_revision_action(self):
        # 1. Publish rev 1
        self.rev1.submit_for_review()
        approve_page_revision(self.rev1.id, self.super_admin1)
        publish_page_translation(self.trans.id, self.rev1.id, self.super_admin1)

        # 2. Create, submit, approve, and publish rev 2
        rev2 = self.trans.create_next_revision(self.operator, title='Rev 2 Title', body_markdown='Rev 2 Text')
        rev2.submit_for_review()
        approve_page_revision(rev2.id, self.super_admin1)
        publish_page_translation(self.trans.id, rev2.id, self.super_admin1)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.current_approved_revision, rev2)

        # 3. Rollback to rev 1 via admin action
        self.client.force_login(self.super_admin1)
        response = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'rollback_to_this_revision_action',
                '_selected_action': [str(self.rev1.id)],
                'justification': 'Rollback to Revision 1 due to inaccuracies identified in Revision 2.',
                'apply': '1',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.current_approved_revision, self.rev1)
        self.assertTrue(
            PublicationEvent.objects.filter(
                target_id=self.trans.id,
                event_type=EVENT_ROLLBACK,
                actor=self.super_admin1,
            ).exists()
        )

    def test_create_next_revision_action(self):
        self.client.force_login(self.operator)
        response = self.client.post(
            reverse('admin:content_pagetranslation_changelist'),
            {
                'action': 'create_next_revision_action',
                '_selected_action': [str(self.trans.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        new_rev = self.trans.revisions.order_by('-revision_number').first()
        self.assertEqual(new_rev.revision_number, 2)
        self.assertEqual(new_rev.editorial_status, EDITORIAL_DRAFT)
        self.assertEqual(new_rev.created_by, self.operator)


class AdminIntegrityAndTamperResistanceTests(TestCase):
    """
    Tests for server-side tamper resistance, immutability, and data integrity in Django Admin.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.super_admin, role=ROLE_SUPER_ADMIN)

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Operator Patil',
            password='TestPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        self.page = Page.objects.create(slug='governance-portal', display_order=1)
        self.trans = PageTranslation.objects.create(
            page=self.page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='shasan-portal',
        )
        self.rev = PageRevision.objects.create(
            translation=self.trans,
            revision_number=1,
            title='प्रशासन माहिती',
            body_markdown='मजकूर',
            created_by=self.operator,
        )

    def test_forged_post_cannot_alter_translation_status_or_pointers(self):
        """
        Direct POST to translation change form cannot bypass workflow by setting status or pointers.
        """
        self.assertEqual(self.trans.status, STATUS_DRAFT)
        self.assertIsNone(self.trans.current_approved_revision)

        site = AdminSite()
        trans_admin = PageTranslationAdmin(PageTranslation, site)

        rf = RequestFactory()
        req = rf.post('/admin/content/pagetranslation/')
        req.user = self.operator

        # Simulate forged model instance submitted via form
        tampered_trans = PageTranslation.objects.get(pk=self.trans.pk)
        tampered_trans.status = STATUS_PUBLISHED
        tampered_trans.current_approved_revision = self.rev

        trans_admin.save_model(req, tampered_trans, form=None, change=True)

        # Verify that save_model reset the status and pointers to database original
        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_DRAFT)
        self.assertIsNone(self.trans.current_approved_revision)

    def test_revision_immutability_enforced_in_admin(self):
        """
        Once submitted or approved, revisions cannot be modified via admin.
        """
        self.rev.editorial_status = EDITORIAL_SUBMITTED
        self.rev.save()

        site = AdminSite()
        rev_admin = PageRevisionAdmin(PageRevision, site)

        rf = RequestFactory()
        req = rf.get('/admin/content/pagerevision/')
        req.user = self.operator

        # Change permission is denied for non-draft revisions
        self.assertFalse(rev_admin.has_change_permission(req, self.rev))

        # Read-only fields include all content fields
        readonly_fields = rev_admin.get_readonly_fields(req, self.rev)
        for f in ('translation', 'revision_number', 'title', 'summary', 'body_markdown', 'editorial_status'):
            self.assertIn(f, readonly_fields)

        # Direct invocation of save_model on submitted revision raises ValidationError
        with self.assertRaises(ValidationError) as ctx:
            rev_admin.save_model(req, self.rev, form=None, change=True)
        self.assertIn("Submitted and reviewed revisions are strictly immutable", str(ctx.exception))

    def test_hash_tampering_detection_blocks_approval_in_admin(self):
        """
        If revision body is tampered behind the scenes, approval action detects hash mismatch and aborts.
        """
        self.rev.submit_for_review()
        self.rev.refresh_from_db()

        # Simulate database tamper: update body_markdown without updating content_hash
        PageRevision.objects.filter(id=self.rev.id).update(body_markdown='Tampered content behind the scenes')

        self.client.force_login(self.super_admin)
        response = self.client.post(
            reverse('admin:content_pagerevision_changelist'),
            {
                'action': 'approve_revisions_action',
                '_selected_action': [str(self.rev.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Revision remains submitted, no approval record created
        self.rev.refresh_from_db()
        self.assertEqual(self.rev.editorial_status, EDITORIAL_SUBMITTED)
        self.assertFalse(ApprovalRecord.objects.filter(revision_id=self.rev.id).exists())

        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Revision hash mismatch" in str(m) for m in messages_list))

    def test_system_page_cannot_be_deleted_via_admin(self):
        system_page = Page.objects.create(slug='home', is_system_page=True)

        site = AdminSite()
        page_admin = PageAdmin(Page, site)

        rf = RequestFactory()
        req = rf.get('/admin/content/page/')
        req.user = self.super_admin

        # Admin delete permission returns False for system page
        self.assertFalse(page_admin.has_delete_permission(req, system_page))

        self.client.force_login(self.super_admin)
        response = self.client.post(
            reverse('admin:content_page_delete', args=[system_page.pk]),
            {'post': 'yes'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Page.objects.filter(id=system_page.id).exists())

    def test_page_admin_displays_translation_completeness_badges(self):
        # Page with only Marathi translation
        page = Page.objects.create(slug='citizen-charter', display_order=10)
        PageTranslation.objects.create(
            page=page,
            language_code=LANGUAGE_MARATHI,
            localized_slug='nagarik-sanad',
        )

        site = AdminSite()
        page_admin = PageAdmin(Page, site)
        html = page_admin.translation_completeness(page)

        self.assertIn('mr: Draft', str(html))
        self.assertIn('hi: अनुपलब्ध (Missing)', str(html))
        self.assertIn('en: Missing', str(html))


class ContentDeliveryBugFixRegressionTests(TestCase):
    """
    Regression tests for Issue 1: Public Information page main content visibility and fallback.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.super_admin,
            role=ROLE_SUPER_ADMIN,
        )

    def test_page_list_api_returns_body_markdown_and_supports_fallback(self):
        page = Page.objects.create(slug='village-profile', display_order=1)
        trans = PageTranslation.objects.create(
            page=page,
            language_code='en',
            localized_slug='village-profile',
            status='published',
        )
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Village Profile',
            summary='Brief village summary',
            body_markdown='# Heading\n\nFull village information paragraph.\n\nSecond paragraph of details.',
            editorial_status='approved',
            created_by=self.super_admin,
        )
        trans.current_approved_revision = rev
        trans.save()

        # 1. English request returns full body_markdown
        resp_en = self.client.get('/api/content/pages/?lang=en')
        self.assertEqual(resp_en.status_code, 200)
        data_en = resp_en.json()
        self.assertEqual(data_en['count'], 1)
        self.assertIn('Full village information', data_en['results'][0]['body_markdown'])
        self.assertIn('Second paragraph of details', data_en['results'][0]['body_markdown'])
        self.assertEqual(data_en['results'][0]['summary'], 'Brief village summary')
        self.assertFalse(data_en['results'][0]['is_fallback'])

        # 2. Marathi request with fallback=1 gracefully returns the record with fallback flag
        resp_mr = self.client.get('/api/content/pages/?lang=mr&fallback=1')
        self.assertEqual(resp_mr.status_code, 200)
        data_mr = resp_mr.json()
        self.assertEqual(data_mr['count'], 1)
        self.assertTrue(data_mr['results'][0]['is_fallback'])
        self.assertIn('Full village information', data_mr['results'][0]['body_markdown'])

        # 3. Marathi request with fallback=0 returns empty list (strict language isolation preserved)
        resp_strict = self.client.get('/api/content/pages/?lang=mr&fallback=0')
        self.assertEqual(resp_strict.status_code, 200)
        self.assertEqual(resp_strict.json()['count'], 0)

        # 4. Unapproved draft revisions do NOT leak
        rev2 = PageRevision.objects.create(
            translation=trans,
            revision_number=2,
            title='Leaked Draft',
            summary='Draft summary',
            body_markdown='Secret unapproved draft content',
            editorial_status='draft',
            created_by=self.super_admin,
        )
        resp_after_draft = self.client.get('/api/content/pages/?lang=en')
        self.assertNotIn('Secret unapproved draft content', resp_after_draft.json()['results'][0]['body_markdown'])
        self.assertEqual(resp_after_draft.json()['results'][0]['title'], 'Village Profile')


