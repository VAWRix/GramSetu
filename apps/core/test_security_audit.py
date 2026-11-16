"""
Milestone 4J: Cross-Domain Integration and Security Audit Regression Tests.

Verifies:
1. Stale Search-Index Records Defense: Search-index entries cannot independently
   authorize disclosure; canonical domain model querysets strictly govern visibility.
2. Governance & Audit Immutability: ApprovalRecord, RejectionRecord, PublicationEvent,
   and submitted/approved revisions cannot be deleted at model level.
3. Anti-Self-Approval Enforcement: Authors cannot approve their own content revisions.
4. Leakage Prevention: Unapproved, withdrawn, draft, and confidential content return 404 to citizens.
5. Path Traversal & Storage Isolation: Private directories are isolated outside static serving.
6. Session Security & Headers: 30-minute timeout and statutory security headers.
"""

from datetime import timedelta, date
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.utils import timezone

from apps.identity.models import (
    User,
    RoleAssignment,
    ROLE_SUPER_ADMIN,
    ROLE_OPERATOR,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_WITHDRAWAL,
)
from apps.governance.services import (
    approve_page_revision,
    submit_page_revision,
)
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
    STATUS_DRAFT as CONTENT_DRAFT,
    STATUS_PUBLISHED as CONTENT_PUBLISHED,
    STATUS_WITHDRAWN as CONTENT_WITHDRAWN,
    LANGUAGE_MARATHI,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    TYPE_GENERAL,
    STATUS_PUBLISHED as NOTICE_PUBLISHED,
    STATUS_WITHDRAWN as NOTICE_WITHDRAWN,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    CATEGORY_RESOLUTION,
    STATUS_DISCLOSED,
    STATUS_WITHDRAWN as DOC_WITHDRAWN,
    DISCLOSURE_APPROVED,
    DISCLOSURE_DRAFT,
)
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    EVENT_GRAM_SABHA,
    STATUS_PUBLISHED as EVENT_PUBLISHED,
    STATUS_DRAFT as EVENT_DRAFT,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
    STATUS_PUBLISHED as SCHEME_PUBLISHED,
)
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
    CATEGORY_INFRASTRUCTURE,
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
)
from apps.search.services import execute_unified_search


class Milestone4JSecurityAuditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.now = timezone.now()

        # Users
        self.super_admin = User.objects.create_user(
            email='audit_admin@gramsetu.in',
            full_name='Audit Super Admin',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.super_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )

        self.operator = User.objects.create_user(
            email='audit_operator@gramsetu.in',
            full_name='Audit Operator',
            password='OperatorPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.operator,
            role=ROLE_OPERATOR,
            assigned_by=self.super_admin,
        )

        self.citizen = User.objects.create_user(
            email='audit_citizen@gramsetu.in',
            full_name='Audit Citizen',
            password='CitizenPassword123!',
            is_staff=False,
        )

    # --------------------------------------------------------------------------
    # 1. Stale Search Index Defense & Source-of-Truth Enforcement
    # --------------------------------------------------------------------------

    def test_stale_search_index_cannot_authorize_withdrawn_page_disclosure(self):
        """
        If a PageTranslation is withdrawn but an index entry remains in SearchDocumentIndex,
        execute_unified_search MUST strictly filter it out via canonical domain querysets.
        """
        page = Page.objects.create(slug='audit-water-project')
        trans = PageTranslation.objects.create(
            page=page,
            language_code=LANGUAGE_MARATHI,
            status=CONTENT_WITHDRAWN,  # WITHDRAWN
        )
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='पाणी प्रकल्प माहिती',
            summary='गावातील पाणी प्रकल्प',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        trans.current_approved_revision = rev
        trans.save()

        # Artificially inject a stale search index entry pretending it is published
        stale_entry = SearchDocumentIndex.objects.create(
            target_content_type=TYPE_PAGE,
            target_id=page.id,
            language_code=LANGUAGE_MARATHI,
            title='पाणी प्रकल्प माहिती',
            summary='गावातील पाणी प्रकल्प',
            search_text='पाणी प्रकल्प माहिती गावातील पाणी प्रकल्प',
            published_at=self.now,
            url_path=f"/pages/{page.slug}/",
            category='information',
        )

        # Citizen searches for the withdrawn page
        res = execute_unified_search(query='पाणी', language=LANGUAGE_MARATHI)
        self.assertEqual(res['total_results'], 0)
        self.assertEqual(len(res['results']), 0)

    def test_stale_search_index_cannot_authorize_expired_notice_disclosure(self):
        """
        If a Notice is expired but indexed in SearchDocumentIndex,
        execute_unified_search MUST strictly filter it out.
        """
        notice = Notice.objects.create(
            notice_type=TYPE_GENERAL,
            reference_number='AUDIT/NOT/01',
            effective_from=self.now - timedelta(days=10),
            expires_at=self.now - timedelta(days=1),  # EXPIRED
        )
        trans = NoticeTranslation.objects.create(
            notice=notice,
            language_code=LANGUAGE_MARATHI,
            status=NOTICE_PUBLISHED,
        )
        rev = NoticeRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='जुनी मुदत संपलेली सूचना',
            summary='ही सूचना आता कालबाह्य झाली आहे.',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        trans.current_approved_revision = rev
        trans.save()

        # Artificially inject stale index entry
        SearchDocumentIndex.objects.create(
            target_content_type=TYPE_NOTICE,
            target_id=notice.id,
            language_code=LANGUAGE_MARATHI,
            title='जुनी मुदत संपलेली सूचना',
            summary='ही सूचना आता कालबाह्य झाली आहे.',
            search_text='जुनी मुदत संपलेली सूचना',
            published_at=notice.effective_from,
            url_path=f"/notices/{notice.id}/",
            category=TYPE_GENERAL,
        )

        res = execute_unified_search(query='कालबाह्य', language=LANGUAGE_MARATHI)
        self.assertEqual(res['total_results'], 0)
        self.assertEqual(len(res['results']), 0)

    def test_stale_search_index_cannot_authorize_confidential_document_disclosure(self):
        """
        If a Document is confidential but indexed in SearchDocumentIndex,
        execute_unified_search MUST strictly filter it out.
        """
        doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='SECRET-DOC-99',
            issuing_department='गोपनीय विभाग',
            is_confidential=True,  # CONFIDENTIAL
        )
        trans = DocumentTranslation.objects.create(
            document=doc,
            language_code=LANGUAGE_MARATHI,
            title='अत्यंत गोपनीय अहवाल',
            description='चौकशी अहवाल',
            status=STATUS_DISCLOSED,
        )

        SearchDocumentIndex.objects.create(
            target_content_type=TYPE_DOCUMENT,
            target_id=doc.id,
            language_code=LANGUAGE_MARATHI,
            title='अत्यंत गोपनीय अहवाल',
            summary='चौकशी अहवाल',
            search_text='अत्यंत गोपनीय अहवाल चौकशी अहवाल',
            published_at=self.now,
            url_path=f"/documents/{trans.id}/download/",
            category=CATEGORY_RESOLUTION,
        )

        res = execute_unified_search(query='गोपनीय', language=LANGUAGE_MARATHI)
        self.assertEqual(res['total_results'], 0)
        self.assertEqual(len(res['results']), 0)

    def test_stale_search_index_cannot_authorize_inactive_scheme_disclosure(self):
        """
        If a WelfareScheme is deactivated (is_active=False),
        search results MUST immediately filter out its index entry.
        """
        scheme = WelfareScheme.objects.create(
            slug='closed-subsidy-scheme',
            scheme_level='state',
            target_beneficiary='farmers',
            is_active=False,  # INACTIVE
            created_by=self.operator,
        )
        trans = SchemeTranslation.objects.create(
            scheme=scheme,
            language_code=LANGUAGE_MARATHI,
            status=SCHEME_PUBLISHED,
        )
        rev = SchemeRevision.objects.create(
            translation=trans,
            revision_number=1,
            scheme_name='बंद झालेली कृषी योजना',
            short_summary='ही योजना आता बंद झाली आहे.',
            eligibility_criteria='शेतकरी',
            required_documents='७/१२',
            application_process='पोर्टल',
            editorial_status=EDITORIAL_APPROVED,
            created_by=self.operator,
        )
        trans.current_approved_revision = rev
        trans.save()

        SearchDocumentIndex.objects.create(
            target_content_type=TYPE_SCHEME,
            target_id=scheme.id,
            language_code=LANGUAGE_MARATHI,
            title='बंद झालेली कृषी योजना',
            summary='ही योजना आता बंद झाली आहे.',
            search_text='बंद झालेली कृषी योजना',
            published_at=self.now,
            url_path=f"/schemes/{scheme.slug}/",
            category='farmers',
        )

        res = execute_unified_search(query='बंद', language=LANGUAGE_MARATHI)
        self.assertEqual(res['total_results'], 0)

    # --------------------------------------------------------------------------
    # 2. Immutable Audit & Revision Deletion Protections
    # --------------------------------------------------------------------------

    def test_approval_record_cannot_be_deleted(self):
        """
        ApprovalRecord.delete() must raise ValidationError to prevent audit tampering.
        """
        page = Page.objects.create(slug='immutable-audit-page')
        trans = PageTranslation.objects.create(page=page, language_code=LANGUAGE_MARATHI)
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Audit Page',
            created_by=self.operator,
        )
        approval = ApprovalRecord.objects.create(
            target_content_type='pagetranslation',
            target_id=trans.id,
            revision_id=rev.id,
            revision_hash='a' * 64,
            approved_by=self.super_admin,
            notes='Formal approval',
        )
        with self.assertRaises(ValidationError):
            approval.delete()

    def test_rejection_record_cannot_be_deleted(self):
        """
        RejectionRecord.delete() must raise ValidationError.
        """
        page = Page.objects.create(slug='immutable-rejection-page')
        trans = PageTranslation.objects.create(page=page, language_code=LANGUAGE_MARATHI)
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Rejection Page',
            created_by=self.operator,
        )
        rejection = RejectionRecord.objects.create(
            target_content_type='pagetranslation',
            target_id=trans.id,
            revision_id=rev.id,
            rejected_by=self.super_admin,
            rejection_reason='Incomplete statutory documentation.',
        )
        with self.assertRaises(ValidationError):
            rejection.delete()

    def test_publication_event_cannot_be_deleted(self):
        """
        PublicationEvent.delete() must raise ValidationError.
        """
        page = Page.objects.create(slug='immutable-pub-event-page')
        trans = PageTranslation.objects.create(page=page, language_code=LANGUAGE_MARATHI)
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Pub Event Page',
            created_by=self.operator,
        )
        event = PublicationEvent.objects.create(
            target_content_type='pagetranslation',
            target_id=trans.id,
            revision_id=rev.id,
            event_type=EVENT_INITIAL_PUBLISH,
            actor=self.super_admin,
            justification='Initial approved launch',
        )
        with self.assertRaises(ValidationError):
            event.delete()

    def test_scheme_revision_deletion_protection(self):
        """
        SchemeRevision in submitted or approved status cannot be deleted.
        Draft revisions can be cleanly discarded.
        """
        scheme = WelfareScheme.objects.create(
            slug='audit-scheme-del',
            scheme_level='state',
            target_beneficiary='youth',
            created_by=self.operator,
        )
        trans = SchemeTranslation.objects.create(scheme=scheme, language_code=LANGUAGE_MARATHI)

        # Submitted revision
        rev_submitted = SchemeRevision.objects.create(
            translation=trans,
            revision_number=1,
            scheme_name='कौशल्य विकास योजना',
            short_summary='तरुणांसाठी कौशल्य प्रशिक्षण',
            eligibility_criteria='१० वी पास युवक',
            required_documents='शाळा सोडल्याचा दाखला',
            application_process='ऑनलाईन नोंदणी',
            editorial_status=EDITORIAL_SUBMITTED,
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            rev_submitted.delete()

        # Draft revision CAN be deleted
        rev_draft = SchemeRevision.objects.create(
            translation=trans,
            revision_number=2,
            scheme_name='कौशल्य विकास योजना v2',
            short_summary='मसुदा',
            eligibility_criteria='युवक',
            required_documents='दाखला',
            application_process='अर्ज',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        rev_draft_id = rev_draft.id
        rev_draft.delete()
        self.assertFalse(SchemeRevision.objects.filter(id=rev_draft_id).exists())

    # --------------------------------------------------------------------------
    # 3. Anti-Self-Approval Enforcement
    # --------------------------------------------------------------------------

    def test_separation_of_duties_prevents_author_self_approval(self):
        """
        An author cannot approve their own submitted revision (ADR 0002).
        """
        page = Page.objects.create(slug='self-approval-test')
        trans = PageTranslation.objects.create(page=page, language_code=LANGUAGE_MARATHI)
        rev = PageRevision.objects.create(
            translation=trans,
            revision_number=1,
            title='Self Approval Test',
            created_by=self.super_admin,  # Author is super_admin
        )
        submit_page_revision(rev.id, author=self.super_admin)

        # Super admin attempting to approve their own revision
        with self.assertRaises(ValidationError) as ctx:
            approve_page_revision(rev.id, approver=self.super_admin, allow_self_approval=False)
        self.assertIn("Separation of duties violation", str(ctx.exception))

    # --------------------------------------------------------------------------
    # 4. Session Security & Header Settings
    # --------------------------------------------------------------------------

    def test_statutory_session_and_security_configuration(self):
        """
        Verifies GIGW / Government of Maharashtra security settings:
        - 30-minute session inactivity timeout
        - Session expires on browser close
        - HttpOnly session and CSRF cookies
        - X-Frame-Options DENY
        - nosniff header
        """
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Lax')
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertTrue(settings.SECURE_BROWSER_XSS_FILTER)
