"""
Comprehensive Automated Test Suite for:
1. Super Admin direct publishing and Marathi gallery translation validation.
2. Optional notice deadlines in CMS and public portal.
3. Safe page viewing and revision branching/editing without page ID/slug duplication.
4. Welfare scheme details (department, contact_details) and anonymous access control.
5. Content-aware immutable audit trail and historical snapshots.
"""

import json
from datetime import timedelta
from django.test import TestCase, Client
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
    STATUS_PUBLISHED as NOTICE_STATUS_PUBLISHED,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
    STATUS_PUBLISHED as SCHEME_STATUS_PUBLISHED,
    STATUS_DRAFT as SCHEME_STATUS_DRAFT,
)
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
    STATUS_PUBLISHED as GALLERY_STATUS_PUBLISHED,
    STATUS_DRAFT as GALLERY_STATUS_DRAFT,
)


class GovernanceAndContentEnhancementTests(TestCase):
    """
    Integration tests covering all 6 feature areas.
    """

    def setUp(self):
        # 1. Users: Super Admin (Gram Sevak) & Operator (Computer Operator)
        self.super_admin = User.objects.create_user(
            email='gram.sevak@gramsetu.gov.in',
            full_name='Gram Sevak Patil',
            password='AdminPassword123!',
        )
        RoleAssignment.objects.create(user=self.super_admin, role=ROLE_SUPER_ADMIN)

        self.operator = User.objects.create_user(
            email='operator@gramsetu.gov.in',
            full_name='Computer Operator Kadam',
            password='OperatorPassword123!',
        )
        RoleAssignment.objects.create(user=self.operator, role=ROLE_OPERATOR)

        self.citizen = User.objects.create_user(
            email='citizen@example.com',
            full_name='Citizen User',
            password='CitizenPassword123!',
        )

        # 2. MFA Verified Clients
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
    # 1. Super Admin Direct Publishing & Marathi Validation (Gallery)
    # ==========================================================================

    def test_gallery_super_admin_direct_publish_success(self):
        """Super Admin can directly publish an album containing at least one photo item."""
        # Create album container
        album = GalleryAlbum.objects.create(
            slug='village-fair-2026',
            category='cultural',
            status=GALLERY_STATUS_DRAFT,
            created_by=self.super_admin,
        )
        AlbumTranslation.objects.create(
            album=album,
            language_code='mr',
            title='ग्रामिण यात्रा महोत्सव २०२६',
            description='वार्षिक ग्रामिण यात्रा व सांस्कृतिक कार्यक्रम.',
        )
        # Add photograph item (required by governance policy)
        GalleryItem.objects.create(
            album=album,
            source_type='link',
            external_url='https://example.gov.in/photo1.jpg',
            storage_path='link-village-fair-2026-1',
            original_filename='fair.jpg',
            file_size_bytes=1024,
            mime_type='image/jpeg',
            checksum_sha256='0' * 64,
            caption_mr='यात्रा मुख्य प्रवेशद्वार',
            uploaded_by=self.super_admin,
        )

        resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'gallery',
                'action': 'publish',
                'target_id': str(album.id),
                'justification': 'Direct statutory publication by Super Administrator.',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        album.refresh_from_db()
        self.assertTrue(album.is_published)
        self.assertEqual(album.status, GALLERY_STATUS_PUBLISHED)

    def test_gallery_operator_cannot_direct_publish(self):
        """Operator cannot publish gallery albums directly."""
        album = GalleryAlbum.objects.create(
            slug='operator-album',
            category='infrastructure',
            status=GALLERY_STATUS_DRAFT,
            created_by=self.operator,
        )
        AlbumTranslation.objects.create(
            album=album,
            language_code='mr',
            title='ऑपरेटर अल्बम',
            description='मसुदा वर्णन.',
        )
        resp = self.operator_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'gallery',
                'action': 'publish',
                'target_id': str(album.id),
                'justification': 'Operator attempting unauthorized publication.',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_gallery_primary_language_creation_and_validation(self):
        """Gallery album creation supports English primary without requiring Marathi."""
        payload_en = {
            'slug': 'english-only-album',
            'title_en': 'English Only Album',
            'description_en': 'Infrastructure development photos in English',
            'primary_language': 'en',
            'category': 'infrastructure',
        }
        resp = self.admin_client.post(
            reverse('api:cms:gallery_collection'),
            data=json.dumps(payload_en),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()['success'])

        # Missing primary title fails with 400
        payload_invalid = {
            'slug': 'invalid-primary-album',
            'primary_language': 'mr',
            'title_mr': '',
            'category': 'infrastructure',
        }
        resp_inv = self.admin_client.post(
            reverse('api:cms:gallery_collection'),
            data=json.dumps(payload_invalid),
            content_type='application/json',
        )
        self.assertEqual(resp_inv.status_code, 400)
        detail_msg = resp_inv.json().get('detail', '')
        self.assertTrue('title' in detail_msg.lower() or 'अल्बम शीर्षक' in detail_msg)

    # ==========================================================================
    # 2. Optional Notice Deadlines
    # ==========================================================================

    def test_notice_deadline_creation_and_public_rendering(self):
        """Notice with a future deadline renders deadline and does not hide when deadline passes."""
        future_deadline = timezone.now() + timedelta(days=5)
        payload = {
            'title': 'निविदा सूचना २०२६',
            'description': 'रस्ता दुरुस्तीसाठी ई-निविदा मागविण्यात येत आहेत.',
            'notice_type': 'tender',
            'urgency': 'routine',
            'reference_number': 'TND-2026-99',
            'deadline': future_deadline.isoformat(),
            'language_code': 'mr',
            'publish_now': True,
        }
        resp = self.admin_client.post(
            reverse('api:cms:notices_collection'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        notice_id = resp.json()['notice_id']

        notice = Notice.objects.get(id=notice_id)
        self.assertIsNotNone(notice.deadline)
        self.assertTrue(notice.has_deadline)
        self.assertFalse(notice.is_deadline_passed)

        # Check Public List API
        pub_resp = self.anon_client.get(reverse('api:notice_list') + '?lang=mr')
        self.assertEqual(pub_resp.status_code, 200)
        items = pub_resp.json()['results']
        matched = [i for i in items if i['id'] == str(notice.id)]
        self.assertEqual(len(matched), 1)
        self.assertTrue(matched[0]['has_deadline'])
        self.assertFalse(matched[0]['is_deadline_passed'])
        self.assertIsNotNone(matched[0]['deadline'])

        # Now simulate passed deadline: notice must still be publicly visible!
        notice.deadline = timezone.now() - timedelta(hours=2)
        notice.save()
        self.assertTrue(notice.is_deadline_passed)

        pub_resp_after = self.anon_client.get(reverse('api:notice_list') + '?lang=mr')
        self.assertEqual(pub_resp_after.status_code, 200)
        items_after = pub_resp_after.json()['results']
        matched_after = [i for i in items_after if i['id'] == str(notice.id)]
        self.assertEqual(len(matched_after), 1, "Notice must NOT be hidden merely because deadline has passed.")
        self.assertTrue(matched_after[0]['is_deadline_passed'])

    # ==========================================================================
    # 3. Page Revision Branching & Identity Preservation
    # ==========================================================================

    def test_page_revision_branching_preserves_page_identity(self):
        """Editing an existing published page creates a new draft revision without duplicating page ID or slug."""
        # Setup initial published page
        page = Page.objects.create(
            slug='about-panchayat-history',
        )
        trans = PageTranslation.objects.create(
            page=page,
            language_code='mr',
            localized_slug='about-panchayat-history',
            status=STATUS_PUBLISHED,
        )
        rev1 = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='ग्रामपंचायत इतिहास (मूळ)',
            summary='ग्रामपंचायतीची मूळ माहिती.',
            body_markdown='# इतिहास\n\nगावाचा संक्षिप्त इतिहास.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.super_admin,
        )
        rev1.content_hash = rev1.calculate_hash()
        rev1.save()
        trans.current_approved_revision = rev1
        trans.save()

        # Operator branches new revision
        branch_resp = self.operator_client.post(
            reverse('api:cms:page_detail_revisions', kwargs={'page_id': str(page.id)}),
            data=json.dumps({
                'title': 'ग्रामपंचायत इतिहास (सुधारित आवृत्ती)',
                'summary': 'नवीन सुधारित माहिती.',
                'body_markdown': '# इतिहास\n\nसुधारित माहिती व अद्यतने.',
                'language_code': 'mr',
            }),
            content_type='application/json',
        )
        self.assertEqual(branch_resp.status_code, 201)

        # Verify page ID and slug are preserved
        self.assertEqual(Page.objects.filter(slug='about-panchayat-history').count(), 1)
        page.refresh_from_db()
        self.assertEqual(page.translations.count(), 1)
        trans.refresh_from_db()
        self.assertEqual(trans.revisions.count(), 2)

        rev2 = trans.revisions.order_by('-revision_number').first()
        self.assertEqual(rev2.revision_number, 2)
        self.assertEqual(rev2.editorial_status, EDITORIAL_DRAFT)

        # Public page must still show rev1
        pub_resp = self.anon_client.get(reverse('api:page_detail', kwargs={'slug': 'about-panchayat-history'}))
        self.assertEqual(pub_resp.status_code, 200)
        self.assertEqual(pub_resp.json()['title'], 'ग्रामपंचायत इतिहास (मूळ)')

        # Super Admin directly publishes rev2
        pub_resp2 = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'page',
                'action': 'publish',
                'target_id': str(trans.id),
                'revision_id': str(rev2.id),
                'justification': 'Super admin publishing revision 2.',
            }),
            content_type='application/json',
        )
        self.assertEqual(pub_resp2.status_code, 200)

        # Now public page shows rev2
        pub_resp_updated = self.anon_client.get(reverse('api:page_detail', kwargs={'slug': 'about-panchayat-history'}))
        self.assertEqual(pub_resp_updated.status_code, 200)
        self.assertEqual(pub_resp_updated.json()['title'], 'ग्रामपंचायत इतिहास (सुधारित आवृत्ती)')

    # ==========================================================================
    # 4. Welfare Scheme Details & Anonymous Access Control
    # ==========================================================================

    def test_welfare_scheme_details_and_access_gate(self):
        """Welfare scheme stores department and contact details; anonymous visitors cannot access draft schemes."""
        payload = {
            'slug': 'organic-farming-subsidy',
            'title': 'सेंद्रिय शेती अनुदान योजना',
            'scheme_level': 'state',
            'target_beneficiary': 'farmers',
            'department': 'कृषी विभाग, महाराष्ट्र शासन',
            'contact_details': 'टोल फ्री १८००-१८०-१५५१',
            'short_description': 'सेंद्रिय खत व कीटकनाशकांसाठी अनुदान.',
            'benefits_summary': 'प्रति हेक्टरी रु. १०,०००/-',
            'eligibility_criteria': 'सर्व अल्पभूधारक शेतकरी पात्र.',
            'required_documents': '७/१२, आधार कार्ड, बँक पासबुक.',
            'application_process': 'आपले सरकार पोर्टलवर ऑनलाइन अर्ज.',
            'language_code': 'mr',
            'publish_now': False,  # Draft
        }
        create_resp = self.operator_client.post(
            reverse('api:cms:schemes_collection'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(create_resp.status_code, 201)

        # Anonymous user cannot view draft scheme
        anon_resp = self.anon_client.get(reverse('api:scheme_detail', kwargs={'identifier': 'organic-farming-subsidy'}))
        self.assertEqual(anon_resp.status_code, 404, "Draft schemes must return 404 to anonymous visitors.")

        # Super Admin publishes scheme
        scheme = WelfareScheme.objects.get(slug='organic-farming-subsidy')
        trans = scheme.translations.first()
        rev = trans.revisions.first()

        pub_resp = self.admin_client.post(
            reverse('api:cms:governance_action'),
            data=json.dumps({
                'entity_type': 'scheme',
                'action': 'publish',
                'target_id': str(trans.id),
                'revision_id': str(rev.id),
                'justification': 'Publishing organic farming state scheme.',
            }),
            content_type='application/json',
        )
        self.assertEqual(pub_resp.status_code, 200)

        # Anonymous user can now view published scheme with full details
        anon_pub_resp = self.anon_client.get(reverse('api:scheme_detail', kwargs={'identifier': 'organic-farming-subsidy'}))
        self.assertEqual(anon_pub_resp.status_code, 200)
        data = anon_pub_resp.json()
        self.assertEqual(data['department'], 'कृषी विभाग, महाराष्ट्र शासन')
        self.assertEqual(data['contact_details'], 'टोल फ्री १८००-१८०-१५५१')
        self.assertEqual(data['target_beneficiary'], 'farmers')

    # ==========================================================================
    # 5. Content-Aware Immutable Audit Trail
    # ==========================================================================

    def test_audit_log_captures_content_title_snapshot_and_metadata(self):
        """Governance actions stamp content_title_snapshot and API enriches historical records."""
        # 1. Trigger an approval action to ensure approval record exists
        appr = ApprovalRecord.objects.filter(approved_by=self.super_admin).order_by('-approved_at').first()
        if not appr:
            # Create a published page revision
            page = Page.objects.create(slug='audit-test-page')
            trans = PageTranslation.objects.create(page=page, language_code='mr', localized_slug='audit-test-page')
            rev = PageRevision.objects.create(
                translation=trans,
                revision_number=1,
                title='ऑडिट चाचणी पृष्ठ',
                summary='ऑडिट नोंदीसाठी चाचणी.',
                body_markdown='मजकूर',
                editorial_status=EDITORIAL_DRAFT,
                created_by=self.operator,
            )
            rev.content_hash = rev.calculate_hash()
            rev.save()
            self.admin_client.post(
                reverse('api:cms:governance_action'),
                data=json.dumps({
                    'entity_type': 'page',
                    'action': 'publish',
                    'target_id': str(trans.id),
                    'revision_id': str(rev.id),
                    'justification': 'Publishing page to create audit entry.',
                }),
                content_type='application/json',
            )
            appr = ApprovalRecord.objects.filter(approved_by=self.super_admin).order_by('-approved_at').first()

        self.assertIsNotNone(appr)
        self.assertTrue(len(appr.content_title_snapshot) > 0)

        # 2. Check publication event
        pub = PublicationEvent.objects.filter(actor=self.super_admin).order_by('-created_at').first()
        self.assertIsNotNone(pub)
        self.assertTrue(len(pub.content_title_snapshot) > 0)

        # 3. Query Audit API with filters
        audit_resp = self.admin_client.get(reverse('api:cms:audit_logs') + '?content_type=page')
        self.assertEqual(audit_resp.status_code, 200)
        results = audit_resp.json()['results']
        self.assertTrue(len(results) > 0)

        entry = results[0]
        self.assertIn('content_title', entry)
        self.assertIn('content_type_display', entry)
        self.assertIn('content_link', entry)
        self.assertIn('actor_role_display', entry)
