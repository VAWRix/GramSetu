"""
Comprehensive domain, governance, view, and admin tests for apps.schemes (Milestone 4G).

Verifies:
- WelfareScheme model constraints, UUIDv7 PK, scheme levels, target beneficiaries, and supporting documents.
- SchemeTranslation multilingual uniqueness, localized Devanagari slugs, and strict no-silent-language-fallback.
- SchemeRevision immutability, cryptographic content hashing (SHA-256), and tampering detection.
- Governance workflows: submission, separation of duties in approval, rejection rationale, publication, scheduled publication, withdrawal, and non-destructive rollback.
- Public views and disclosure gate (draft, submitted, unapproved, and withdrawn schemes strictly return 404 to anonymous citizens).
- Filter-based listing by government level and target beneficiary.
- Disclosed supporting document access.
- Django Admin interface permissions, retention protections, and separation of duties enforcement.
"""

from datetime import timedelta
from django.contrib.admin.sites import AdminSite
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
)
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
    submit_scheme_revision,
    approve_scheme_revision,
    reject_scheme_revision,
    publish_scheme_translation,
    withdraw_scheme_translation,
    rollback_scheme_translation,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
    LEVEL_CENTRAL,
    LEVEL_STATE,
    LEVEL_DISTRICT,
    BENEFICIARY_FARMERS,
    BENEFICIARY_WOMEN,
    BENEFICIARY_YOUTH,
    BENEFICIARY_SENIOR_CITIZENS,
    BENEFICIARY_GENERAL,
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
from apps.schemes.admin import (
    WelfareSchemeAdmin,
    SchemeTranslationAdmin,
    SchemeRevisionAdmin,
    RejectSchemeActionForm,
    WithdrawSchemeActionForm,
    ScheduleSchemeActionForm,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    CATEGORY_RESOLUTION,
    DISCLOSURE_APPROVED,
    STATUS_DISCLOSED,
)


class SchemeBaseTestCase(TestCase):
    """
    Base fixture establishing administrative and citizen users.
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

        self.second_admin = User.objects.create_user(
            email='gramsevak2@gramsetu.in',
            full_name='Gram Sevak Administrator 2',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.second_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )


class SchemeModelAndConstraintTests(SchemeBaseTestCase):
    """
    Tests for WelfareScheme and SchemeTranslation schema constraints and validation.
    """

    def test_scheme_creation_and_defaults(self):
        scheme = WelfareScheme.objects.create(
            slug='pm-kisan',
            scheme_level=LEVEL_CENTRAL,
            target_beneficiary=BENEFICIARY_FARMERS,
            official_portal_url='https://pmkisan.gov.in',
            created_by=self.operator,
        )
        self.assertIsNotNone(scheme.id)
        self.assertTrue(scheme.is_active)
        self.assertEqual(scheme.display_order, 0)
        self.assertIn('pm-kisan', str(scheme))

    def test_invalid_scheme_level_rejected_by_db(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WelfareScheme.objects.create(
                    slug='invalid-level',
                    scheme_level='international',
                    target_beneficiary=BENEFICIARY_GENERAL,
                    created_by=self.operator,
                )

    def test_invalid_beneficiary_rejected_by_db(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WelfareScheme.objects.create(
                    slug='invalid-beneficiary',
                    scheme_level=LEVEL_STATE,
                    target_beneficiary='corporations',
                    created_by=self.operator,
                )

    def test_unique_slug_enforcement(self):
        WelfareScheme.objects.create(
            slug='sanjay-gandhi-yojana',
            scheme_level=LEVEL_STATE,
            target_beneficiary=BENEFICIARY_SENIOR_CITIZENS,
            created_by=self.operator,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WelfareScheme.objects.create(
                    slug='sanjay-gandhi-yojana',
                    scheme_level=LEVEL_STATE,
                    target_beneficiary=BENEFICIARY_SENIOR_CITIZENS,
                    created_by=self.operator,
                )

    def test_translation_creation_and_devanagari_slug(self):
        scheme = WelfareScheme.objects.create(
            slug='pmay-gramin',
            scheme_level=LEVEL_CENTRAL,
            target_beneficiary=BENEFICIARY_GENERAL,
            created_by=self.operator,
        )
        trans = SchemeTranslation.objects.create(
            scheme=scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='पीएम-आवास-योजना',
            status=STATUS_DRAFT,
        )
        self.assertEqual(trans.language_code, 'mr')
        self.assertEqual(trans.localized_slug, 'पीएम-आवास-योजना')
        self.assertEqual(trans.status, STATUS_DRAFT)

    def test_unique_translation_per_language_per_scheme(self):
        scheme = WelfareScheme.objects.create(
            slug='magel-tyala-shettale',
            scheme_level=LEVEL_STATE,
            target_beneficiary=BENEFICIARY_FARMERS,
            created_by=self.operator,
        )
        SchemeTranslation.objects.create(
            scheme=scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='मागेल-त्याला-शेततळे',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SchemeTranslation.objects.create(
                    scheme=scheme,
                    language_code=LANGUAGE_MARATHI,
                    localized_slug='मागेल-त्याला-शेततळे-२',
                )

    def test_invalid_language_code_rejected_by_db(self):
        scheme = WelfareScheme.objects.create(
            slug='invalid-lang-test',
            scheme_level=LEVEL_STATE,
            target_beneficiary=BENEFICIARY_YOUTH,
            created_by=self.operator,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SchemeTranslation.objects.create(
                    scheme=scheme,
                    language_code='fr',
                    localized_slug='invalid-fr',
                )

    def test_strict_language_selection_no_silent_fallback(self):
        scheme = WelfareScheme.objects.create(
            slug='jal-yukta-shivar',
            scheme_level=LEVEL_STATE,
            target_beneficiary=BENEFICIARY_FARMERS,
            created_by=self.operator,
        )
        trans = SchemeTranslation.objects.create(
            scheme=scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='जलयुक्त-शिवार',
        )
        SchemeRevision.objects.create(
            translation=trans,
            revision_number=1,
            scheme_name='जलयुक्त शिवार अभियान',
            short_summary='जलसंधारण योजना',
            eligibility_criteria='सर्व ग्रामस्थ व शेतकरी',
            required_documents='७/१२ उतारा',
            application_process='ग्रामपंचायत कार्यालयात संपर्क',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )

        # Requesting Marathi returns name; requesting English returns empty string (no silent fallback)
        self.assertEqual(scheme.get_name(LANGUAGE_MARATHI), 'जलयुक्त शिवार अभियान')
        self.assertEqual(scheme.get_name(LANGUAGE_ENGLISH), '')


class SchemeRevisionImmutabilityAndHashTests(SchemeBaseTestCase):
    """
    Tests for SchemeRevision immutability, SHA-256 content hashing, and tampering detection (ADR 0002).
    """

    def setUp(self):
        super().setUp()
        self.scheme = WelfareScheme.objects.create(
            slug='kanyadan-yojana',
            scheme_level=LEVEL_STATE,
            target_beneficiary=BENEFICIARY_WOMEN,
            created_by=self.operator,
        )
        self.translation = SchemeTranslation.objects.create(
            scheme=self.scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='कन्यादान-योजना',
        )

    def test_revision_creation_and_hash_computation(self):
        rev = SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='शुभमंगल कन्यादान योजना',
            short_summary='आर्थिक दुर्बल घटकांतील मुलींच्या विवाहासाठी आर्थिक सहाय्य',
            eligibility_criteria='कुटुंबाचे वार्षिक उत्पन्न १ लाख रुपयांपेक्षा कमी असावे',
            benefits='२५,०००/- रुपये थेट बँक खात्यात',
            required_documents='उत्पन्नाचा दाखला, आधार कार्ड, विवाह नोंदणी प्रमाणपत्र',
            application_process='विहित नमुन्यातील अर्ज ग्रामपंचायत अथवा पंचायत समिती कार्यालयात सादर करावा',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        self.assertIsNotNone(rev.id)
        self.assertEqual(len(rev.content_hash), 64)
        self.assertEqual(rev.content_hash, rev.calculate_hash())
        self.assertTrue(rev.verify_integrity())

    def test_draft_revision_can_be_edited(self):
        rev = SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='Original Name',
            short_summary='Original Summary',
            eligibility_criteria='Original Criteria',
            required_documents='Original Docs',
            application_process='Original Process',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        rev.scheme_name = 'Updated Name'
        rev.short_summary = 'Updated Summary'
        rev.save()

        rev.refresh_from_db()
        self.assertEqual(rev.scheme_name, 'Updated Name')
        self.assertEqual(rev.short_summary, 'Updated Summary')

    def test_submit_for_review_validation(self):
        rev = SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='Sh',  # < 3 chars fails
            short_summary='Short',
            eligibility_criteria='Criteria',  # < 10 chars fails
            required_documents='Docs',  # < 5 chars fails
            application_process='Proc',  # < 10 chars fails
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        with self.assertRaises(ValidationError):
            rev.submit_for_review()

    def test_submitted_revision_becomes_immutable(self):
        rev = SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='शुभमंगल कन्यादान योजना',
            short_summary='मुलींच्या विवाहासाठी आर्थिक सहाय्य',
            eligibility_criteria='कुटुंबाचे वार्षिक उत्पन्न १ लाख रुपयांपेक्षा कमी',
            benefits='२५,००० रुपये अनुदान',
            required_documents='उत्पन्नाचा दाखला, आधार कार्ड, विवाह नोंदणी',
            application_process='ग्रामपंचायत अथवा पंचायत समिती कार्यालयात संपर्क साधावा',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        rev.submit_for_review()
        self.assertEqual(rev.editorial_status, EDITORIAL_SUBMITTED)
        self.assertIsNotNone(rev.submitted_at)

        # In-place modification of content fields must raise ValidationError
        rev.scheme_name = 'Tampered Scheme Name'
        with self.assertRaises(ValidationError) as ctx:
            rev.save()
        self.assertIn("strictly immutable", str(ctx.exception))

        rev.refresh_from_db()
        self.assertEqual(rev.scheme_name, 'शुभमंगल कन्यादान योजना')

    def test_unique_revision_number_per_translation(self):
        SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='Scheme A',
            short_summary='Summary A',
            eligibility_criteria='Criteria A',
            required_documents='Docs A',
            application_process='Process A',
            created_by=self.operator,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SchemeRevision.objects.create(
                    translation=self.translation,
                    revision_number=1,
                    scheme_name='Scheme B',
                    short_summary='Summary B',
                    eligibility_criteria='Criteria B',
                    required_documents='Docs B',
                    application_process='Process B',
                    created_by=self.operator,
                )

    def test_branching_new_revision(self):
        rev1 = SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='Initial Scheme Title',
            short_summary='Initial Summary',
            eligibility_criteria='Income < 1 Lakh',
            required_documents='Ration Card',
            application_process='Apply at GP',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        rev1.submit_for_review()

        # Branch revision 2
        rev2 = self.translation.create_next_revision(
            author=self.operator,
            scheme_name='Updated Scheme Title for Rev 2',
        )
        self.assertEqual(rev2.revision_number, 2)
        self.assertEqual(rev2.scheme_name, 'Updated Scheme Title for Rev 2')
        self.assertEqual(rev2.eligibility_criteria, 'Income < 1 Lakh')
        self.assertEqual(rev2.editorial_status, EDITORIAL_DRAFT)


class SchemeGovernanceWorkflowTests(SchemeBaseTestCase):
    """
    Tests for submit, approve, reject, publish, schedule, withdraw, and rollback services.
    """

    def setUp(self):
        super().setUp()
        self.scheme = WelfareScheme.objects.create(
            slug='pm-kisan-workflow',
            scheme_level=LEVEL_CENTRAL,
            target_beneficiary=BENEFICIARY_FARMERS,
            official_portal_url='https://pmkisan.gov.in',
            created_by=self.operator,
        )
        self.translation = SchemeTranslation.objects.create(
            scheme=self.scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='पीएम-किसान-सन्मान',
        )
        self.revision = SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='प्रधानमंत्री किसान सन्मान निधी',
            short_summary='शेतकऱ्यांना वार्षिक ६००० रुपये आर्थिक सहाय्य',
            eligibility_criteria='जमीन धारक शेतकरी कुटुंब',
            benefits='दर चार महिन्यांनी २,००० रुपयांचे तीन हप्ते (एकूण ६,००० रु.)',
            required_documents='७/१२ उतारा, ८-अ, आधार कार्ड, बँक खाते पासबुक',
            application_process='pmkisan.gov.in पोर्टलवर अथवा सीएससी केंद्रावर अर्ज करावा',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )

    def test_submit_scheme_revision(self):
        rev = submit_scheme_revision(self.revision.id, self.operator)
        self.assertEqual(rev.editorial_status, EDITORIAL_SUBMITTED)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.status, STATUS_SUBMITTED)

    def test_approve_scheme_revision_separation_of_duties(self):
        submit_scheme_revision(self.revision.id, self.operator)

        # Author cannot approve their own revision
        with self.assertRaises(ValidationError) as ctx:
            approve_scheme_revision(
                self.revision.id,
                approver=self.operator,
                notes="Self-approval attempt",
                allow_self_approval=False,
            )
        self.assertIn("Separation of duties violation", str(ctx.exception))

        # Distinct Super Admin can approve
        rev, approval = approve_scheme_revision(
            self.revision.id,
            approver=self.super_admin,
            notes="Formal approval by Super Administrator",
        )
        self.assertEqual(rev.editorial_status, EDITORIAL_APPROVED)
        self.assertEqual(approval.target_content_type, 'schemetranslation')
        self.assertEqual(approval.target_id, self.translation.id)
        self.assertEqual(approval.revision_hash, rev.content_hash)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.status, STATUS_APPROVED)

    def test_reject_scheme_revision(self):
        submit_scheme_revision(self.revision.id, self.operator)

        # Reason < 10 chars fails
        with self.assertRaises(ValidationError):
            reject_scheme_revision(self.revision.id, self.super_admin, "Too short")

        rev, rejection = reject_scheme_revision(
            self.revision.id,
            self.super_admin,
            "Eligibility criteria lacks landholding ceiling details.",
        )
        self.assertEqual(rev.editorial_status, EDITORIAL_REJECTED)
        self.assertEqual(rejection.target_content_type, 'schemetranslation')
        self.assertIn("lacks landholding", rejection.rejection_reason)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.status, STATUS_DRAFT)

    def test_publish_scheme_translation_immediate(self):
        submit_scheme_revision(self.revision.id, self.operator)
        approve_scheme_revision(self.revision.id, self.super_admin)

        pub_event = publish_scheme_translation(
            self.translation.id,
            self.revision.id,
            self.super_admin,
            justification="Official publication of PM-Kisan scheme",
        )
        self.assertEqual(pub_event.event_type, EVENT_INITIAL_PUBLISH)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.status, STATUS_PUBLISHED)
        self.assertEqual(self.translation.current_publication_event_id, pub_event.id)

    def test_publish_scheme_translation_scheduled(self):
        submit_scheme_revision(self.revision.id, self.operator)
        approve_scheme_revision(self.revision.id, self.super_admin)

        future_effective = timezone.now() + timedelta(days=2)
        pub_event = publish_scheme_translation(
            self.translation.id,
            self.revision.id,
            self.super_admin,
            effective_from=future_effective,
            justification="Scheduled launch alongside agricultural season",
        )
        self.assertEqual(pub_event.event_type, EVENT_SCHEDULED_PUBLISH)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.status, STATUS_SCHEDULED)

    def test_withdraw_scheme_translation(self):
        submit_scheme_revision(self.revision.id, self.operator)
        approve_scheme_revision(self.revision.id, self.super_admin)
        publish_scheme_translation(self.translation.id, self.revision.id, self.super_admin)

        # Reason < 10 chars fails
        with self.assertRaises(ValidationError):
            withdraw_scheme_translation(self.translation.id, self.super_admin, "Short")

        pub_event = withdraw_scheme_translation(
            self.translation.id,
            self.super_admin,
            "Temporarily withdrawn pending official revision from Department of Agriculture.",
        )
        self.assertEqual(pub_event.event_type, EVENT_WITHDRAWAL)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.status, STATUS_WITHDRAWN)

    def test_rollback_scheme_translation(self):
        # Publish Revision 1
        submit_scheme_revision(self.revision.id, self.operator)
        approve_scheme_revision(self.revision.id, self.super_admin)
        publish_scheme_translation(self.translation.id, self.revision.id, self.super_admin)

        # Create, submit, approve, and publish Revision 2
        rev2 = self.translation.create_next_revision(
            author=self.operator,
            scheme_name='प्रधानमंत्री किसान सन्मान निधी (सुधारित)',
        )
        submit_scheme_revision(rev2.id, self.operator)
        approve_scheme_revision(rev2.id, self.second_admin)
        publish_scheme_translation(self.translation.id, rev2.id, self.second_admin)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.current_approved_revision_id, rev2.id)

        # Rollback to Revision 1
        pub_event = rollback_scheme_translation(
            self.translation.id,
            self.revision.id,
            self.super_admin,
            justification="Rollback to Revision 1 due to typographical errors in Revision 2.",
        )
        self.assertEqual(pub_event.event_type, EVENT_ROLLBACK)
        self.translation.refresh_from_db()
        self.assertEqual(self.translation.current_approved_revision_id, self.revision.id)


class SchemePublicViewsTests(SchemeBaseTestCase):
    """
    Tests for public scheme list and detail endpoints, filters, and disclosure gating.
    """

    def setUp(self):
        super().setUp()
        # Create published central farmer scheme
        self.published_scheme = WelfareScheme.objects.create(
            slug='pm-kisan-live',
            scheme_level=LEVEL_CENTRAL,
            target_beneficiary=BENEFICIARY_FARMERS,
            official_portal_url='https://pmkisan.gov.in',
            created_by=self.operator,
        )
        self.trans_mr = SchemeTranslation.objects.create(
            scheme=self.published_scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='पीएम-किसान-थेट',
        )
        rev1 = SchemeRevision.objects.create(
            translation=self.trans_mr,
            revision_number=1,
            scheme_name='पीएम किसान सन्मान',
            short_summary='वार्षिक ६००० रु. शेतकरी सहाय्य',
            eligibility_criteria='सर्व पात्र अल्पभूधारक शेतकरी',
            benefits='२,००० रुपयांचे तीन हप्ते',
            required_documents='७/१२, आधार कार्ड',
            application_process='पोर्टलवर नोंदणी करा',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        submit_scheme_revision(rev1.id, self.operator)
        approve_scheme_revision(rev1.id, self.super_admin)
        publish_scheme_translation(self.trans_mr.id, rev1.id, self.super_admin)

        # Create published state women scheme
        self.state_scheme = WelfareScheme.objects.create(
            slug='majhi-kanya-bhagyashree',
            scheme_level=LEVEL_STATE,
            target_beneficiary=BENEFICIARY_WOMEN,
            official_portal_url='https://womenchild.maharashtra.gov.in',
            created_by=self.operator,
        )
        self.state_trans_mr = SchemeTranslation.objects.create(
            scheme=self.state_scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='माझी-कन्या-भाग्यश्री',
        )
        rev2 = SchemeRevision.objects.create(
            translation=self.state_trans_mr,
            revision_number=1,
            scheme_name='माझी कन्या भाग्यश्री योजना',
            short_summary='मुलींच्या शिक्षणासाठी व आरोग्यासाठी सहाय्य',
            eligibility_criteria='महाराष्ट्र राज्यातील कुटुंब',
            benefits='आर्थिक मुदत ठेव प्रमाणपत्र',
            required_documents='जन्म प्रमाणपत्र, आधार कार्ड',
            application_process='अंगणवाडी अथवा ग्रामपंचायत कार्यालयात अर्ज',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )
        submit_scheme_revision(rev2.id, self.operator)
        approve_scheme_revision(rev2.id, self.super_admin)
        publish_scheme_translation(self.state_trans_mr.id, rev2.id, self.super_admin)

        # Create unapproved draft scheme
        self.draft_scheme = WelfareScheme.objects.create(
            slug='draft-youth-scheme',
            scheme_level=LEVEL_STATE,
            target_beneficiary=BENEFICIARY_YOUTH,
            created_by=self.operator,
        )
        self.draft_trans = SchemeTranslation.objects.create(
            scheme=self.draft_scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='मसुदा-योजना',
            status=STATUS_DRAFT,
        )
        SchemeRevision.objects.create(
            translation=self.draft_trans,
            revision_number=1,
            scheme_name='मसुदा युवक योजना',
            short_summary='अप्रकाशित मसुदा',
            eligibility_criteria='पात्रता निकष',
            required_documents='कागदपत्रे',
            application_process='प्रक्रिया',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.operator,
        )

        # Create supporting document
        self.doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='DOC/2026/045',
            issuing_department='Department of Agriculture',
        )
        self.doc_trans = DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_MARATHI,
            title='पीएम किसान शासन निर्णय GR',
            status=STATUS_DISCLOSED,
        )
        self.doc_ver = DocumentVersion.objects.create(
            translation=self.doc_trans,
            version_number=1,
            storage_path='01a14fa6-pmkisan-gr.dat',
            original_filename='pmkisan_gr_2026.pdf',
            file_size_bytes=1048576,
            mime_type='application/pdf',
            checksum_sha256='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            disclosure_status=DISCLOSURE_APPROVED,
            uploaded_by=self.operator,
        )
        self.doc_trans.current_version = self.doc_ver
        self.doc_trans.save()
        self.published_scheme.supporting_documents.add(self.doc)

    def test_anonymous_citizen_scheme_list_published_only(self):
        url = reverse('schemes:scheme_list')
        resp = self.client.get(url, {'lang': 'mr'})
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        slugs = [s['slug'] for s in data['results']]
        self.assertIn('pm-kisan-live', slugs)
        self.assertIn('majhi-kanya-bhagyashree', slugs)
        self.assertNotIn('draft-youth-scheme', slugs)

    def test_scheme_list_filters(self):
        url = reverse('schemes:scheme_list')

        # Filter by level
        resp_central = self.client.get(url, {'level': 'central', 'lang': 'mr'})
        self.assertEqual(resp_central.status_code, 200)
        c_slugs = [s['slug'] for s in resp_central.json()['results']]
        self.assertIn('pm-kisan-live', c_slugs)
        self.assertNotIn('majhi-kanya-bhagyashree', c_slugs)

        # Filter by beneficiary
        resp_women = self.client.get(url, {'beneficiary': 'women', 'lang': 'mr'})
        self.assertEqual(resp_women.status_code, 200)
        w_slugs = [s['slug'] for s in resp_women.json()['results']]
        self.assertIn('majhi-kanya-bhagyashree', w_slugs)
        self.assertNotIn('pm-kisan-live', w_slugs)

    def test_scheme_list_strict_language_filtering(self):
        url = reverse('schemes:scheme_list')
        # Neither scheme has English translations
        resp_en = self.client.get(url, {'lang': 'en'})
        self.assertEqual(resp_en.status_code, 200)
        self.assertEqual(resp_en.json()['count'], 0)

    def test_anonymous_citizen_gets_404_for_draft_and_withdrawn_scheme(self):
        # Draft scheme returns 404
        url_draft = reverse('schemes:scheme_detail', args=[self.draft_scheme.slug])
        resp_draft = self.client.get(url_draft)
        self.assertEqual(resp_draft.status_code, 404)

        # Withdraw published scheme
        withdraw_scheme_translation(self.trans_mr.id, self.super_admin, "Temporarily taken down.")
        url_withdrawn = reverse('schemes:scheme_detail', args=[self.published_scheme.slug])
        resp_withdrawn = self.client.get(url_withdrawn)
        self.assertEqual(resp_withdrawn.status_code, 404)

    def test_staff_can_preview_unapproved_scheme(self):
        self.client.force_login(self.operator)
        url = reverse('schemes:scheme_detail', args=[self.draft_scheme.slug])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['scheme_name'], 'मसुदा युवक योजना')

    def test_public_scheme_detail_lookup_by_slug_and_uuid(self):
        # By slug
        url_slug = reverse('schemes:scheme_detail', args=[self.published_scheme.slug])
        resp_slug = self.client.get(url_slug, {'lang': 'mr'})
        self.assertEqual(resp_slug.status_code, 200)
        self.assertEqual(resp_slug.json()['scheme_name'], 'पीएम किसान सन्मान')

        # By UUID
        url_id = reverse('schemes:scheme_detail', args=[str(self.published_scheme.id)])
        resp_id = self.client.get(url_id, {'lang': 'mr'})
        self.assertEqual(resp_id.status_code, 200)
        self.assertEqual(resp_id.json()['id'], str(self.published_scheme.id))

    def test_public_scheme_detail_disclosed_supporting_documents(self):
        url = reverse('schemes:scheme_detail', args=[self.published_scheme.slug])
        resp = self.client.get(url, {'lang': 'mr'})
        self.assertEqual(resp.status_code, 200)

        docs = resp.json()['supporting_documents']
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]['title'], 'पीएम किसान शासन निर्णय GR')
        self.assertIn('/documents/', docs[0]['download_url'])

    def test_strict_language_detail_view_returns_404_for_missing_translation(self):
        url = reverse('schemes:scheme_detail', args=[self.published_scheme.slug])
        resp = self.client.get(url, {'lang': 'en'})
        self.assertEqual(resp.status_code, 404)


class SchemeAdminTests(SchemeBaseTestCase):
    """
    Tests for Django Admin role-based permissions and governance actions.
    """

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.scheme_admin = WelfareSchemeAdmin(WelfareScheme, self.site)
        self.revision_admin = SchemeRevisionAdmin(SchemeRevision, self.site)

        self.scheme = WelfareScheme.objects.create(
            slug='admin-test-scheme',
            scheme_level=LEVEL_DISTRICT,
            target_beneficiary=BENEFICIARY_GENERAL,
            created_by=self.super_admin,
        )
        self.translation = SchemeTranslation.objects.create(
            scheme=self.scheme,
            language_code=LANGUAGE_MARATHI,
            localized_slug='प्रशासकीय-चाचणी',
        )
        self.revision = SchemeRevision.objects.create(
            translation=self.translation,
            revision_number=1,
            scheme_name='जिल्हा परिषद चाचणी योजना',
            short_summary='चाचणी सारांश',
            eligibility_criteria='जिल्हा रहिवासी नागरिक',
            benefits='प्रशासकीय लाभ',
            required_documents='रहिवासी दाखला',
            application_process='जिल्हा परिषद कार्यालयात संपर्क',
            editorial_status=EDITORIAL_DRAFT,
            created_by=self.super_admin,
        )

    def test_operator_cannot_delete_welfare_scheme(self):
        request = self.factory.get('/admin/')
        request.user = self.operator
        self.assertFalse(self.scheme_admin.has_delete_permission(request, self.scheme))

    def test_admin_approve_action_anti_self_approval(self):
        url = reverse('admin:schemes_schemerevision_changelist')
        self.revision.submit_for_review()

        # Author (super_admin) cannot approve own revision via admin action
        self.client.force_login(self.super_admin)
        response = self.client.post(
            url,
            {
                'action': 'approve_revisions_action',
                '_selected_action': [str(self.revision.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.editorial_status, EDITORIAL_SUBMITTED)

        # Distinct Super Admin can approve
        self.client.force_login(self.second_admin)
        response = self.client.post(
            url,
            {
                'action': 'approve_revisions_action',
                '_selected_action': [str(self.revision.id)],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.editorial_status, EDITORIAL_APPROVED)

    def test_admin_action_forms_validation(self):
        # Reject form min 10 chars
        f_invalid = RejectSchemeActionForm(data={'rejection_reason': 'Short'})
        self.assertFalse(f_invalid.is_valid())
        self.assertIn('rejection_reason', f_invalid.errors)

        f_valid = RejectSchemeActionForm(data={'rejection_reason': 'Eligibility criteria missing income limits.'})
        self.assertTrue(f_valid.is_valid())

        # Withdraw form min 10 chars
        w_invalid = WithdrawSchemeActionForm(data={'justification': 'Bad'})
        self.assertFalse(w_invalid.is_valid())
        self.assertIn('justification', w_invalid.errors)

        w_valid = WithdrawSchemeActionForm(data={'justification': 'Withdrawn due to government departmental notification.'})
        self.assertTrue(w_valid.is_valid())

        # Schedule form must be future
        past_time = timezone.now() - timedelta(hours=1)
        s_invalid = ScheduleSchemeActionForm(data={'effective_from': past_time.strftime('%Y-%m-%dT%H:%M')})
        self.assertFalse(s_invalid.is_valid())

        future_time = timezone.now() + timedelta(days=3)
        s_valid = ScheduleSchemeActionForm(data={'effective_from': future_time.strftime('%Y-%m-%dT%H:%M')})
        self.assertTrue(s_valid.is_valid())
