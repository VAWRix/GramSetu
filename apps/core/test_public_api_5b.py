"""
Comprehensive unit and integration tests for Milestone 5B Public Read-Only JSON API.

Verifies:
1. /api/site-config/ response shape, language isolation, active banner, and navigation.
2. /api/content/pages/ list and detail publication gates, revisions, and language isolation.
3. /api/notices/ list and detail pagination, filtering, urgency, and attachments sanitization.
4. /api/documents/ disclosed metadata, confidential document exclusion, and download URL generation.
5. /api/events/, /api/schemes/, /api/gallery/, /api/search/ routing.
6. Deliberate non-wildcard CORS middleware headers and preflight handling.
7. HTTP method enforcement (405 Method Not Allowed on POST/DELETE) and clean 404 error handling.
"""

from datetime import timedelta
import json
from django.test import TestCase, Client
from django.utils import timezone
from apps.identity.models import User
from apps.governance.models import ApprovalRecord, PublicationEvent, EVENT_INITIAL_PUBLISH
from apps.site_config.models import (
    PanchayatProfile,
    SiteNavigation,
    NavigationTranslation,
    EmergencyBanner,
    EmergencyBannerTranslation,
)
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    STATUS_PUBLISHED,
    STATUS_DRAFT,
    STATUS_WITHDRAWN,
    EDITORIAL_APPROVED,
    EDITORIAL_DRAFT,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    TYPE_TENDER,
    TYPE_GENERAL,
    URGENCY_URGENT,
    URGENCY_STANDARD,
    STATUS_PUBLISHED as NOTICE_PUBLISHED,
    STATUS_DRAFT as NOTICE_DRAFT,
    EDITORIAL_APPROVED as NOTICE_APPROVED,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    CATEGORY_RESOLUTION,
    CATEGORY_BUDGET,
    STATUS_DISCLOSED,
    STATUS_DRAFT as DOC_DRAFT,
    DISCLOSURE_APPROVED,
    DISCLOSURE_DRAFT,
)


class PublicApiIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.now = timezone.now()

        # Create staff user for creating records
        self.staff_user = User.objects.create_user(
            email='official@panchayat.gov.in',
            full_name='Panchayat Staff',
            password='TestPassword123!',
        )

    # --------------------------------------------------------------------------
    # 1. Site Configuration API
    # --------------------------------------------------------------------------
    def test_site_config_empty(self):
        """When no profile exists, returns null profile without crashing."""
        res = self.client.get('/api/site-config/?lang=mr')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['language'], 'mr')
        self.assertIsNone(data['profile'])
        self.assertIsNone(data['emergency_banner'])
        self.assertEqual(data['navigation'], [])

    def test_site_config_populated_and_language_isolation(self):
        """Verifies profile localization, active banner, and navigation isolation."""
        profile = PanchayatProfile.objects.create(
            id=1,
            census_code='543210',
            lgd_code='260123',
            district_name_mr='पुणे',
            district_name_en='Pune',
            taluka_name_mr='हवेली',
            taluka_name_en='Haveli',
            panchayat_name_mr='ग्रामपंचायत कोरेगाव',
            panchayat_name_en='Gram Panchayat Koregaon',
            office_address_mr='मु.पो. कोरेगाव',
            office_address_en='At Post Koregaon',
            contact_email='contact@koregaon.gov.in',
            contact_phone='020-24445555',
            sarpanch_name='श्री. पाटील',
            gram_sevak_name='श्री. कुलकर्णी',
        )

        banner = EmergencyBanner.objects.create(
            severity='warning',
            is_active=True,
            created_by=self.staff_user,
        )
        EmergencyBannerTranslation.objects.create(
            banner=banner,
            language_code='mr',
            message='मुसळधार पावसाचा इशारा.',
            action_url='https://mahadma.gov.in',
            action_label='तपशील पहा',
        )

        nav = SiteNavigation.objects.create(
            menu_location='header',
            display_order=1,
            is_active=True,
        )
        NavigationTranslation.objects.create(
            navigation=nav,
            language_code='mr',
            label='मुख्यपृष्ठ',
            url_path='/',
        )

        # 1. Marathi request
        res_mr = self.client.get('/api/site-config/?lang=mr')
        self.assertEqual(res_mr.status_code, 200)
        data_mr = res_mr.json()
        self.assertEqual(data_mr['profile']['district_name'], 'पुणे')
        self.assertEqual(data_mr['profile']['panchayat_name'], 'ग्रामपंचायत कोरेगाव')
        self.assertIsNotNone(data_mr['emergency_banner'])
        self.assertEqual(data_mr['emergency_banner']['message'], 'मुसळधार पावसाचा इशारा.')
        self.assertEqual(len(data_mr['navigation']), 1)
        self.assertEqual(data_mr['navigation'][0]['label'], 'मुख्यपृष्ठ')

        # 2. English request: Banner has no 'en' translation -> must be None (no silent fallback)
        res_en = self.client.get('/api/site-config/?lang=en')
        self.assertEqual(res_en.status_code, 200)
        data_en = res_en.json()
        self.assertEqual(data_en['profile']['district_name'], 'Pune')
        self.assertEqual(data_en['profile']['panchayat_name'], 'Gram Panchayat Koregaon')
        self.assertIsNone(data_en['emergency_banner'], "Emergency banner without English copy must not silently fallback.")
        self.assertEqual(len(data_en['navigation']), 0, "Navigation without English translation must not be included.")

    # --------------------------------------------------------------------------
    # 2. Informational Content Pages API
    # --------------------------------------------------------------------------
    def test_content_pages_list_and_detail(self):
        page = Page.objects.create(slug='village-history', display_order=1)
        trans_mr = PageTranslation.objects.create(
            page=page,
            language_code='mr',
            localized_slug='गाव-इतिहास',
            status=STATUS_PUBLISHED,
        )
        rev = PageRevision.objects.create(
            translation=trans_mr,
            revision_number=1,
            title='गावाचा ऐतिहासिक वारसा',
            summary='कोरेगाव गावाचा प्राचीन इतिहास',
            body_markdown='# इतिहास\n\nगावाची स्थापना पेशवेकाळात झाली.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.staff_user,
        )
        trans_mr.current_approved_revision = rev
        trans_mr.save()

        # Draft page (must never leak)
        draft_page = Page.objects.create(slug='draft-initiatives')
        trans_draft = PageTranslation.objects.create(
            page=draft_page,
            language_code='mr',
            localized_slug='मसुदा',
            status=STATUS_DRAFT,
        )
        rev_draft = PageRevision.objects.create(
            translation=trans_draft,
            revision_number=1,
            title='अप्रकाशित मसुदा',
            summary='मसुदा',
            body_markdown='गुप्त माहिती',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.staff_user,
        )
        trans_draft.current_approved_revision = rev_draft
        trans_draft.save()

        # 1. List API
        res_list = self.client.get('/api/content/pages/?lang=mr')
        self.assertEqual(res_list.status_code, 200)
        data_list = res_list.json()
        self.assertEqual(data_list['count'], 1)
        self.assertEqual(data_list['results'][0]['slug'], 'village-history')
        self.assertEqual(data_list['results'][0]['title'], 'गावाचा ऐतिहासिक वारसा')

        # 2. Detail API by ASCII slug
        res_det = self.client.get('/api/content/pages/village-history/?lang=mr')
        self.assertEqual(res_det.status_code, 200)
        data_det = res_det.json()
        self.assertEqual(data_det['title'], 'गावाचा ऐतिहासिक वारसा')
        self.assertIn('पेशवेकाळात', data_det['body_markdown'])

        # 3. Detail API by Localized Devanagari slug
        res_det_loc = self.client.get('/api/content/pages/गाव-इतिहास/?lang=mr')
        self.assertEqual(res_det_loc.status_code, 200)

        # 4. English request (translation does not exist) -> Strict 404
        res_det_en = self.client.get('/api/content/pages/village-history/?lang=en')
        self.assertEqual(res_det_en.status_code, 404)

        # 5. Draft page -> Strict 404
        res_draft = self.client.get('/api/content/pages/draft-initiatives/?lang=mr')
        self.assertEqual(res_draft.status_code, 404)

    # --------------------------------------------------------------------------
    # 3. Notices API
    # --------------------------------------------------------------------------
    def test_notices_list_and_detail(self):
        notice = Notice.objects.create(
            notice_type=TYPE_TENDER,
            urgency=URGENCY_URGENT,
            reference_number='GP/2026/TND-01',
            effective_from=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=15),
        )
        trans = NoticeTranslation.objects.create(
            notice=notice,
            language_code='mr',
            status=NOTICE_PUBLISHED,
        )
        attachments_payload = [
            {'title': 'निविदा अटी', 'original_filename': 'tender_terms.pdf', 'file_size_bytes': 204800, 'mime_type': 'application/pdf', 'internal_path': '/secret/path/to/leak.dat'}
        ]
        rev = NoticeRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='पाणी पुरवठा योजना निविदा',
            summary='गाव पाणी पुरवठा दुरुस्ती कामाची जाहीर निविदा.',
            body_markdown='सविस्तर अटी व शर्ती खालीलप्रमाणे.',
            attachments_metadata=attachments_payload,
            editorial_status=NOTICE_APPROVED,
            created_by=self.staff_user,
        )
        trans.current_approved_revision = rev
        trans.save()

        # 1. List API
        res_list = self.client.get('/api/notices/?lang=mr&type=tender')
        self.assertEqual(res_list.status_code, 200)
        data_list = res_list.json()
        self.assertEqual(data_list['count'], 1)
        self.assertEqual(data_list['results'][0]['reference_number'], 'GP/2026/TND-01')
        self.assertEqual(data_list['results'][0]['urgency'], 'urgent')

        # 2. Detail API
        res_det = self.client.get(f'/api/notices/{notice.id}/?lang=mr')
        self.assertEqual(res_det.status_code, 200)
        data_det = res_det.json()
        self.assertEqual(data_det['title'], 'पाणी पुरवठा योजना निविदा')
        self.assertEqual(len(data_det['attachments']), 1)
        self.assertEqual(data_det['attachments'][0]['filename'], 'tender_terms.pdf')
        # Crucial security verification: internal disk path is NEVER leaked
        self.assertNotIn('internal_path', data_det['attachments'][0])

        # 3. Filter by wrong type returns 0 items
        res_empty = self.client.get('/api/notices/?lang=mr&type=general')
        self.assertEqual(res_empty.json()['count'], 0)

    # --------------------------------------------------------------------------
    # 4. Disclosed Documents API
    # --------------------------------------------------------------------------
    def test_documents_list_and_detail(self):
        doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='GP/2026/RES-12',
            issuing_department='ग्रामपंचायत प्रशासन',
            is_confidential=False,
            retention_hold=False,
        )
        trans = DocumentTranslation.objects.create(
            document=doc,
            language_code='mr',
            slug='gram-sabha-res-12',
            title='ग्रामसभा ठराव क्र. १२',
            description='गावातील रस्ते काँक्रीटीकरण ठराव.',
            status=STATUS_DISCLOSED,
        )
        ver = DocumentVersion.objects.create(
            translation=trans,
            version_number=1,
            storage_path='0192a83f-mock-sha.dat',
            original_filename='resolution_12_approved.pdf',
            file_size_bytes=1048576,
            mime_type='application/pdf',
            checksum_sha256='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            disclosure_status=DISCLOSURE_APPROVED,
            uploaded_by=self.staff_user,
        )
        trans.current_version = ver
        trans.save()

        # Confidential Document (must NEVER be exposed)
        conf_doc = Document.objects.create(
            category=CATEGORY_BUDGET,
            reference_number='GP/2026/CONF-01',
            issuing_department='लेखा विभाग',
            is_confidential=True,
        )
        conf_trans = DocumentTranslation.objects.create(
            document=conf_doc,
            language_code='mr',
            title='गोपनीय अहवाल',
            status=DOC_DRAFT,
        )

        # 1. List API
        res_list = self.client.get('/api/documents/?lang=mr')
        self.assertEqual(res_list.status_code, 200)
        data_list = res_list.json()
        self.assertEqual(data_list['count'], 1)
        self.assertEqual(data_list['results'][0]['reference_number'], 'GP/2026/RES-12')
        self.assertEqual(data_list['results'][0]['download_url'], f'/documents/{trans.id}/download/')
        # Crucial security check: internal storage_path is omitted
        self.assertNotIn('storage_path', data_list['results'][0])

        # 2. Detail API
        res_det = self.client.get(f'/api/documents/{doc.id}/?lang=mr')
        self.assertEqual(res_det.status_code, 200)
        data_det = res_det.json()
        self.assertEqual(data_det['title'], 'ग्रामसभा ठराव क्र. १२')
        self.assertEqual(data_det['file_size_bytes'], 1048576)

        # 3. Confidential Document Detail -> Strict 404
        res_conf = self.client.get(f'/api/documents/{conf_doc.id}/?lang=mr')
        self.assertEqual(res_conf.status_code, 404)

    # --------------------------------------------------------------------------
    # 5. Events, Schemes, Gallery, and Search API Routes
    # --------------------------------------------------------------------------
    def test_events_schemes_gallery_search_api_routes(self):
        """Verifies that the /api/ mounted domain endpoints respond with JSON."""
        res_events = self.client.get('/api/events/?lang=mr')
        self.assertEqual(res_events.status_code, 200)
        self.assertIn('results', res_events.json())

        res_schemes = self.client.get('/api/schemes/?lang=mr')
        self.assertEqual(res_schemes.status_code, 200)
        self.assertIn('results', res_schemes.json())

        res_gallery = self.client.get('/api/gallery/?lang=mr')
        self.assertEqual(res_gallery.status_code, 200)
        self.assertIn('results', res_gallery.json())

        res_search = self.client.get('/api/search/?q=ग्राम&lang=mr')
        self.assertEqual(res_search.status_code, 200)
        self.assertIn('results', res_search.json())

    # --------------------------------------------------------------------------
    # 6. Deliberate CORS Middleware Tests
    # --------------------------------------------------------------------------
    def test_deliberate_cors_trusted_origin(self):
        """Allowed origin receives specific echo and credentials header (never wildcard)."""
        res = self.client.get('/api/site-config/', HTTP_ORIGIN='http://localhost:3000')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), 'http://localhost:3000')
        self.assertEqual(res.headers.get('Access-Control-Allow-Credentials'), 'true')
        self.assertNotEqual(res.headers.get('Access-Control-Allow-Origin'), '*')

    def test_deliberate_cors_untrusted_origin(self):
        """Untrusted origin receives no CORS headers."""
        res = self.client.get('/api/site-config/', HTTP_ORIGIN='https://malicious-portal.com')
        self.assertEqual(res.status_code, 200)
        self.assertNotIn('Access-Control-Allow-Origin', res.headers)

    def test_deliberate_cors_preflight(self):
        """Preflight OPTIONS request returns 200 with allowed methods."""
        res = self.client.options('/api/site-config/', HTTP_ORIGIN='http://localhost:3000')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), 'http://localhost:3000')
        self.assertEqual(res.headers.get('Access-Control-Allow-Methods'), 'GET, HEAD, OPTIONS')

    # --------------------------------------------------------------------------
    # 7. Safe Error Handling & Method Restrictions
    # --------------------------------------------------------------------------
    def test_disallowed_methods_return_405(self):
        """Public read-only endpoints reject write attempts with 405 Method Not Allowed."""
        res_post = self.client.post('/api/site-config/', {})
        self.assertEqual(res_post.status_code, 405)

        res_delete = self.client.delete('/api/content/pages/')
        self.assertEqual(res_delete.status_code, 405)

        res_post_notice = self.client.post('/api/notices/', {})
        self.assertEqual(res_post_notice.status_code, 405)

    def test_invalid_uuid_returns_404_not_500(self):
        """Malformed identifiers return 404 rather than unhandled server errors."""
        res = self.client.get('/api/notices/not-a-valid-uuid/?lang=mr')
        self.assertEqual(res.status_code, 404)
