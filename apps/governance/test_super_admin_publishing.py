"""
Comprehensive tests for Super Administrator Direct Publishing and Governance Authority.

Verifies:
1. Super Admin direct publish of new content (via `publish_now: true`).
2. Direct publish of existing draft without intermediate review.
3. Non-pending review state (Super Admin can directly approve/publish drafts).
4. Operator 403 on direct publish and privileged actions.
5. Operator blocked on self-approval (separation of duties).
6. Unauthorized requests rejected (401 unauthenticated, 403 unauthorized citizen).
7. Public route availability immediately upon direct publication.
8. Idempotency on duplicate publication requests without duplicate records.
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.identity.models import (
    User,
    RoleAssignment,
    ROLE_SUPER_ADMIN,
    ROLE_OPERATOR,
)
from apps.governance.models import (
    ApprovalRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
)
from apps.governance import services as gov_services
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_APPROVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
)
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    STATUS_PUBLISHED as EVENT_STATUS_PUBLISHED,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    DISCLOSURE_APPROVED,
)
from apps.documents.storage import save_private_document
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError


class SuperAdminPublishingAuthorityTests(TestCase):
    """
    Test suite for Super Administrator direct publishing authority,
    role-based approval policies, and separation of duties enforcement.
    """

    def setUp(self):
        # 1. Super Administrator (Gram Sevak)
        self.super_admin = User.objects.create_user(
            email='gram.sevak@gramsetu.gov.in',
            full_name='Gram Sevak Patil',
            password='AdminPassword123!',
        )
        RoleAssignment.objects.create(user=self.super_admin, role=ROLE_SUPER_ADMIN)

        # 2. Operator (Computer Operator)
        self.operator = User.objects.create_user(
            email='operator@gramsetu.gov.in',
            full_name='Computer Operator Kadam',
            password='OperatorPassword123!',
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        # 3. Citizen (Non-admin)
        self.citizen = User.objects.create_user(
            email='citizen.user@example.com',
            full_name='Citizen User',
            password='CitizenPassword123!',
        )

        # 4. Verified Clients
        self.admin_client = self._create_mfa_client(self.super_admin)
        self.operator_client = self._create_mfa_client(self.operator)
        self.citizen_client = self._create_mfa_client(self.citizen)

    def _create_mfa_client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session['mfa_verified'] = True
        session.save()
        return client

    # ==========================================================================
    # 1. Super Admin Direct Publish on Creation (publish_now: True)
    # ==========================================================================

    def test_01_super_admin_direct_publish_notice(self):
        """Super Admin creates a Notice with publish_now: true -> immediately approved & published."""
        payload = {
            'title': 'तात्काळ सार्वजनिक सूचना',
            'description': 'ग्रामपंचायतीची विशेष जाहीर नोटीस तपशील.',
            'notice_type': 'general',
            'urgency': 'routine',
            'reference_number': 'NOT-2026-001',
            'language_code': 'mr',
            'publish_now': True,
        }
        resp = self.admin_client.post(
            reverse('api:cms:notices_collection'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_published'])
        self.assertEqual(data['status'], 'published')
        self.assertEqual(data['editorial_status'], EDITORIAL_APPROVED)

        # Verify database state
        notice_id = data['notice_id']
        trans = NoticeTranslation.objects.get(id=data['translation_id'])
        self.assertEqual(trans.status, 'published')
        self.assertIsNotNone(trans.current_approved_revision_id)
        self.assertEqual(trans.current_approved_revision.editorial_status, EDITORIAL_APPROVED)

        # Verify ApprovalRecord and PublicationEvent
        approval = ApprovalRecord.objects.filter(target_id=trans.id).first()
        self.assertIsNotNone(approval)
        self.assertEqual(approval.approved_by, self.super_admin)
        self.assertTrue(approval.is_self_approval)

        pub_event = PublicationEvent.objects.filter(target_id=trans.id).first()
        self.assertIsNotNone(pub_event)
        self.assertEqual(pub_event.actor, self.super_admin)

    def test_01b_super_admin_direct_publish_event(self):
        """Super Admin creates an Event with publish_now: true -> immediately published."""
        now = timezone.now()
        payload = {
            'title': 'विशेष ग्रामसभा बैठक',
            'event_type': 'gram_sabha',
            'start_datetime': (now + timedelta(days=2)).isoformat(),
            'end_datetime': (now + timedelta(days=2, hours=3)).isoformat(),
            'venue_mr': 'ग्रामपंचायत मुख्य सभागृह',
            'description': 'वार्षिक विकास आराखडा मंजुरी.',
            'agenda': '१. विकास कामे २. अंदाजपत्रक',
            'language_code': 'mr',
            'publish_now': True,
        }
        resp = self.admin_client.post(
            reverse('api:cms:events_collection'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_published'])
        self.assertEqual(data['status'], EVENT_STATUS_PUBLISHED)

        ev = PanchayatEvent.objects.get(id=data['event_id'])
        self.assertTrue(ev.is_published)
        self.assertEqual(ev.status, EVENT_STATUS_PUBLISHED)

    def test_01c_super_admin_direct_publish_scheme(self):
        """Super Admin creates a Scheme with publish_now: true -> immediately approved & published."""
        payload = {
            'slug': 'super-admin-scheme',
            'title': 'शेततळे अनुदान योजना',
            'scheme_level': 'state',
            'target_beneficiary': 'farmers',
            'short_summary': 'शेततळ्यासाठी थेट अनुदान.',
            'benefits': '७५ हजार रुपये आर्थिक मदत',
            'eligibility_criteria': 'अल्पभूधारक शेतकरी',
            'language_code': 'mr',
            'publish_now': True,
        }
        resp = self.admin_client.post(
            reverse('api:cms:schemes_collection'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_published'])
        self.assertEqual(data['status'], 'published')

        trans = SchemeTranslation.objects.get(id=data['translation_id'])
        self.assertEqual(trans.status, 'published')
        self.assertEqual(trans.current_approved_revision.editorial_status, EDITORIAL_APPROVED)

    def test_01d_super_admin_direct_publish_page(self):
        """Super Admin creates a Page with publish_now: true -> immediately approved & published."""
        payload = {
            'slug': 'test-water-heritage',
            'title': 'जल संवर्धन इतिहास',
            'summary': 'गावातील जल संवर्धन प्रकल्प.',
            'body_markdown': '# जल संवर्धन प्रकल्प\n\nसविस्तर माहिती.',
            'language_code': 'mr',
            'publish_now': True,
        }
        resp = self.admin_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_published'])
        self.assertEqual(data['status'], 'published')

        trans = PageTranslation.objects.get(id=data['translation_id'])
        self.assertEqual(trans.status, 'published')

    # ==========================================================================
    # 2. Direct Publish of Existing Draft Without Intermediate Review
    # ==========================================================================

    def test_02_super_admin_direct_publish_existing_draft(self):
        """Super Admin directly publishes an existing draft Page without intermediate review submission."""
        # Create a draft page
        page = Page.objects.create(slug='draft-heritage-page', display_order=1)
        trans = PageTranslation.objects.create(
            page=page,
            language_code='mr',
            localized_slug='draft-heritage-page-mr',
            status=STATUS_DRAFT,
        )
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='वारसा स्थळे',
            summary='गावाचा ऐतिहासिक वारसा.',
            body_markdown='वारसा स्थळांची संपूर्ण माहिती.',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.super_admin,
        )

        # Super Admin calls publish action directly via governance endpoint
        payload = {
            'entity_type': 'page',
            'action': 'publish',
            'target_id': str(trans.id),
            'revision_id': str(rev.id),
            'justification': 'Direct publish of administrative content by Super Administrator',
        }
        resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])

        # Verify DB state
        trans.refresh_from_db()
        rev.refresh_from_db()
        self.assertEqual(trans.status, STATUS_PUBLISHED)
        self.assertEqual(rev.editorial_status, EDITORIAL_APPROVED)
        self.assertEqual(trans.current_approved_revision_id, rev.id)

    # ==========================================================================
    # 3. Non-Pending Review State (Draft Directly Approved by Super Admin)
    # ==========================================================================

    def test_03_super_admin_can_approve_draft_directly(self):
        """Super Admin can approve a revision directly in 'draft' status without requiring 'submitted' status."""
        notice = Notice.objects.create(reference_number='DRAFT-APP-001')
        trans = NoticeTranslation.objects.create(
            notice=notice,
            language_code='mr',
            slug='draft-notice-slug',
            status=STATUS_DRAFT,
        )
        rev = NoticeRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='मसुदा नोटीस',
            summary='मसुदा नोटीस सारांश.',
            body_markdown='मसुदा नोटीस तपशील.',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.super_admin,
        )

        # Super Admin calls approve action directly
        payload = {
            'entity_type': 'notice',
            'action': 'approve',
            'target_id': str(trans.id),
            'revision_id': str(rev.id),
            'notes': 'Direct approval by Super Administrator',
        }
        resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])

        rev.refresh_from_db()
        self.assertEqual(rev.editorial_status, EDITORIAL_APPROVED)

    # ==========================================================================
    # 4. Operator 403 on Direct Publish and Privileged Actions
    # ==========================================================================

    def test_04_operator_rejected_on_publish_now(self):
        """Operator attempting publish_now: true on notice/event/scheme receives HTTP 403."""
        # 1. Notice
        payload_notice = {
            'title': 'ऑपरेटर अनाधिकृत नोटीस',
            'description': 'चाचणी नोटीस.',
            'publish_now': True,
        }
        resp_notice = self.operator_client.post(
            reverse('api:cms:notices_collection'),
            data=json.dumps(payload_notice),
            content_type='application/json',
        )
        self.assertEqual(resp_notice.status_code, 403)
        self.assertIn('Super Administrator', resp_notice.json()['detail'])

        # 2. Event
        now = timezone.now()
        payload_event = {
            'title': 'ऑपरेटर अनाधिकृत सभा',
            'event_type': 'gram_sabha',
            'start_datetime': (now + timedelta(days=1)).isoformat(),
            'end_datetime': (now + timedelta(days=1, hours=2)).isoformat(),
            'venue_mr': 'सभागृह',
            'publish_now': True,
        }
        resp_event = self.operator_client.post(
            reverse('api:cms:events_collection'),
            data=json.dumps(payload_event),
            content_type='application/json',
        )
        self.assertEqual(resp_event.status_code, 403)

        # 3. Scheme
        payload_scheme = {
            'slug': 'op-unauth-scheme',
            'title': 'ऑपरेटर अनाधिकृत योजना',
            'publish_now': True,
        }
        resp_scheme = self.operator_client.post(
            reverse('api:cms:schemes_collection'),
            data=json.dumps(payload_scheme),
            content_type='application/json',
        )
        self.assertEqual(resp_scheme.status_code, 403)

    def test_04b_operator_rejected_on_governance_publish_action(self):
        """Operator calling governance_action with action='publish' or 'approve' receives HTTP 403."""
        payload = {
            'entity_type': 'page',
            'action': 'publish',
            'target_id': '00000000-0000-0000-0000-000000000001',
            'revision_id': '00000000-0000-0000-0000-000000000001',
        }
        resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Super Administrator authority required', resp.json()['detail'])

    # ==========================================================================
    # 5. Operator Blocked on Self-Approval (Separation of Duties)
    # ==========================================================================

    def test_05_operator_blocked_on_self_approval(self):
        """Separation of duties: An Operator who created a revision cannot self-approve."""
        notice = Notice.objects.create(reference_number='OP-SOD-001')
        trans = NoticeTranslation.objects.create(
            notice=notice,
            language_code='mr',
            slug='op-sod-notice',
            status=STATUS_DRAFT,
        )
        rev = NoticeRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='ऑपरेटर नोटीस',
            summary='सारांश',
            body_markdown='तपशील',
            editorial_status='submitted',
            created_by=self.operator,
        )

        # Even directly in service, passing approver=self.operator raises ValidationError
        with self.assertRaises(ValidationError) as ctx:
            gov_services.approve_notice_revision(
                revision_id=rev.id,
                approver=self.operator,
                notes='Self-approval attempt',
                allow_self_approval=False,
            )
        self.assertIn("Separation of duties violation", str(ctx.exception))

    # ==========================================================================
    # 6. Unauthorized Requests Rejected (401 unauthenticated, 403 citizen)
    # ==========================================================================

    def test_06_unauthorized_requests_rejected(self):
        """Unauthenticated requests get 401, non-administrative citizen gets 403."""
        anon = Client()
        resp_anon = anon.post(
            reverse('api:cms:notices_collection'),
            data=json.dumps({'title': 'Test', 'publish_now': True}),
            content_type='application/json',
        )
        self.assertEqual(resp_anon.status_code, 401)

        resp_citizen = self.citizen_client.post(
            reverse('api:cms:notices_collection'),
            data=json.dumps({'title': 'Test', 'publish_now': True}),
            content_type='application/json',
        )
        self.assertEqual(resp_citizen.status_code, 403)

    # ==========================================================================
    # 7. Public Route Availability Immediately Upon Publication
    # ==========================================================================

    def test_07_published_notice_immediately_available_on_public_route(self):
        """Directly published content is immediately queryable via public API."""
        ref = f"PUB-ROUTE-{timezone.now().timestamp()}"
        payload = {
            'title': 'सार्वजनिक रस्ता कामाची सूचना',
            'description': 'रस्ता दुरुस्तीबाबत सर्व नागरिकांना सूचना.',
            'reference_number': ref,
            'language_code': 'mr',
            'publish_now': True,
        }
        resp = self.admin_client.post(
            reverse('api:cms:notices_collection'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)

        # Anonymous public client queries public notices API
        anon = Client()
        pub_resp = anon.get(reverse('api:notice_list'), {'lang': 'mr'})
        self.assertEqual(pub_resp.status_code, 200)
        items = pub_resp.json().get('results', [])
        found = any(item.get('reference_number') == ref for item in items)
        self.assertTrue(found, "Directly published notice must immediately appear in public notice list.")

    # ==========================================================================
    # 8. Idempotency on Duplicate Requests
    # ==========================================================================

    def test_08_duplicate_publish_requests_are_idempotent(self):
        """Repeated publication requests for an already published revision do not duplicate events."""
        notice = Notice.objects.create(reference_number='IDEM-001')
        trans = NoticeTranslation.objects.create(
            notice=notice,
            language_code='mr',
            slug='idem-notice',
            status=STATUS_DRAFT,
        )
        rev = NoticeRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='पुनरावृत्ती चाचणी',
            summary='सारांश',
            body_markdown='तपशील',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.super_admin,
        )

        # First publish
        pe1 = gov_services.publish_notice_translation(
            translation_id=trans.id,
            revision_id=rev.id,
            actor=self.super_admin,
            justification='First publication',
        )
        initial_events_count = PublicationEvent.objects.filter(target_id=trans.id).count()
        self.assertEqual(initial_events_count, 1)

        # Second publish of the same revision
        pe2 = gov_services.publish_notice_translation(
            translation_id=trans.id,
            revision_id=rev.id,
            actor=self.super_admin,
            justification='Duplicate publish call',
        )
        final_events_count = PublicationEvent.objects.filter(target_id=trans.id).count()
        self.assertEqual(final_events_count, 1, "Duplicate publication call must not create duplicate PublicationEvents.")
        self.assertEqual(pe1.id, pe2.id, "Idempotent call should return the existing PublicationEvent.")
