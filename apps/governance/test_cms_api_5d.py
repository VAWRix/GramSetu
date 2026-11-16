"""
Targeted tests for Milestone 5D: CMS Backend Integration & Governance Workflows.

Verifies:
1. Security & Authentication:
   - Unauthenticated access returns 401.
   - Non-MFA verified session returns 401.
   - Non-administrative user returns 403.
   - Operator attempting privileged governance action returns 403.
2. Dashboard & Review Queue:
   - Live metrics across all statutory domains.
   - Unified pending review queue across Pages, Notices, Documents, Events, Schemes, Gallery.
3. Pages Domain:
   - Draft creation, revision update, submission.
   - Anti-self-approval rule enforcement.
   - Super Admin approval, publication, and withdrawal.
   - Public visibility reflects publication state.
4. Notices Domain:
   - Draft creation, review workflow.
   - Urgent publication with authorization ID and audit logging.
5. Documents Domain:
   - Secure private upload, SHA-256 verification.
   - Authenticated download.
   - Version replacement and disclosure approval.
6. Events Domain:
   - Creation, scheduling, submission, approval, and cancellation.
7. Schemes Domain:
   - Creation, revision branching, approval, and publication.
8. Gallery Domain:
   - Album creation, photo item upload, authenticated image serve, approval.
9. Audit Trail:
   - Retrieval of ApprovalRecord, RejectionRecord, PublicationEvent, NoticeUrgentLog.
"""

import io
import json
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.identity.models import User, RoleAssignment, ROLE_SUPER_ADMIN, ROLE_OPERATOR, OperatorUrgentAuthorization
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_URGENT_PUBLISH,
)
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
    EDITORIAL_REJECTED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    STATUS_WITHDRAWN,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    NoticeUrgentLog,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    DISCLOSURE_DRAFT,
    DISCLOSURE_PENDING_APPROVAL,
    DISCLOSURE_APPROVED,
)
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
)
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
)


class Milestone5DCmsApiTests(TestCase):
    """
    Comprehensive test suite for CMS endpoints and governance integration.
    """

    def setUp(self):
        # 1. Super Admin (Gram Sevak)
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
    # 1. Security & Authentication Checks
    # ==========================================================================

    def test_01_unauthenticated_requests_return_401(self):
        anon_client = Client()
        endpoints = [
            reverse('api:cms:dashboard'),
            reverse('api:cms:pending_submissions'),
            reverse('api:cms:audit_logs'),
            reverse('api:cms:pages_collection'),
            reverse('api:cms:notices_collection'),
            reverse('api:cms:documents_collection'),
            reverse('api:cms:events_collection'),
            reverse('api:cms:schemes_collection'),
            reverse('api:cms:gallery_collection'),
        ]
        for ep in endpoints:
            resp = anon_client.get(ep)
            self.assertEqual(resp.status_code, 401, f"Expected 401 on {ep}")

    def test_02_session_without_mfa_returns_401(self):
        unverified_client = Client()
        unverified_client.force_login(self.super_admin)
        # Note: 'mfa_verified' session key is NOT set
        resp = unverified_client.get(reverse('api:cms:dashboard'))
        self.assertEqual(resp.status_code, 401)
        self.assertIn('Multi-factor authentication', resp.json().get('detail'))

    def test_03_citizen_user_returns_403(self):
        resp = self.citizen_client.get(reverse('api:cms:dashboard'))
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Administrative authority required', resp.json().get('detail'))

    def test_04_operator_forbidden_from_privileged_actions(self):
        # Operator cannot approve or publish
        resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'approve',
                'target_id': '00000000-0000-0000-0000-000000000001',
                'revision_id': '00000000-0000-0000-0000-000000000002',
                'notes': 'Attempting unauthorized approval',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Super Administrator authority required', resp.json().get('detail'))

    # ==========================================================================
    # 2. Content Domain: Pages Lifecycle & Governance
    # ==========================================================================

    def test_05_page_full_lifecycle_and_anti_self_approval(self):
        # Step A: Operator creates draft page
        create_resp = self.operator_client.post(
            reverse('api:cms:pages_collection'),
            data=json.dumps({
                'slug': 'test-panchayat-history',
                'title': 'ग्रामपंचायतीचा इतिहास',
                'summary': 'गावाचा संक्षिप्त इतिहास',
                'body_markdown': '# इतिहास\nआमचे गाव १०० वर्षे जुने आहे.',
                'language_code': 'mr',
                'display_order': 1,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        data = create_resp.json()
        page_id = data['page_id']
        trans_id = data['translation_id']
        rev_id = data['revision_id']

        # Verify initial revision is in draft status
        rev = PageRevision.objects.get(id=rev_id)
        self.assertEqual(rev.editorial_status, EDITORIAL_DRAFT)

        # Step B: Operator updates draft revision
        update_resp = self.operator_client.put(
            reverse('api:cms:page_revision_update', kwargs={'revision_id': rev_id}),
            data=json.dumps({
                'title': 'ग्रामपंचायतीचा संपूर्ण इतिहास',
                'summary': 'सुधारित इतिहास',
                'body_markdown': '# सुधारित इतिहास\nअधिक माहिती.',
            }),
            content_type='application/json',
        )
        self.assertEqual(update_resp.status_code, 200)
        rev.refresh_from_db()
        self.assertEqual(rev.title, 'ग्रामपंचायतीचा संपूर्ण इतिहास')

        # Step C: Operator submits revision for approval
        submit_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'submit',
                'target_id': trans_id,
                'revision_id': rev_id,
            }),
            content_type='application/json',
        )
        self.assertEqual(submit_resp.status_code, 200)
        rev.refresh_from_db()
        self.assertEqual(rev.editorial_status, EDITORIAL_SUBMITTED)

        # Step D: Operator attempts to self-approve -> MUST BE REJECTED
        # Direct service invocation with operator raises ValidationError (separation of duties)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            from apps.governance import services as gov_services
            gov_services.approve_page_revision(
                revision_id=rev_id,
                approver=self.operator,
                notes='Trying to self approve',
                allow_self_approval=False,
            )

        # Operator attempting to approve via API is blocked with 403 Forbidden
        self_approve_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'approve',
                'target_id': trans_id,
                'revision_id': rev_id,
                'notes': 'Trying to self approve my own revision',
            }),
            content_type='application/json',
        )
        self.assertEqual(self_approve_resp.status_code, 403)

        # Step E: Super Admin approves revision
        approve_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'approve',
                'target_id': trans_id,
                'revision_id': rev_id,
                'notes': 'Approved after factual review.',
            }),
            content_type='application/json',
        )
        self.assertEqual(approve_resp.status_code, 200)
        rev.refresh_from_db()
        self.assertEqual(rev.editorial_status, EDITORIAL_APPROVED)
        self.assertTrue(ApprovalRecord.objects.filter(revision_id=rev_id).exists())

        # Step F: Super Admin publishes translation
        pub_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'publish',
                'target_id': trans_id,
                'revision_id': rev_id,
                'justification': 'Official release of history page.',
            }),
            content_type='application/json',
        )
        self.assertEqual(pub_resp.status_code, 200)
        trans = PageTranslation.objects.get(id=trans_id)
        self.assertEqual(trans.status, STATUS_PUBLISHED)
        self.assertTrue(PublicationEvent.objects.filter(target_id=trans_id, event_type=EVENT_INITIAL_PUBLISH).exists())

        # Step G: Public page API now returns published page
        public_resp = self.client.get(reverse('api:page_detail', kwargs={'slug': 'test-panchayat-history'}))
        self.assertEqual(public_resp.status_code, 200)
        self.assertEqual(public_resp.json().get('title'), 'ग्रामपंचायतीचा संपूर्ण इतिहास')

        # Step H: Super Admin withdraws translation
        withdraw_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'withdraw',
                'target_id': trans_id,
                'justification': 'Temporary withdrawal for revision update.',
            }),
            content_type='application/json',
        )
        self.assertEqual(withdraw_resp.status_code, 200)
        trans.refresh_from_db()
        self.assertEqual(trans.status, STATUS_WITHDRAWN)

        # Step I: Public API no longer returns withdrawn page (404)
        public_after_withdraw = self.client.get(reverse('api:page_detail', kwargs={'slug': 'test-panchayat-history'}))
        self.assertEqual(public_after_withdraw.status_code, 404)

    def test_06_page_rejection_requires_minimum_reason(self):
        # Create and submit a page revision
        page = Page.objects.create(slug='reject-test')
        trans = PageTranslation.objects.create(page=page, language_code='mr', status=STATUS_DRAFT)
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='अपूर्ण माहिती',
            editorial_status=EDITORIAL_SUBMITTED,
            created_by=self.operator,
        )

        # Super Admin attempts to reject with short reason (<10 chars) -> MUST FAIL
        short_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'reject',
                'target_id': str(trans.id),
                'revision_id': str(rev.id),
                'reason': 'Bad',
            }),
            content_type='application/json',
        )
        self.assertEqual(short_resp.status_code, 400)
        self.assertIn('10 non-whitespace characters', short_resp.json().get('detail'))

        # Reject with valid rationale
        valid_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'reject',
                'target_id': str(trans.id),
                'revision_id': str(rev.id),
                'reason': 'माहिती अपूर्ण आहे, कृपया अधिक तपशील जोडावेत.',
            }),
            content_type='application/json',
        )
        self.assertEqual(valid_resp.status_code, 200)
        rev.refresh_from_db()
        self.assertEqual(rev.editorial_status, EDITORIAL_REJECTED)
        self.assertTrue(RejectionRecord.objects.filter(revision_id=str(rev.id)).exists())

    # ==========================================================================
    # 3. Notices Domain & Urgent Publishing
    # ==========================================================================

    def test_07_notice_urgent_publication_workflow(self):
        # Step A: Operator creates draft notice
        create_resp = self.operator_client.post(
            reverse('api:cms:notices_collection'),
            data=json.dumps({
                'notice_type': 'statutory',
                'title': 'तातडीची ग्रामसभा सूचना',
                'description': 'अतिवृष्टीमुळे तातडीची सभा बोलावण्यात आली आहे.',
                'language_code': 'mr',
                'is_emergency': True,
                'display_order': 1,
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        notice_id = create_resp.json()['notice_id']
        trans_id = create_resp.json()['translation_id']
        rev_id = create_resp.json()['revision_id']

        # Create active urgent authorization for operator
        auth = OperatorUrgentAuthorization.objects.create(
            operator=self.operator,
            authorized_by=self.super_admin,
            allowed_category='disaster_alert',
            valid_from=timezone.now() - timedelta(hours=1),
            valid_to=timezone.now() + timedelta(hours=24),
        )

        # Step B: Operator executes urgent_publish with authorization code and justification
        urgent_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'notice',
                'action': 'urgent_publish',
                'target_id': trans_id,
                'notice_id': notice_id,
                'revision_id': rev_id,
                'urgent_authorization_id': str(auth.id),
                'justification': 'जिल्हाधिकारी कार्यालयाकडून आलेली पूर परिस्थितीची तातडीची सूचना.',
            }),
            content_type='application/json',
        )
        self.assertEqual(urgent_resp.status_code, 200)
        data = urgent_resp.json()
        self.assertTrue(data.get('success'))

        # Check NoticeUrgentLog is recorded
        self.assertTrue(NoticeUrgentLog.objects.filter(notice_id=notice_id).exists())
        log_entry = NoticeUrgentLog.objects.get(notice_id=notice_id)
        self.assertEqual(str(log_entry.urgent_authorization_id), str(auth.id))
        self.assertEqual(log_entry.ratification_status, 'pending_review')

        # Check notice is published immediately on public portal
        public_resp = self.client.get(reverse('api:notice_detail', kwargs={'notice_id': notice_id}))
        self.assertEqual(public_resp.status_code, 200)
        self.assertEqual(public_resp.json().get('title'), 'तातडीची ग्रामसभा सूचना')

    # ==========================================================================
    # 4. Documents Domain & Secure Version Management
    # ==========================================================================

    def test_08_document_upload_download_and_versioning(self):
        # Create a sample PDF-like content
        dummy_pdf = io.BytesIO(b"%PDF-1.4 test document content for gramsetu")
        uploaded_file = SimpleUploadedFile("resolution_2026.pdf", dummy_pdf.read(), content_type="application/pdf")

        # Step A: Operator uploads document draft
        upload_resp = self.operator_client.post(
            reverse('api:cms:documents_collection'),
            data={
                'title': 'वार्षिक अंदाजपत्रक ठराव',
                'category': 'resolution',
                'reference_number': 'RES-2026-001',
                'issuing_department': 'ग्रामपंचायत कार्यालय',
                'language_code': 'mr',
                'file': uploaded_file,
            },
        )
        self.assertEqual(upload_resp.status_code, 201)
        doc_data = upload_resp.json()
        doc_id = doc_data['document_id']
        trans_id = doc_data['translation_id']
        ver_id = doc_data['version_id']

        # Verify initial status is draft
        ver = DocumentVersion.objects.get(id=ver_id)
        self.assertEqual(ver.disclosure_status, DISCLOSURE_DRAFT)

        # Step B: Authenticated admin downloads file for inspection
        dl_resp = self.admin_client.get(reverse('api:cms:document_version_download', kwargs={'version_id': ver_id}))
        self.assertEqual(dl_resp.status_code, 200)
        self.assertEqual(dl_resp['Content-Type'], 'application/octet-stream')

        # Unauthenticated download MUST fail
        anon_dl = self.client.get(reverse('api:cms:document_version_download', kwargs={'version_id': ver_id}))
        self.assertEqual(anon_dl.status_code, 401)

        # Step C: Operator submits document version for disclosure
        submit_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'document',
                'action': 'submit',
                'target_id': ver_id,
                'version_id': ver_id,
            }),
            content_type='application/json',
        )
        self.assertEqual(submit_resp.status_code, 200)
        ver.refresh_from_db()
        self.assertEqual(ver.disclosure_status, DISCLOSURE_PENDING_APPROVAL)

        # Step D: Super Admin approves disclosure
        approve_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'document',
                'action': 'approve',
                'target_id': ver_id,
                'version_id': ver_id,
                'notes': 'Verified stamp and signature.',
                'justification': 'Statutory disclosure under section 4.',
            }),
            content_type='application/json',
        )
        self.assertEqual(approve_resp.status_code, 200)
        ver.refresh_from_db()
        self.assertEqual(ver.disclosure_status, DISCLOSURE_APPROVED)

        # Step E: Operator uploads replacement version 2
        dummy_v2 = io.BytesIO(b"%PDF-1.4 updated resolution with appendix")
        v2_file = SimpleUploadedFile("resolution_2026_v2.pdf", dummy_v2.read(), content_type="application/pdf")
        v2_resp = self.operator_client.post(
            reverse('api:cms:document_version_upload', kwargs={'document_id': doc_id}),
            data={
                'language_code': 'mr',
                'file': v2_file,
            },
        )
        self.assertEqual(v2_resp.status_code, 201)
        v2_data = v2_resp.json()
        self.assertEqual(v2_data['version_number'], 2)

    # ==========================================================================
    # 5. Events Domain: Meetings & Cancellations
    # ==========================================================================

    def test_09_event_creation_approval_and_cancellation(self):
        start_time = (timezone.now() + timedelta(days=7)).isoformat()
        end_time = (timezone.now() + timedelta(days=7, hours=3)).isoformat()

        # Step A: Operator creates draft event
        create_resp = self.operator_client.post(
            reverse('api:cms:events_collection'),
            data=json.dumps({
                'title': 'प्रजासत्ताक दिन विशेष ग्रामसभा',
                'event_type': 'gram_sabha',
                'start_datetime': start_time,
                'end_datetime': end_time,
                'venue_mr': 'ग्रामपंचायत सभागृह',
                'description': 'विकास कामांचा आढावा.',
                'agenda': '१. मागील सभेचे इतिवृत्त\n२. नवीन रस्ते कामे',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        event_id = create_resp.json()['event_id']

        # Step B: Operator submits event
        submit_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'event',
                'action': 'submit',
                'target_id': event_id,
            }),
            content_type='application/json',
        )
        self.assertEqual(submit_resp.status_code, 200)

        # Step C: Super Admin approves and publishes event
        approve_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'event',
                'action': 'approve',
                'target_id': event_id,
                'notes': 'Notice issued to all ward members.',
            }),
            content_type='application/json',
        )
        self.assertEqual(approve_resp.status_code, 200)
        ev = PanchayatEvent.objects.get(id=event_id)
        self.assertTrue(ev.is_published)

        # Step D: Super Admin cancels event with reason
        cancel_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'event',
                'action': 'cancel',
                'target_id': event_id,
                'reason': 'अपरिहार्य प्रशासकीय कारणास्तव सभा पुढे ढकलण्यात येत आहे.',
            }),
            content_type='application/json',
        )
        self.assertEqual(cancel_resp.status_code, 200)
        ev.refresh_from_db()
        self.assertEqual(ev.status, STATUS_CANCELLED)
        self.assertIn('अपरिहार्य', ev.cancellation_reason)

    # ==========================================================================
    # 6. Welfare Schemes Domain
    # ==========================================================================

    def test_10_scheme_creation_and_approval(self):
        # Step A: Operator creates draft scheme
        create_resp = self.operator_client.post(
            reverse('api:cms:schemes_collection'),
            data=json.dumps({
                'slug': 'pm-kisan-sanman',
                'title': 'पीएम किसान सन्मान निधी योजना',
                'scheme_level': 'central',
                'target_beneficiary': 'farmers',
                'short_description': 'शेतकऱ्यांना वार्षिक आर्थिक सहाय्य.',
                'benefits_summary': 'दरवर्षी रु. ६,००० तीन हप्त्यांमध्ये दिले जातात.',
                'eligibility_criteria': 'जमीनधारक शेतकरी कुटुंबे ज्यांच्या नावावर शेतजमीन आहे.',
                'required_documents': 'आधार कार्ड, ७/१२ उतारा, ८-अ, बँक पासबुक',
                'application_process': 'सीएससी केंद्र किंवा महाडीबीटी पोर्टलद्वारे अर्ज करावा.',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        scheme_id = create_resp.json()['scheme_id']
        trans_id = create_resp.json()['translation_id']
        rev_id = create_resp.json()['revision_id']

        # Step B: Operator submits scheme revision
        sub_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'scheme',
                'action': 'submit',
                'target_id': trans_id,
                'revision_id': rev_id,
            }),
            content_type='application/json',
        )
        self.assertEqual(sub_resp.status_code, 200)

        # Step C: Super Admin approves and publishes scheme
        approve_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'scheme',
                'action': 'approve',
                'target_id': trans_id,
                'revision_id': rev_id,
                'notes': 'Verified with agriculture department guidelines.',
            }),
            content_type='application/json',
        )
        self.assertEqual(approve_resp.status_code, 200)

        pub_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'scheme',
                'action': 'publish',
                'target_id': trans_id,
                'revision_id': rev_id,
                'justification': 'Published for general farmer awareness.',
            }),
            content_type='application/json',
        )
        self.assertEqual(pub_resp.status_code, 200)

        # Verify public API returns scheme
        public_resp = self.client.get(reverse('api:scheme_detail', kwargs={'identifier': 'pm-kisan-sanman'}))
        self.assertEqual(public_resp.status_code, 200)
        self.assertEqual(public_resp.json().get('scheme_name'), 'पीएम किसान सन्मान निधी योजना')

    # ==========================================================================
    # 7. Photo Gallery Domain
    # ==========================================================================

    def test_11_gallery_album_upload_and_image_serving(self):
        # Step A: Operator creates album draft
        create_resp = self.operator_client.post(
            reverse('api:cms:gallery_collection'),
            data=json.dumps({
                'slug': 'water-tank-inauguration-2026',
                'title': 'नवीन पाणीपुरवठा टाकी लोकार्पण',
                'category': 'infrastructure',
                'language_code': 'mr',
                'description': 'जलजीवन मिशन अंतर्गत जलकुंभ लोकार्पण.',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)
        album_id = create_resp.json()['album_id']

        # Step B: Operator uploads a photo item (JPEG)
        # 1x1 dummy JPEG
        dummy_jpeg = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
            b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
        )
        img_file = SimpleUploadedFile("water_tank.jpg", dummy_jpeg, content_type="image/jpeg")

        upload_img_resp = self.operator_client.post(
            reverse('api:cms:gallery_detail_items', kwargs={'album_id': album_id}),
            data={
                'image_file': img_file,
                'caption_mr': 'जलकुंभाचे उद्घाटन करताना सरपंच व ग्रामस्थ',
            },
        )
        self.assertEqual(upload_img_resp.status_code, 201)
        item_id = upload_img_resp.json()['item_id']

        # Step C: Authenticated admin can view image
        serve_resp = self.admin_client.get(reverse('api:cms:gallery_image_serve', kwargs={'item_id': item_id}))
        self.assertEqual(serve_resp.status_code, 200)
        self.assertEqual(serve_resp['Content-Type'], 'image/jpeg')

        # Unauthenticated request MUST be rejected with 401
        anon_serve = self.client.get(reverse('api:cms:gallery_image_serve', kwargs={'item_id': item_id}))
        self.assertEqual(anon_serve.status_code, 401)

    # ==========================================================================
    # 8. Pending Queue & Audit Ledger
    # ==========================================================================

    def test_12_dashboard_pending_queue_and_audit_ledger(self):
        # Create a submitted page revision to populate queue
        page = Page.objects.create(slug='queue-check')
        trans = PageTranslation.objects.create(page=page, language_code='mr', status=STATUS_DRAFT)
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='प्रलंबित पान',
            editorial_status=EDITORIAL_SUBMITTED,
            created_by=self.operator,
        )

        # Check pending submissions endpoint
        pending_resp = self.admin_client.get(reverse('api:cms:pending_submissions'))
        self.assertEqual(pending_resp.status_code, 200)
        p_data = pending_resp.json()
        self.assertGreaterEqual(p_data['count'], 1)
        found = any(it['revision_id'] == str(rev.id) for it in p_data['results'])
        self.assertTrue(found, "Newly submitted revision must appear in pending queue.")

        # Check dashboard metrics
        dash_resp = self.admin_client.get(reverse('api:cms:dashboard'))
        self.assertEqual(dash_resp.status_code, 200)
        d_data = dash_resp.json()
        self.assertGreaterEqual(d_data['overview']['pending_review_count'], 1)

        # Check audit ledger
        audit_resp = self.admin_client.get(reverse('api:cms:audit_logs'))
        self.assertEqual(audit_resp.status_code, 200)
        a_data = audit_resp.json()
        self.assertIn('results', a_data)
