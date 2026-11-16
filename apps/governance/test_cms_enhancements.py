"""
Targeted integration tests for CMS Content Governance, Record Details, Cancellation Lifecycle & Photo Gallery Redesign.
Covers Workstreams A, B, C, D, and E.
"""

import json
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile

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
    EVENT_WITHDRAWAL,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    STATUS_PUBLISHED as NOTICE_PUBLISHED,
    STATUS_WITHDRAWN as NOTICE_WITHDRAWN,
    EDITORIAL_APPROVED,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    DISCLOSURE_APPROVED,
    DISCLOSURE_WITHDRAWN,
    STATUS_DISCLOSED,
)
from apps.documents.storage import save_private_document
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    STATUS_PUBLISHED as EVENT_PUBLISHED,
    STATUS_CANCELLED as EVENT_CANCELLED,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
    STATUS_PUBLISHED as SCHEME_PUBLISHED,
    STATUS_DRAFT as SCHEME_DRAFT,
)
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
    STATUS_PUBLISHED as GALLERY_PUBLISHED,
    STATUS_DRAFT as GALLERY_DRAFT,
)
from apps.gallery.storage import convert_and_validate_image_url


class CmsEnhancementsTests(TestCase):
    """
    Automated verification of Workstreams A through E.
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

        # 3. Authenticated Clients
        self.admin_client = self._create_mfa_client(self.super_admin)
        self.operator_client = self._create_mfa_client(self.operator)
        self.anon_client = Client()

    def _create_mfa_client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session['mfa_verified'] = True
        session.save()
        return client

    # ==========================================================================
    # Workstream A: Documents & Disclosures (Published Records & Withdrawal)
    # ==========================================================================

    def test_workstream_a_documents_collection_and_withdrawal(self):
        """Verify document collection returns published records and handles withdrawal."""
        # Create a document with disclosed version
        doc = Document.objects.create(category='citizen_charter', reference_number='DOC-2026-001')
        trans = DocumentTranslation.objects.create(
            document=doc,
            language_code='mr',
            title='नागरिक सनद २०२६',
            description='नागरिक सनद सविस्तर दस्तऐवज.',
            status=STATUS_DISCLOSED,
        )
        dummy_file = SimpleUploadedFile("charter.pdf", b"%PDF-1.4 test document content", content_type="application/pdf")
        rel_path, size_bytes, sha256 = save_private_document(dummy_file)

        ver = DocumentVersion.objects.create(
            translation=trans,
            version_number=1,
            original_filename='charter.pdf',
            storage_path=rel_path,
            file_size_bytes=size_bytes,
            mime_type='application/pdf',
            checksum_sha256=sha256,
            disclosure_status=DISCLOSURE_APPROVED,
            uploaded_by=self.operator,
        )
        trans.current_version = ver
        trans.save()

        # 1. Fetch CMS documents collection - must include published/disclosed record
        resp = self.admin_client.get(reverse('api:cms:documents_collection'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(any(d['id'] == str(doc.id) for d in data['results']))

        # 2. Operator cannot withdraw document (requires Super Admin)
        withdraw_payload = {
            'entity_type': 'document',
            'action': 'withdraw',
            'target_id': str(trans.id),
            'justification': 'Outdated document replaced by statutory decree.',
        }
        op_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(withdraw_payload),
            content_type='application/json',
        )
        self.assertEqual(op_resp.status_code, 403)

        # 3. Super Admin withdraws document with justification < 10 chars -> rejected
        invalid_payload = dict(withdraw_payload, justification='Too short')
        inv_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(invalid_payload),
            content_type='application/json',
        )
        self.assertEqual(inv_resp.status_code, 400)

        # 4. Super Admin withdraws document with valid justification -> succeeds
        admin_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(withdraw_payload),
            content_type='application/json',
        )
        self.assertEqual(admin_resp.status_code, 200)
        self.assertTrue(admin_resp.json()['success'])

        trans.refresh_from_db()
        self.assertEqual(trans.status, 'withdrawn')

    # ==========================================================================
    # Workstream B: Schemes & Welfare (Inspection & Public Details)
    # ==========================================================================

    def test_workstream_b_schemes_collection_and_public_detail(self):
        """Verify scheme collection exports required fields and public detail page enforces disclosure gate."""
        scheme = WelfareScheme.objects.create(
            slug='kisan-tractor-subsidy',
            scheme_level='state',
            target_beneficiary='farmers',
            display_order=5,
            created_by=self.operator,
        )
        trans = SchemeTranslation.objects.create(
            scheme=scheme,
            language_code='mr',
            localized_slug='kisan-tractor-subsidy-mr',
            status=SCHEME_PUBLISHED,
        )
        rev = SchemeRevision.objects.create(
            translation=trans,
            revision_number=1,
            scheme_name='कृषी ट्रॅक्टर अनुदान योजना',
            short_summary='शेतकऱ्यांना ट्रॅक्टर खरेदीसाठी थेट आर्थिक सहाय्य.',
            benefits='१.२५ लाख रुपये थेट बँक खात्यात अनुदान.',
            eligibility_criteria='किमान २ एकर शेती जमीन आणि आधार संलग्न बँक खाते.',
            required_documents='७/१२ उतारा, ८-अ उतारा, आधार कार्ड, बँक पासबुक प्रत.',
            application_process='आपले सरकार सेवा केंद्र किंवा ग्रामपंचायत कार्यालयात अर्ज सादर करावा.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        trans.current_approved_revision = rev
        trans.save()

        # 1. CMS Schemes collection includes display fields & required_documents
        resp = self.admin_client.get(reverse('api:cms:schemes_collection'))
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        matched = next((s for s in results if s['id'] == str(scheme.id)), None)
        self.assertIsNotNone(matched)
        self.assertEqual(matched['display_order'], 5)
        self.assertEqual(matched['translations'][0]['revisions'][0]['required_documents'], '७/१२ उतारा, ८-अ उतारा, आधार कार्ड, बँक पासबुक प्रत.')
        self.assertIn('राज्य', matched['scheme_level_display'])

        # 2. Public detail endpoint returns complete data
        public_resp = self.anon_client.get(f'/api/schemes/{scheme.slug}/?lang=mr')
        self.assertEqual(public_resp.status_code, 200)
        pub_data = public_resp.json()
        self.assertEqual(pub_data['scheme_name'], 'कृषी ट्रॅक्टर अनुदान योजना')
        self.assertIn('७/१२ उतारा', pub_data['required_documents'])

        # 3. Draft scheme returns 404 to anonymous citizens
        draft_scheme = WelfareScheme.objects.create(slug='draft-irrigation-scheme', scheme_level='central', target_beneficiary='farmers', created_by=self.operator)
        SchemeTranslation.objects.create(scheme=draft_scheme, language_code='mr', localized_slug='draft-irrigation-mr', status=SCHEME_DRAFT)
        draft_resp = self.anon_client.get(f'/api/schemes/{draft_scheme.slug}/?lang=mr')
        self.assertEqual(draft_resp.status_code, 404)

    # ==========================================================================
    # Workstream C: Approval Review Screen (Full Submitted Fields)
    # ==========================================================================

    def test_workstream_c_pending_submissions_inspection_fields(self):
        """Verify pending review queue returns full submitted fields for comprehensive inspection."""
        now = timezone.now()
        event = PanchayatEvent.objects.create(
            event_type='gram_sabha',
            start_datetime=now + timedelta(days=3),
            end_datetime=now + timedelta(days=3, hours=2),
            venue_mr='ग्रामपंचायत मुख्य सभागृह, सानेवाडी',
            status='pending_approval',
            created_by=self.operator,
        )
        EventTranslation.objects.create(
            event=event,
            language_code='mr',
            title='पाणी पुरवठा नियोजन विशेष ग्रामसभा',
            description='गावातील पाणी टंचाई निवारण व पाईपलाईन दुरुस्ती.',
            agenda='१. जुनी पाईपलाईन दुरुस्ती २. नवीन विहीर खोदकाम मंजुरी',
        )

        resp = self.admin_client.get(reverse('api:cms:pending_submissions'))
        self.assertEqual(resp.status_code, 200)
        pending = resp.json()['results']
        matched_event = next((s for s in pending if s['id'] == str(event.id)), None)
        self.assertIsNotNone(matched_event)
        self.assertEqual(matched_event['entity_type'], 'event')
        self.assertEqual(matched_event['venue'], 'ग्रामपंचायत मुख्य सभागृह, सानेवाडी')
        self.assertIn('पाईपलाईन दुरुस्ती', matched_event['agenda'])

    # ==========================================================================
    # Workstream D: Meeting Cancellation Lifecycle & 6-Hour Alert Expiry
    # ==========================================================================

    def test_workstream_d_cancellation_lifecycle_and_expiry(self):
        """Verify event cancellation records timestamp and expires from alert after 6 hours."""
        now = timezone.now()
        event = PanchayatEvent.objects.create(
            event_type='gram_sabha',
            start_datetime=now + timedelta(days=1),
            end_datetime=now + timedelta(days=1, hours=2),
            venue_mr='ग्रामपंचायत कार्यालय',
            status=EVENT_PUBLISHED,
            is_published=True,
            created_by=self.operator,
        )
        EventTranslation.objects.create(
            event=event,
            language_code='mr',
            title='मासिक आढावा बैठक',
            agenda='मागील महिन्यातील कामांचा आढावा.',
        )

        # Cancel event with mandatory reason
        cancel_payload = {
            'entity_type': 'event',
            'action': 'cancel',
            'target_id': str(event.id),
            'reason': 'अपरिहार्य तांत्रिक कारणामुळे आणि भारी पावसामुळे बैठक रद्द करण्यात आली आहे.',
        }
        resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps(cancel_payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

        event.refresh_from_db()
        self.assertEqual(event.status, EVENT_CANCELLED)
        self.assertIsNotNone(event.cancelled_at)
        self.assertIn('भारी पावसामुळे', event.cancellation_reason)

        # Alert is active immediately after cancellation
        self.assertTrue(event.is_cancellation_alert_active(now=event.cancelled_at + timedelta(hours=1)))
        # Alert is inactive after 6 hours
        self.assertFalse(event.is_cancellation_alert_active(now=event.cancelled_at + timedelta(hours=6, minutes=1)))

        # Public events API includes cancelled_at and is_cancellation_alert_active
        pub_resp = self.anon_client.get('/api/events/?lang=mr')
        self.assertEqual(pub_resp.status_code, 200)
        pub_events = pub_resp.json()['results']
        matched_pub = next((e for e in pub_events if e['id'] == str(event.id)), None)
        self.assertIsNotNone(matched_pub)
        self.assertEqual(matched_pub['status'], EVENT_CANCELLED)
        self.assertTrue(matched_pub['is_cancellation_alert_active'])
        self.assertIn('भारी पावसामुळे', matched_pub['cancellation_reason'])

    # ==========================================================================
    # Workstream E: Photo Gallery Redesign (SSRF Protection & Item Management)
    # ==========================================================================

    def test_workstream_e_ssrf_safety_and_image_management(self):
        """Verify URL validation prevents SSRF attacks and handles Google Drive translation."""
        # 1. SSRF loopback protection
        converted, err = convert_and_validate_image_url('http://127.0.0.1:8000/private.jpg')
        self.assertIsNotNone(err)
        self.assertIn("forbidden", err.lower())

        # 2. SSRF local network protection
        converted, err = convert_and_validate_image_url('http://192.168.1.1/router.jpg')
        self.assertIsNotNone(err)
        self.assertIn("blocked", err.lower())

        # 3. Google Drive direct stream URL translation
        drive_url = 'https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view?usp=sharing'
        converted, err = convert_and_validate_image_url(drive_url)
        self.assertIsNone(err)
        self.assertEqual(converted, 'https://drive.google.com/uc?export=view&id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs')

        # 4. Create an album and test item management via CMS items endpoint
        album = GalleryAlbum.objects.create(
            category='infrastructure',
            slug='solar-lights-installation',
            status=GALLERY_DRAFT,
            created_by=self.super_admin,
        )
        AlbumTranslation.objects.create(
            album=album,
            language_code='mr',
            title='सौर पथदिवे प्रतिष्ठापन प्रकल्प',
            description='गावातील सर्व रस्त्यांवर सौर पथदिवे बसविण्यात आले.',
        )

        # 5. Attempt adding malicious SSRF link via CMS endpoint -> blocked with 400
        ssrf_payload = {
            'action': 'add_link',
            'external_url': 'http://127.0.0.1:8000/internal-admin.png',
            'caption_mr': 'हॅक प्रयत्न',
            'alt_text_mr': 'अनाधिकृत छायाचित्र',
        }
        ssrf_resp = self.admin_client.post(
            reverse('api:cms:gallery_detail_items', kwargs={'album_id': str(album.id)}),
            data=json.dumps(ssrf_payload),
            content_type='application/json',
        )
        self.assertEqual(ssrf_resp.status_code, 400)

        # 6. Add valid image link via CMS endpoint
        add_link_payload = {
            'action': 'add_link',
            'external_url': 'https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/view',
            'caption_mr': 'मुख्य रस्त्यावरील सौर दिवे',
            'alt_text_mr': 'रस्त्याच्या कडेला बसवलेला सौर पथदिवा',
        }
        link_resp = self.admin_client.post(
            reverse('api:cms:gallery_detail_items', kwargs={'album_id': str(album.id)}),
            data=json.dumps(add_link_payload),
            content_type='application/json',
        )
        self.assertEqual(link_resp.status_code, 201)
        item1_id = link_resp.json()['item_id']

        item1 = GalleryItem.objects.get(id=item1_id)
        self.assertEqual(item1.source_type, 'link')
        self.assertTrue(item1.external_url.startswith('https://drive.google.com/uc?export=view&id='))

        # 7. Set cover image
        cover_payload = {
            'action': 'set_cover',
            'item_id': item1_id,
        }
        cover_resp = self.admin_client.post(
            reverse('api:cms:gallery_detail_items', kwargs={'album_id': str(album.id)}),
            data=json.dumps(cover_payload),
            content_type='application/json',
        )
        self.assertEqual(cover_resp.status_code, 200)
        album.refresh_from_db()
        self.assertEqual(album.cover_image.id, item1.id)

    def test_document_disclosure_idempotency_and_no_500(self):
        """
        Regression test: publishing an already approved or disclosed version does not 500.
        """
        from apps.governance import services as gov_services

        doc = Document.objects.create(
            category='resolution',
            reference_number='GP/REG/RES-01',
            issuing_department='सामान्य प्रशासन',
        )
        trans = DocumentTranslation.objects.create(
            document=doc,
            language_code='mr',
            title='ग्रामसभा ठराव क्रमांक १',
            status='draft',
        )
        test_file = SimpleUploadedFile("resolution.pdf", b"%PDF-1.4 test document binary content", content_type="application/pdf")
        filename, size, checksum = save_private_document(test_file)
        ver = DocumentVersion.objects.create(
            translation=trans,
            version_number=1,
            storage_path=filename,
            original_filename="resolution.pdf",
            file_size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=self.operator,
            disclosure_status='draft',
        )

        # 1. Operator submits version for disclosure
        submit_resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'document',
                'target_id': str(trans.id),
                'revision_id': str(ver.id),
                'action': 'submit',
            }),
            content_type='application/json',
        )
        self.assertEqual(submit_resp.status_code, 200)
        ver.refresh_from_db()
        self.assertEqual(ver.disclosure_status, 'pending_approval')

        # 2. Super Admin approves disclosure (target_id=translation_id, revision_id=version_id)
        approve_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'document',
                'target_id': str(trans.id),
                'revision_id': str(ver.id),
                'action': 'approve',
                'notes': 'Statutory disclosure approved.',
            }),
            content_type='application/json',
        )
        self.assertEqual(approve_resp.status_code, 200)
        ver.refresh_from_db()
        trans.refresh_from_db()
        self.assertEqual(ver.disclosure_status, 'approved_for_disclosure')
        self.assertEqual(trans.status, 'disclosed')
        self.assertEqual(trans.current_version_id, ver.id)

        # 3. Idempotency check: Repeated publish action does NOT 500
        repeat_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'document',
                'target_id': str(trans.id),
                'revision_id': str(ver.id),
                'action': 'publish',
                'notes': 'Second publish click.',
            }),
            content_type='application/json',
        )
        self.assertEqual(repeat_resp.status_code, 200)
        self.assertTrue(repeat_resp.json()['success'])

    def test_document_creation_category_mapping_and_validation(self):
        """
        Regression test: category mapping converts legacy/frontend categories and invalid categories return 400.
        """
        test_file = SimpleUploadedFile("minutes.pdf", b"%PDF-1.4 test minutes binary", content_type="application/pdf")
        resp = self.admin_client.post(
            reverse('api:cms:documents_collection'),
            data={
                'title': 'ग्रामसभा इतिवृत्त',
                'category': 'meeting_minutes', # mapped to 'resolution'
                'reference_number': 'GP/2026/MM-01',
                'file': test_file,
                'publish_now': 'true',
            },
        )
        self.assertEqual(resp.status_code, 201)
        doc_id = resp.json()['document_id']
        doc = Document.objects.get(id=doc_id)
        self.assertEqual(doc.category, 'resolution')

        # Invalid category returns 400, not 500
        invalid_file = SimpleUploadedFile("invalid.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        bad_resp = self.admin_client.post(
            reverse('api:cms:documents_collection'),
            data={
                'title': 'चुकीचा प्रवर्ग',
                'category': 'totally_invalid_category_xyz',
                'file': invalid_file,
            },
        )
        self.assertEqual(bad_resp.status_code, 400)
        self.assertIn('Invalid category', bad_resp.json()['detail'])

    def test_scheme_duplicate_slug_handling(self):
        """
        Regression test: duplicate scheme slug returns 400 error rather than database 500 crash.
        """
        WelfareScheme.objects.create(
            slug='pm-kisan-yojana',
            scheme_level='central',
            target_beneficiary='farmers',
            created_by=self.super_admin,
        )

        resp = self.admin_client.post(
            reverse('api:cms:schemes_collection'),
            data=json.dumps({
                'slug': 'pm-kisan-yojana',
                'title': 'पीएम किसान योजना',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already exists', resp.json()['detail'])

    def test_gallery_pending_governance_no_500(self):
        """
        Regression test: /api/cms/pending/ handles gallery albums without crashing on image_file attribute.
        """
        album = GalleryAlbum.objects.create(
            slug='village-fest-2026',
            category='cultural',
            status='pending_approval',
            created_by=self.operator,
        )
        AlbumTranslation.objects.create(
            album=album,
            language_code='mr',
            title='ग्राम उत्सव २०२६',
        )
        GalleryItem.objects.create(
            album=album,
            storage_path='img_001.jpg',
            original_filename='fest.jpg',
            file_size_bytes=1024,
            mime_type='image/jpeg',
            checksum_sha256='0'*64,
            caption_mr='उत्सव उद्घाटन',
            alt_text_mr='उद्घाटन समारंभ',
            uploaded_by=self.operator,
        )

        for status in ['pending', 'approved', 'published', 'all']:
            resp = self.admin_client.get(f"{reverse('api:cms:pending_submissions')}?status={status}")
            self.assertEqual(resp.status_code, 200)

    def test_public_multilingual_fallback_to_marathi(self):
        """
        Regression test: English and Hindi citizen queries fall back to primary Marathi record.
        """
        # 1. Document with only Marathi translation
        doc = Document.objects.create(
            category='resolution',
            reference_number='GP/2026/DOC-MR',
            issuing_department='प्रशासन',
        )
        dtrans = DocumentTranslation.objects.create(
            document=doc,
            language_code='mr',
            title='मराठी ठराव',
            status='disclosed',
        )
        tfile = SimpleUploadedFile("test.pdf", b"%PDF-1.4 sample content", content_type="application/pdf")
        fname, fsize, fhash = save_private_document(tfile)
        dver = DocumentVersion.objects.create(
            translation=dtrans,
            version_number=1,
            storage_path=fname,
            original_filename="test.pdf",
            file_size_bytes=fsize,
            checksum_sha256=fhash,
            uploaded_by=self.super_admin,
            disclosure_status='approved_for_disclosure',
        )
        dtrans.current_version = dver
        dtrans.save()

        # Query public document in English with fallback enabled
        client = Client()
        doc_resp = client.get('/documents/?lang=en&fallback=1')
        self.assertEqual(doc_resp.status_code, 200)
        doc_data = doc_resp.json()
        self.assertGreaterEqual(doc_data['count'], 1)
        found_doc = next((d for d in doc_data['results'] if d['id'] == str(doc.id)), None)
        self.assertIsNotNone(found_doc)
        self.assertEqual(found_doc['title'], 'मराठी ठराव')
        self.assertTrue(found_doc['is_fallback'])

        # 2. Notice with only Marathi translation
        notice = Notice.objects.create(
            notice_type='statutory',
            urgency='standard',
            reference_number='GP/2026/NOT-MR',
        )
        ntrans = NoticeTranslation.objects.create(
            notice=notice,
            language_code='mr',
            status='published',
        )
        nrev = NoticeRevision.objects.create(
            translation=ntrans,
            revision_number=1,
            title='मराठी सूचना',
            summary='मराठी सारांश',
            body_markdown='मराठी तपशील',
            editorial_status='approved',
            created_by=self.super_admin,
        )
        ntrans.current_approved_revision = nrev
        ntrans.save()

        notice_resp = client.get('/api/notices/?lang=en&fallback=1')
        self.assertEqual(notice_resp.status_code, 200)
        notice_data = notice_resp.json()
        found_notice = next((n for n in notice_data['results'] if n['id'] == str(notice.id)), None)
        self.assertIsNotNone(found_notice)
        self.assertEqual(found_notice['title'], 'मराठी सूचना')
        self.assertTrue(found_notice['is_fallback'])

        # 3. Event with only Marathi translation
        event = PanchayatEvent.objects.create(
            event_type='gram_sabha',
            status='published',
            start_datetime=timezone.now() + timedelta(days=2),
            end_datetime=timezone.now() + timedelta(days=2, hours=2),
            venue_mr='ग्रामपंचायत सभागृह',
            is_published=True,
            created_by=self.super_admin,
        )
        EventTranslation.objects.create(
            event=event,
            language_code='mr',
            title='मराठी सभा',
            agenda='मराठी अजेंडा',
        )

        event_resp = client.get('/events/?lang=en&fallback=1')
        self.assertEqual(event_resp.status_code, 200)
        event_data = event_resp.json()
        found_event = next((e for e in event_data['results'] if e['id'] == str(event.id)), None)
        self.assertIsNotNone(found_event)
        self.assertEqual(found_event['title'], 'मराठी सभा')
        self.assertTrue(found_event['is_fallback'])

    def test_public_notice_summary_and_body_preview_derivation(self):
        """
        Task 1 Verification:
        - Notice with explicit summary displays that summary.
        - Notice without explicit summary derives safe, clean preview from body_markdown.
        - Notice detail API returns full body_markdown and attachments.
        """
        client = Client(HTTP_HOST='127.0.0.1')

        # 1. Notice with explicit summary
        notice_explicit = Notice.objects.create(
            notice_type='statutory',
            urgency='standard',
            reference_number='NOT-EXP-01',
            effective_from=timezone.now() - timedelta(days=1),
        )
        trans1 = NoticeTranslation.objects.create(
            notice=notice_explicit,
            language_code='mr',
            slug=f"not-exp-{notice_explicit.id.hex}",
            status='published',
        )
        rev1 = NoticeRevision.objects.create(
            translation=trans1,
            revision_number=1,
            title='पाणी पुरवठा दुरुस्ती सूचना',
            summary='गावातील पाणीपुरवठा मुख्य जलवाहिनीच्या दुरुस्तीमुळे उद्या बंद राहील.',
            body_markdown='# महत्त्वाची सूचना\n\nउद्या सकाळी ८ ते दुपारी २ या वेळेत जलवाहिनी दुरुस्ती काम चालेल.',
            editorial_status='approved',
            created_by=self.super_admin,
        )
        trans1.current_approved_revision = rev1
        trans1.save()

        # 2. Notice without explicit summary (only body_markdown)
        notice_body_only = Notice.objects.create(
            notice_type='gram_sabha',
            urgency='urgent',
            reference_number='NOT-BODY-02',
            effective_from=timezone.now() - timedelta(days=1),
        )
        trans2 = NoticeTranslation.objects.create(
            notice=notice_body_only,
            language_code='mr',
            slug=f"not-body-{notice_body_only.id.hex}",
            status='published',
        )
        rev2 = NoticeRevision.objects.create(
            translation=trans2,
            revision_number=1,
            title='विशेष ग्रामसभा आयोजन',
            summary='',
            body_markdown='## विशेष ग्रामसभा नोटीस\n\n**सर्व नागरिकांना** कळविण्यात येते की ग्रामपंचायतीची विशेष ग्रामसभा सोमवार दिनांक २५ रोजी सकाळी १० वाजता आयोजित करण्यात आली आहे. कृपया उपस्थित राहावे.',
            editorial_status='approved',
            created_by=self.super_admin,
        )
        trans2.current_approved_revision = rev2
        trans2.save()

        # Query public notice listing API
        resp = client.get('/api/notices/?lang=mr')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Check explicit notice
        item1 = next((n for n in data['results'] if n['id'] == str(notice_explicit.id)), None)
        self.assertIsNotNone(item1)
        self.assertEqual(item1['summary'], 'गावातील पाणीपुरवठा मुख्य जलवाहिनीच्या दुरुस्तीमुळे उद्या बंद राहील.')
        self.assertEqual(item1['description'], 'गावातील पाणीपुरवठा मुख्य जलवाहिनीच्या दुरुस्तीमुळे उद्या बंद राहील.')

        # Check body-only notice
        item2 = next((n for n in data['results'] if n['id'] == str(notice_body_only.id)), None)
        self.assertIsNotNone(item2)
        self.assertTrue(len(item2['summary']) > 0)
        self.assertNotIn('##', item2['summary'])
        self.assertNotIn('**', item2['summary'])
        self.assertIn('विशेष ग्रामसभा नोटीस', item2['summary'])
        self.assertIn('सर्व नागरिकांना', item2['summary'])

        # Check public detail view
        detail_resp = client.get(f"/api/notices/{notice_body_only.id}/?lang=mr")
        self.assertEqual(detail_resp.status_code, 200)
        detail_data = detail_resp.json()
        self.assertEqual(detail_data['id'], str(notice_body_only.id))
        self.assertEqual(detail_data['body_markdown'], rev2.body_markdown)
        self.assertTrue(len(detail_data['description']) > 0)

    def test_cms_gallery_album_creation_and_error_handling(self):
        """
        Task 2 Verification:
        - Initial album listing returns 200 with {count, results}.
        - Authorized Super Admin and Operator can create albums.
        - Category aliases ('culture', 'water_supply', 'general') map cleanly without check constraint violation.
        - Duplicate slug produces clean 400 validation error (no HTTP 500).
        - Invalid slug, invalid category, and invalid date return clean 400 validation errors.
        - Anonymous creation is rejected with 401.
        """
        admin_client = self.admin_client
        op_client = self.operator_client
        anon_client = self.anon_client

        # 1. Listing returns 200
        list_resp = admin_client.get('/api/cms/gallery/')
        self.assertEqual(list_resp.status_code, 200)
        self.assertIn('count', list_resp.json())
        self.assertIn('results', list_resp.json())

        # 2. Super Admin creates album with 'infrastructure'
        create_resp1 = admin_client.post(
            '/api/cms/gallery/',
            data=json.dumps({
                'slug': 'test-infra-album',
                'title': 'पायाभूत सुविधा विकास',
                'category': 'infrastructure',
                'description': 'रस्ते व जलसंधारण कामे',
                'event_date': '2026-10-15',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp1.status_code, 201)
        self.assertTrue(create_resp1.json()['success'])
        album1_id = create_resp1.json()['album_id']

        # 3. Operator creates album with alias category 'culture' (must map to 'cultural' without 500)
        create_resp2 = op_client.post(
            '/api/cms/gallery/',
            data=json.dumps({
                'slug': 'test-culture-festival',
                'title': 'सांस्कृतिक महोत्सव २०२६',
                'category': 'culture',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_resp2.status_code, 201)
        self.assertTrue(create_resp2.json()['success'])
        alb2 = GalleryAlbum.objects.get(slug='test-culture-festival')
        self.assertEqual(alb2.category, 'cultural')

        # 4. Duplicate slug returns clean 400, not 500
        dup_resp = admin_client.post(
            '/api/cms/gallery/',
            data=json.dumps({
                'slug': 'test-infra-album',
                'title': 'Duplicate Slug Album',
                'category': 'infrastructure',
            }),
            content_type='application/json',
        )
        self.assertEqual(dup_resp.status_code, 400)
        self.assertIn('आधीच अस्तित्वात आहे', dup_resp.json()['detail'])

        # 5. Invalid slug format returns clean 400
        inv_slug_resp = admin_client.post(
            '/api/cms/gallery/',
            data=json.dumps({
                'slug': 'Invalid Slug With Spaces!',
                'title': 'Invalid Slug Album',
                'category': 'infrastructure',
            }),
            content_type='application/json',
        )
        self.assertEqual(inv_slug_resp.status_code, 400)

        # 6. Invalid category returns clean 400
        inv_cat_resp = admin_client.post(
            '/api/cms/gallery/',
            data=json.dumps({
                'slug': 'test-inv-cat',
                'title': 'Invalid Category Album',
                'category': 'totally_unknown_category',
            }),
            content_type='application/json',
        )
        self.assertEqual(inv_cat_resp.status_code, 400)

        # 7. Invalid date returns clean 400
        inv_date_resp = admin_client.post(
            '/api/cms/gallery/',
            data=json.dumps({
                'slug': 'test-inv-date',
                'title': 'Invalid Date Album',
                'category': 'infrastructure',
                'event_date': 'not-a-valid-date',
            }),
            content_type='application/json',
        )
        self.assertEqual(inv_date_resp.status_code, 400)

        # 8. Anonymous POST returns 401
        anon_resp = anon_client.post(
            '/api/cms/gallery/',
            data=json.dumps({'slug': 'anon-album', 'title': 'Anon Album'}),
            content_type='application/json',
        )
        self.assertEqual(anon_resp.status_code, 401)

    def test_panchayat_profile_cms_and_sarpanch_office_holder(self):
        """
        Verifies that:
        1. Operator can inspect PanchayatProfile in CMS (GET 200).
        2. Operator CANNOT update PanchayatProfile (PUT 403 Forbidden).
        3. Super Admin (Gram Sevak) CAN update Sarpanch office-holder details (PUT 200).
        4. Public /api/site-config/ immediately reflects the updated Sarpanch name without code changes.
        """
        admin_client = self.admin_client
        operator_client = self.operator_client

        # 1. Operator GET profile
        op_get = operator_client.get('/api/cms/profile/')
        self.assertEqual(op_get.status_code, 200)
        self.assertIn('profile', op_get.json())

        # 2. Operator PUT profile (Forbidden)
        op_put = operator_client.put(
            '/api/cms/profile/',
            data=json.dumps({'sarpanch_name': 'Unauthorized Change'}),
            content_type='application/json',
        )
        self.assertEqual(op_put.status_code, 403)

        # 3. Super Admin PUT profile (Permitted)
        new_sarpanch = 'श्री. शांताराम गायकवाड'
        admin_put = admin_client.put(
            '/api/cms/profile/',
            data=json.dumps({
                'sarpanch_name': new_sarpanch,
                'contact_phone': '02431-224455',
            }),
            content_type='application/json',
        )
        self.assertEqual(admin_put.status_code, 200)
        self.assertEqual(admin_put.json()['profile']['sarpanch_name'], new_sarpanch)

        # 4. Public endpoint reflection
        public_resp = self.client.get('/api/site-config/')
        self.assertEqual(public_resp.status_code, 200)
        self.assertEqual(public_resp.json()['profile']['sarpanch_name'], new_sarpanch)
        self.assertEqual(public_resp.json()['profile']['contact_phone'], '02431-224455')

