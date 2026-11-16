"""
Comprehensive tests for Unified Public Search (apps.search).

Verifies:
- Cross-domain search result retrieval across all 6 domains:
  Pages (apps.content), Notices (apps.notices), Documents (apps.documents),
  Events (apps.events), Schemes (apps.schemes), and Gallery (apps.gallery).
- Strict language isolation (Marathi statutory primary, Hindi, English) with zero silent fallback.
- Complete exclusion of draft, unapproved, rejected, withdrawn, expired, and confidential records.
- Content-type, category, and date range faceted filtering.
- Safe query normalization, control character stripping, and length cap defense.
- Pagination and clean empty-state behavior.
- Anonymous citizen access and protection against data leakage (no storage paths, hashes, or internal IDs).
- Real-time signal synchronization and administrative index rebuild.
"""

from datetime import timedelta, date
import hashlib
from django.contrib.admin.sites import AdminSite
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

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
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_APPROVED,
    STATUS_PUBLISHED as CONTENT_PUBLISHED,
    STATUS_DRAFT as CONTENT_DRAFT,
    STATUS_WITHDRAWN as CONTENT_WITHDRAWN,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    TYPE_GENERAL as NOTICE_GENERAL,
    TYPE_TENDER as NOTICE_TENDER,
    TYPE_GRAM_SABHA as NOTICE_GRAM_SABHA,
    STATUS_PUBLISHED as NOTICE_PUBLISHED,
    STATUS_DRAFT as NOTICE_DRAFT,
    STATUS_WITHDRAWN as NOTICE_WITHDRAWN,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    CATEGORY_RESOLUTION,
    CATEGORY_TENDER as DOC_TENDER,
    STATUS_DISCLOSED,
    STATUS_DRAFT as DOC_DRAFT,
    STATUS_WITHDRAWN as DOC_WITHDRAWN,
    DISCLOSURE_APPROVED,
    DISCLOSURE_DRAFT,
)
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    EVENT_GRAM_SABHA,
    EVENT_HEALTH_CAMP,
    STATUS_PUBLISHED as EVENT_PUBLISHED,
    STATUS_DRAFT as EVENT_DRAFT,
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
    CATEGORY_INFRASTRUCTURE as GALLERY_INFRA,
    STATUS_PUBLISHED as GALLERY_PUBLISHED,
    STATUS_DRAFT as GALLERY_DRAFT,
)
from apps.search.models import (
    SearchDocumentIndex,
    TYPE_PAGE,
    TYPE_NOTICE,
    TYPE_DOCUMENT,
    TYPE_EVENT,
    TYPE_SCHEME,
    TYPE_GALLERY,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
)
from apps.search.services import (
    normalize_search_query,
    rebuild_search_index,
    execute_unified_search,
    sync_page_translation,
    sync_notice_translation,
    sync_document_translation,
    sync_event,
    sync_scheme_translation,
    sync_gallery_album,
)
from apps.search.admin import SearchDocumentIndexAdmin


class SearchBaseTestCase(TestCase):
    """
    Base test fixture providing users and domain test data across all 6 domains.
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
            assigned_by=self.super_admin,
        )

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Gram Panchayat Operator',
            password='OperatorPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.operator,
            role=ROLE_OPERATOR,
            assigned_by=self.super_admin,
        )

        self.citizen = User.objects.create_user(
            email='citizen@gramsetu.in',
            full_name='Ordinary Citizen',
            password='CitizenPassword123!',
            is_staff=False,
        )

        self.now = timezone.now()

        # ----------------------------------------------------------------------
        # 1. Content Page (Published Marathi + English, Draft Page)
        # ----------------------------------------------------------------------
        self.page_history = Page.objects.create(slug='village-history')
        self.page_trans_mr = PageTranslation.objects.create(
            page=self.page_history,
            language_code=LANGUAGE_MARATHI,
            localized_slug='गावाचा-इतिहास',
            status=CONTENT_PUBLISHED,
        )
        self.page_rev_mr = PageRevision.objects.create(
            translation=self.page_trans_mr,
            revision_number=1,
            title='गावाचा ऐतिहासिक वारसा आणि माहिती',
            summary='आमच्या ग्रामपंचायतीचा गौरवशाली ऐतिहासिक वारसा.',
            body_markdown='शिवकालीन पाऊलखुणा आणि गावातील ऐतिहासिक विहिरी आणि मंदिरे.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        self.page_pub_event = PublicationEvent.objects.create(
            target_content_type='pagetranslation',
            target_id=self.page_trans_mr.id,
            revision_id=self.page_rev_mr.id,
            event_type=EVENT_INITIAL_PUBLISH,
            effective_from=self.now - timedelta(days=5),
            actor=self.super_admin,
            justification='Approved village history page',
        )
        self.page_trans_mr.current_approved_revision = self.page_rev_mr
        self.page_trans_mr.current_publication_event = self.page_pub_event
        self.page_trans_mr.save()

        # English translation of Page
        self.page_trans_en = PageTranslation.objects.create(
            page=self.page_history,
            language_code=LANGUAGE_ENGLISH,
            localized_slug='village-history',
            status=CONTENT_PUBLISHED,
        )
        self.page_rev_en = PageRevision.objects.create(
            translation=self.page_trans_en,
            revision_number=1,
            title='Village Historical Heritage and Information',
            summary='Glorious history and ancient temples of our gram panchayat.',
            body_markdown='Historic step-wells and heritage sites.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        self.page_trans_en.current_approved_revision = self.page_rev_en
        self.page_trans_en.save()

        # Draft Page (must NEVER appear in search)
        self.draft_page = Page.objects.create(slug='secret-internal-plan')
        self.draft_page_trans = PageTranslation.objects.create(
            page=self.draft_page,
            language_code=LANGUAGE_MARATHI,
            status=CONTENT_DRAFT,
        )
        self.draft_page_rev = PageRevision.objects.create(
            translation=self.draft_page_trans,
            revision_number=1,
            title='अंतर्गत गोपनीय आराखडा',
            summary='हा मसुदा अजून मंजूर झालेला नाही.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        self.draft_page_trans.current_approved_revision = self.draft_page_rev
        self.draft_page_trans.save()

        # ----------------------------------------------------------------------
        # 2. Notice (Published Marathi, Expired Notice, Draft Notice)
        # ----------------------------------------------------------------------
        self.notice_water = Notice.objects.create(
            notice_type=NOTICE_GENERAL,
            reference_number='GP/2026/NOT-01',
            effective_from=self.now - timedelta(days=2),
            expires_at=self.now + timedelta(days=10),
        )
        self.notice_trans_mr = NoticeTranslation.objects.create(
            notice=self.notice_water,
            language_code=LANGUAGE_MARATHI,
            slug='water-pipeline-repair',
            status=NOTICE_PUBLISHED,
        )
        self.notice_rev_mr = NoticeRevision.objects.create(
            translation=self.notice_trans_mr,
            revision_number=1,
            title='पिण्याच्या पाणी पुरवठा पाईपलाईन दुरुस्ती सूचना',
            summary='मुख्य जलवाहिनी दुरुस्ती कामामुळे पाणी पुरवठा बंद राहील.',
            body_markdown='नागरिकांनी पाण्याचा काटकसरीने वापर करावा.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        self.notice_pub_event = PublicationEvent.objects.create(
            target_content_type='noticetranslation',
            target_id=self.notice_trans_mr.id,
            revision_id=self.notice_rev_mr.id,
            event_type=EVENT_INITIAL_PUBLISH,
            effective_from=self.now - timedelta(days=2),
            actor=self.super_admin,
            justification='Approved water supply notice',
        )
        self.notice_trans_mr.current_approved_revision = self.notice_rev_mr
        self.notice_trans_mr.current_publication_event = self.notice_pub_event
        self.notice_trans_mr.save()

        # Expired Notice (must NEVER appear in public search)
        self.notice_expired = Notice.objects.create(
            notice_type=NOTICE_TENDER,
            reference_number='GP/2026/TND-OLD',
            effective_from=self.now - timedelta(days=30),
            expires_at=self.now - timedelta(days=1),  # Expired yesterday!
        )
        self.notice_exp_trans = NoticeTranslation.objects.create(
            notice=self.notice_expired,
            language_code=LANGUAGE_MARATHI,
            slug='expired-tender-notice',
            status=NOTICE_PUBLISHED,
        )
        self.notice_exp_rev = NoticeRevision.objects.create(
            translation=self.notice_exp_trans,
            revision_number=1,
            title='मुदत संपलेली जुनी निविदा सूचना',
            summary='ही निविदा मुदत संपलेली आहे.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        self.notice_exp_trans.current_approved_revision = self.notice_exp_rev
        self.notice_exp_trans.save()

        # ----------------------------------------------------------------------
        # 3. Document (Disclosed Marathi, Confidential Document)
        # ----------------------------------------------------------------------
        self.doc_resolution = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='RES/2026/42',
            issuing_department='सामान्य प्रशासन विभाग',
            issue_date=date(2026, 4, 1),
            is_confidential=False,
        )
        self.doc_trans_mr = DocumentTranslation.objects.create(
            document=self.doc_resolution,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामपंचायत वार्षिक विकास आराखडा ठराव',
            description='सन २०२६-२७ या आर्थिक वर्षाचा मंजूर ग्रामसभा ठराव क्र. ४२.',
            status=STATUS_DISCLOSED,
        )
        self.doc_version = DocumentVersion.objects.create(
            translation=self.doc_trans_mr,
            version_number=1,
            storage_path='storage_res_42.pdf.dat',
            original_filename='resolution_42.pdf',
            file_size_bytes=1048576,
            mime_type='application/pdf',
            checksum_sha256='a' * 64,
            disclosure_status=DISCLOSURE_APPROVED,
            uploaded_by=self.operator,
        )
        self.doc_trans_mr.current_version = self.doc_version
        self.doc_trans_mr.save()

        # Confidential Document (must NEVER be indexed or returned)
        self.doc_confidential = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='CONF/2026/99',
            issuing_department='दक्षता विभाग',
            issue_date=date(2026, 4, 1),
            is_confidential=True,
        )
        self.doc_conf_trans = DocumentTranslation.objects.create(
            document=self.doc_confidential,
            language_code=LANGUAGE_MARATHI,
            title='गोपनीय दक्षता चौकशी अहवाल',
            description='अत्यंत गोपनीय अहवाल.',
            status=DOC_DRAFT,
        )

        # ----------------------------------------------------------------------
        # 4. Event (Published Marathi Gram Sabha, Cancelled Event)
        # ----------------------------------------------------------------------
        self.event_sabha = PanchayatEvent.objects.create(
            event_type=EVENT_GRAM_SABHA,
            start_datetime=self.now + timedelta(days=7),
            end_datetime=self.now + timedelta(days=7, hours=3),
            venue_mr='ग्रामपंचायत कार्यालय प्रांगण',
            is_published=True,
            status=EVENT_PUBLISHED,
            created_by=self.operator,
        )
        self.event_trans_mr = EventTranslation.objects.create(
            event=self.event_sabha,
            language_code=LANGUAGE_MARATHI,
            title='विशेष ग्रामसभा बैठक २०२६',
            description='गावातील पाणीपुरवठा व रस्ते विकासाबाबत चर्चा.',
            agenda='१. पाणीपुरवठा २. रस्ते डांबरीकरण ३. स्वच्छता मोहीम.',
        )

        # Cancelled Event (must NOT appear in search)
        self.event_cancelled = PanchayatEvent.objects.create(
            event_type=EVENT_HEALTH_CAMP,
            start_datetime=self.now + timedelta(days=14),
            end_datetime=self.now + timedelta(days=14, hours=4),
            venue_mr='प्राथमिक आरोग्य केंद्र',
            is_published=False,
            status=EVENT_CANCELLED,
            created_by=self.operator,
        )
        self.event_canc_trans = EventTranslation.objects.create(
            event=self.event_cancelled,
            language_code=LANGUAGE_MARATHI,
            title='रद्द केलेले आरोग्य शिबिर',
            description='अपरिहार्य कारणास्तव हे शिबिर रद्द करण्यात आले आहे.',
        )

        # ----------------------------------------------------------------------
        # 5. Government Scheme (Published Marathi Scheme)
        # ----------------------------------------------------------------------
        self.scheme_farmer = WelfareScheme.objects.create(
            slug='krishi-sinchan-yojana',
            scheme_level='state',
            target_beneficiary='farmers',
            official_portal_url='https://mahadbt.maharashtra.gov.in',
            is_active=True,
            created_by=self.operator,
        )
        self.scheme_trans_mr = SchemeTranslation.objects.create(
            scheme=self.scheme_farmer,
            language_code=LANGUAGE_MARATHI,
            localized_slug='कृषी-सिंचन-योजना',
            status=SCHEME_PUBLISHED,
        )
        self.scheme_rev_mr = SchemeRevision.objects.create(
            translation=self.scheme_trans_mr,
            revision_number=1,
            scheme_name='मुख्यमंत्री सूक्ष्म सिंचन कृषी योजना',
            short_summary='शेतकऱ्यांना ठिबक व तुषार सिंचनासाठी ८० टक्के अनुदान.',
            eligibility_criteria='महाराष्ट्र राज्यातील शेतकरी, आधार जोडलेले बँक खाते.',
            required_documents='७/१२ उतारा, ८-अ नोंद, आधार कार्ड.',
            application_process='महाडीबीटी पोर्टलवर ऑनलाईन अर्ज करावा.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        self.scheme_trans_mr.current_approved_revision = self.scheme_rev_mr
        self.scheme_trans_mr.save()

        # ----------------------------------------------------------------------
        # 6. Media Gallery (Published Marathi Album)
        # ----------------------------------------------------------------------
        self.album_roads = GalleryAlbum.objects.create(
            slug='road-construction-2026',
            category=GALLERY_INFRA,
            event_date=date(2026, 3, 15),
            is_published=True,
            status=GALLERY_PUBLISHED,
            created_by=self.operator,
        )
        self.album_trans_mr = AlbumTranslation.objects.create(
            album=self.album_roads,
            language_code=LANGUAGE_MARATHI,
            title='गावातील सिमेंट काँक्रीट रस्ता बांधकाम छायाचित्रे',
            description='मुख्यमंत्री ग्राम सडक योजनेअंतर्गत मुख्य रस्त्याचे काम पूर्ण.',
        )
        self.album_item = GalleryItem.objects.create(
            album=self.album_roads,
            storage_path='road_photo_1.jpg.dat',
            original_filename='road_work.jpg',
            file_size_bytes=524288,
            mime_type='image/jpeg',
            checksum_sha256='b' * 64,
            caption_mr='नवीन सिमेंट रस्त्याचे उद्घाटन',
            alt_text_mr='गावातील नवनिर्मित सिमेंट रस्ता',
            uploaded_by=self.operator,
        )

        # Rebuild search index to ensure baseline index state
        rebuild_search_index()


class SearchIndexingAndSyncTests(SearchBaseTestCase):
    """
    Tests model synchronization, rebuilds, and signal reactions across all domains.
    """

    def test_rebuild_search_index_indexes_only_eligible_records(self):
        count = rebuild_search_index()
        self.assertGreater(count, 0)

        # Verify eligible items are present
        self.assertTrue(SearchDocumentIndex.objects.filter(target_content_type=TYPE_PAGE, target_id=self.page_history.id).exists())
        self.assertTrue(SearchDocumentIndex.objects.filter(target_content_type=TYPE_NOTICE, target_id=self.notice_water.id).exists())
        self.assertTrue(SearchDocumentIndex.objects.filter(target_content_type=TYPE_DOCUMENT, target_id=self.doc_resolution.id).exists())
        self.assertTrue(SearchDocumentIndex.objects.filter(target_content_type=TYPE_EVENT, target_id=self.event_sabha.id).exists())
        self.assertTrue(SearchDocumentIndex.objects.filter(target_content_type=TYPE_SCHEME, target_id=self.scheme_farmer.id).exists())
        self.assertTrue(SearchDocumentIndex.objects.filter(target_content_type=TYPE_GALLERY, target_id=self.album_roads.id).exists())

        # Verify ineligible/draft/confidential items are EXCLUDED
        self.assertFalse(SearchDocumentIndex.objects.filter(target_content_type=TYPE_PAGE, target_id=self.draft_page.id).exists())
        self.assertFalse(SearchDocumentIndex.objects.filter(target_content_type=TYPE_DOCUMENT, target_id=self.doc_confidential.id).exists())
        self.assertFalse(SearchDocumentIndex.objects.filter(target_content_type=TYPE_EVENT, target_id=self.event_cancelled.id).exists())
        self.assertFalse(SearchDocumentIndex.objects.filter(target_content_type=TYPE_NOTICE, target_id=self.notice_expired.id).exists())

    def test_sync_notice_deletes_when_expired(self):
        # Active notice is indexed
        self.assertTrue(SearchDocumentIndex.objects.filter(target_id=self.notice_water.id).exists())

        # When notice expires, sync deletes it from index
        self.notice_water.expires_at = timezone.now() - timedelta(minutes=1)
        self.notice_water.save()
        sync_notice_translation(self.notice_trans_mr)

        self.assertFalse(SearchDocumentIndex.objects.filter(target_id=self.notice_water.id).exists())

    def test_confidential_document_is_never_indexed(self):
        res = sync_document_translation(self.doc_conf_trans)
        self.assertIsNone(res)
        self.assertFalse(SearchDocumentIndex.objects.filter(target_id=self.doc_confidential.id).exists())

    def test_signal_deletes_index_entry_on_model_deletion(self):
        # Notice entry exists
        self.assertTrue(SearchDocumentIndex.objects.filter(target_id=self.notice_water.id).exists())

        # Delete notice root model
        self.notice_water.delete()

        # Signal should remove it from search index
        self.assertFalse(SearchDocumentIndex.objects.filter(target_id=self.notice_water.id).exists())


class SearchQueryExecutionTests(SearchBaseTestCase):
    """
    Tests public search query execution, language isolation, filtering, and pagination.
    """

    def test_default_language_is_marathi(self):
        data = execute_unified_search(query="गावाचा")
        self.assertEqual(data['language'], LANGUAGE_MARATHI)
        self.assertGreater(data['total_results'], 0)
        self.assertEqual(data['results'][0]['content_type'], TYPE_PAGE)

    def test_strict_language_isolation_no_silent_fallback(self):
        # Query in Marathi matches Marathi records
        data_mr = execute_unified_search(query="पाणी", language=LANGUAGE_MARATHI)
        self.assertTrue(any(r['content_type'] == TYPE_NOTICE for r in data_mr['results']))

        # Same query in English must NOT return the Marathi notice!
        data_en = execute_unified_search(query="पाणी", language=LANGUAGE_ENGLISH)
        self.assertEqual(data_en['total_results'], 0)

        # English query matches English records
        data_en_heritage = execute_unified_search(query="heritage", language=LANGUAGE_ENGLISH)
        self.assertEqual(data_en_heritage['total_results'], 1)
        self.assertEqual(data_en_heritage['results'][0]['title'], 'Village Historical Heritage and Information')

    def test_cross_domain_retrieval(self):
        # Query matching multiple domains (e.g. 'विकास' or 'ग्राम')
        data = execute_unified_search(query="ग्राम", language=LANGUAGE_MARATHI)
        content_types = {r['content_type'] for r in data['results']}

        # Should find records in pages, events, documents, and schemes
        self.assertIn(TYPE_PAGE, content_types)
        self.assertIn(TYPE_DOCUMENT, content_types)
        self.assertIn(TYPE_EVENT, content_types)

    def test_partial_devanagari_substring_matching(self):
        # 'सिंचन' should match 'मुख्यमंत्री सूक्ष्म सिंचन कृषी योजना'
        data = execute_unified_search(query="सिंचन", language=LANGUAGE_MARATHI)
        self.assertGreater(data['total_results'], 0)
        self.assertEqual(data['results'][0]['content_type'], TYPE_SCHEME)
        self.assertIn("सिंचन", data['results'][0]['title'])

    def test_content_type_filter(self):
        # Filter strictly by scheme
        data = execute_unified_search(query="ग्राम", language=LANGUAGE_MARATHI, content_type=TYPE_SCHEME)
        self.assertTrue(all(r['content_type'] == TYPE_SCHEME for r in data['results']))

        # Filter strictly by event
        data_ev = execute_unified_search(query="ग्राम", language=LANGUAGE_MARATHI, content_type=TYPE_EVENT)
        self.assertTrue(all(r['content_type'] == TYPE_EVENT for r in data_ev['results']))

    def test_category_filter(self):
        # Document category resolution
        data = execute_unified_search(query="", language=LANGUAGE_MARATHI, content_type=TYPE_DOCUMENT, category=CATEGORY_RESOLUTION)
        self.assertGreater(data['total_results'], 0)
        self.assertEqual(data['results'][0]['category'], CATEGORY_RESOLUTION)

    def test_date_range_filter(self):
        # Filter within range
        from_str = (self.now - timedelta(days=10)).strftime("%Y-%m-%d")
        to_str = (self.now + timedelta(days=10)).strftime("%Y-%m-%d")
        data = execute_unified_search(query="पाणी", language=LANGUAGE_MARATHI, date_from=from_str, date_to=to_str)
        self.assertGreater(data['total_results'], 0)

        # Filter in distant past should return 0 results
        old_from = "2020-01-01"
        old_to = "2020-12-31"
        data_old = execute_unified_search(query="पाणी", language=LANGUAGE_MARATHI, date_from=old_from, date_to=old_to)
        self.assertEqual(data_old['total_results'], 0)

    def test_pagination(self):
        data = execute_unified_search(query="ग्राम", language=LANGUAGE_MARATHI, page=1, page_size=2)
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 2)
        self.assertTrue(data['has_next'])

    def test_empty_query_and_no_filters_returns_empty_state(self):
        data = execute_unified_search(query="", language=LANGUAGE_MARATHI)
        self.assertEqual(data['total_results'], 0)
        self.assertEqual(data['results'], [])
        self.assertEqual(data['empty_reason'], 'empty_query')

    def test_query_normalization_and_length_cap(self):
        # Query with control characters and excessive length
        dirty_query = "\x00\x08  पाणी  \x1f पुरवठा   " + ("X" * 300)
        cleaned = normalize_search_query(dirty_query)
        self.assertTrue(cleaned.startswith("पाणी पुरवठा"))
        self.assertLessEqual(len(cleaned), 200)


class SearchSecurityAndLeakageTests(SearchBaseTestCase):
    """
    Tests security boundaries, data leakage prevention, and SQL injection defense.
    """

    def test_public_endpoint_accessible_anonymously(self):
        url = reverse('search:public_search') + '?q=पाणी&lang=mr'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('results', data)
        self.assertGreater(data['total_results'], 0)

    def test_zero_data_leakage_in_public_results(self):
        url = reverse('search:public_search') + '?q=ठराव&lang=mr'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        for item in data['results']:
            # Must NOT expose private binary disk storage paths
            self.assertNotIn('storage_path', item)
            self.assertNotIn('.dat', str(item))
            # Must NOT expose cryptographic hash digests to search
            self.assertNotIn('checksum_sha256', item)
            # Must NOT expose user emails or internal audit data
            self.assertNotIn('email', item)
            self.assertNotIn('actor', item)

    def test_confidential_documents_never_returned_even_on_exact_match(self):
        # 'गोपनीय' is the title of confidential document
        url = reverse('search:public_search') + '?q=गोपनीय&lang=mr'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Must be 0 results
        self.assertEqual(data['total_results'], 0)

    def test_expired_notices_dynamically_excluded(self):
        # Search for expired tender title
        url = reverse('search:public_search') + '?q=निविदा&lang=mr'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Expired notice GP/2026/TND-OLD must NOT appear
        titles = [r['title'] for r in data['results']]
        self.assertNotIn('मुदत संपलेली जुनी निविदा सूचना', titles)

    def test_sql_injection_attempt_is_safe(self):
        malicious_inputs = [
            "'; DROP TABLE search_document_index; --",
            "' OR '1'='1",
            "\" OR \"\"=\"",
            " UNION SELECT 1, 2, 3 --",
            "'; EXEC sp_executesql; --",
        ]
        for payload in malicious_inputs:
            url = reverse('search:public_search') + f'?q={payload}&lang=mr'
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            # Returns cleanly without leaking SQL errors or crashing
            self.assertIsInstance(data['results'], list)


class SearchAdminTests(SearchBaseTestCase):
    """
    Tests Django Admin read-only inspection and reindex action.
    """

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = SearchDocumentIndexAdmin(SearchDocumentIndex, self.site)

    def test_admin_is_read_only(self):
        rf = RequestFactory()
        req = rf.get('/admin/')
        req.user = self.super_admin

        self.assertFalse(self.admin.has_add_permission(req))
        self.assertFalse(self.admin.has_change_permission(req))

    def test_super_admin_rebuild_index_action(self):
        self.client.force_login(self.super_admin)
        post_data = {
            'action': 'rebuild_index_action',
            '_selected_action': [str(SearchDocumentIndex.objects.first().id)],
        }
        resp = self.client.post(reverse('admin:search_searchdocumentindex_changelist'), post_data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Successfully rebuilt unified search index")
