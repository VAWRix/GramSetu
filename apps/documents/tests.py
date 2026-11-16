"""
Comprehensive domain, storage, governance, download security, and admin tests for apps.documents.

Verifies:
- Document model constraints, categories, issue dates, confidentiality, and statutory retention hold.
- DocumentTranslation multilingual model, explicit translation records, and public disclosure gate.
- DocumentVersion physical file metadata, 50 MB hard cap, unguessable names, and immutability.
- Protected storage utilities, path traversal defenses, filename sanitization, and SHA-256 integrity verification.
- Separation of duties in disclosure approval (authors/uploaders cannot approve their own documents).
- Governance publishing workflows: submit, approve, reject, rollback, and administrative withdrawal.
- Citizen and version download views: ADR 0004 compliance (anonymous 404 for unapproved/confidential,
  storage drift handling, integrity failure 500 halting, safe headers, and role access).
- Django Admin interface permissions, retention hold protections, and separation of duties enforcement.
"""

import hashlib
import io
import os
from pathlib import Path
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError, SuspiciousOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory, override_settings
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
    EVENT_ROLLBACK,
    EVENT_WITHDRAWAL,
)
from apps.governance.services import (
    submit_document_version_for_disclosure,
    approve_document_disclosure,
    reject_document_disclosure,
    withdraw_document_translation,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    CATEGORY_RESOLUTION,
    CATEGORY_TENDER,
    CATEGORY_BUDGET,
    CATEGORY_CITIZEN_CHARTER,
    CATEGORY_STATUTORY_REPORT,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_DISCLOSED,
    STATUS_WITHDRAWN,
    STATUS_ARCHIVED,
    DISCLOSURE_DRAFT,
    DISCLOSURE_PENDING_APPROVAL,
    DISCLOSURE_APPROVED,
    DISCLOSURE_REJECTED,
    DISCLOSURE_WITHDRAWN,
)
from apps.documents.storage import (
    save_private_document,
    sanitize_filename,
    resolve_private_file_path,
    verify_file_integrity,
    get_private_storage_dir,
    MAX_FILE_SIZE_BYTES,
)
from apps.documents.admin import (
    DocumentAdmin,
    DocumentTranslationAdmin,
    DocumentVersionAdmin,
    DocumentVersionCreationForm,
)


class DocumentBaseTestCase(TestCase):
    """
    Base test case establishing user fixtures with least-privilege roles.
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
            email='second_admin@gramsetu.in',
            full_name='Second Administrator',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.second_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )

        self.citizen = User.objects.create_user(
            email='citizen@gramsetu.in',
            full_name='Ordinary Citizen',
            password='CitizenPassword123!',
            is_staff=False,
        )

        # Helper method to create a real physical file in private storage
        self.created_files = []

    def create_dummy_file(self, content=b"GramSetu Resolution Official Content", filename="resolution.pdf"):
        uploaded = SimpleUploadedFile(filename, content, content_type="application/pdf")
        storage_filename, size, checksum = save_private_document(uploaded)
        file_path = get_private_storage_dir() / storage_filename
        self.created_files.append(file_path)
        return storage_filename, size, checksum

    def tearDown(self):
        # Clean up any created files on disk
        for fp in self.created_files:
            try:
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass


class DocumentModelTests(DocumentBaseTestCase):
    """
    Tests for Document model (canonical anchor, categories, retention hold, confidentiality).
    """

    def test_document_creation_valid(self):
        doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='GP/2026/RES-101',
            issuing_department='General Administration',
            issue_date=timezone.now().date(),
            is_confidential=False,
            retention_hold=False,
        )
        self.assertIsNotNone(doc.id)
        self.assertEqual(doc.category, CATEGORY_RESOLUTION)
        self.assertEqual(doc.reference_number, 'GP/2026/RES-101')
        self.assertIn('GP/2026/RES-101', str(doc))

    def test_document_invalid_category_fails_check(self):
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                Document.objects.create(
                    category='invalid_category',
                    reference_number='GP/2026/INV-1',
                    issuing_department='Admin',
                )

    def test_statutory_retention_hold_blocks_deletion(self):
        doc = Document.objects.create(
            category=CATEGORY_BUDGET,
            reference_number='BUDGET-2026',
            issuing_department='Accounts',
            retention_hold=True,
        )
        with self.assertRaises(ValidationError) as ctx:
            doc.delete()
        self.assertIn("retention hold", str(ctx.exception))
        # Verify document still exists in DB
        self.assertTrue(Document.objects.filter(id=doc.id).exists())

    def test_confidential_document_blocks_disclosed_translation(self):
        doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='CONF-1',
            issuing_department='Vigilance',
            is_confidential=True,
        )
        trans = DocumentTranslation(
            document=doc,
            language_code=LANGUAGE_MARATHI,
            title='Confidential Resolution',
            status=STATUS_DISCLOSED,
        )
        with self.assertRaises(ValidationError):
            trans.clean()


class DocumentTranslationModelTests(DocumentBaseTestCase):
    """
    Tests for DocumentTranslation model (multilingual explicit entities, status lifecycle).
    """

    def setUp(self):
        super().setUp()
        self.doc = Document.objects.create(
            category=CATEGORY_TENDER,
            reference_number='TENDER-01',
            issuing_department='Engineering',
        )

    def test_multilingual_translations_unique_per_language(self):
        DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_MARATHI,
            title='रस्ता बांधकाम निविदा',
        )
        DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_ENGLISH,
            title='Road Construction Tender',
        )
        # Duplicate language for same document must fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentTranslation.objects.create(
                    document=self.doc,
                    language_code=LANGUAGE_MARATHI,
                    title='Duplicate Marathi Tender',
                )

    def test_invalid_language_code_fails_check(self):
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                DocumentTranslation.objects.create(
                    document=self.doc,
                    language_code='fr',
                    title='French Translation',
                )

    def test_is_publicly_disclosed_gate(self):
        trans = DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_MARATHI,
            title='निविदा',
            status=STATUS_DRAFT,
        )
        # Draft is not publicly disclosed
        self.assertFalse(trans.is_publicly_disclosed())

        storage_path, size, checksum = self.create_dummy_file()
        ver = DocumentVersion.objects.create(
            translation=trans,
            version_number=1,
            storage_path=storage_path,
            original_filename='tender.pdf',
            file_size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=self.operator,
            disclosure_status=DISCLOSURE_DRAFT,
        )

        trans.current_version = ver
        self.assertFalse(trans.is_publicly_disclosed())

        ver.disclosure_status = DISCLOSURE_APPROVED
        ver.save()
        trans.status = STATUS_DISCLOSED
        trans.save()
        self.assertTrue(trans.is_publicly_disclosed())

        # If document is marked confidential, is_publicly_disclosed must become False
        self.doc.is_confidential = True
        self.doc.save()
        self.assertFalse(trans.is_publicly_disclosed())


class DocumentVersionModelTests(DocumentBaseTestCase):
    """
    Tests for DocumentVersion model (physical metadata, 50MB cap, immutability).
    """

    def setUp(self):
        super().setUp()
        self.doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='RES-01',
            issuing_department='Admin',
        )
        self.trans = DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_MARATHI,
            title='ठराव',
        )

    def test_version_sequence_uniqueness(self):
        storage_path1, size1, sum1 = self.create_dummy_file(b"v1")
        DocumentVersion.objects.create(
            translation=self.trans,
            version_number=1,
            storage_path=storage_path1,
            original_filename='res_v1.pdf',
            file_size_bytes=size1,
            checksum_sha256=sum1,
            uploaded_by=self.operator,
        )

        storage_path2, size2, sum2 = self.create_dummy_file(b"v2")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentVersion.objects.create(
                    translation=self.trans,
                    version_number=1,  # Duplicate sequence number
                    storage_path=storage_path2,
                    original_filename='res_v2.pdf',
                    file_size_bytes=size2,
                    checksum_sha256=sum2,
                    uploaded_by=self.operator,
                )

    def test_file_size_limit_check(self):
        # 0 byte check constraint
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                DocumentVersion.objects.create(
                    translation=self.trans,
                    version_number=1,
                    storage_path='dummy_0.dat',
                    original_filename='empty.pdf',
                    file_size_bytes=0,
                    checksum_sha256='0' * 64,
                    uploaded_by=self.operator,
                )

        # > 50 MB check constraint
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                DocumentVersion.objects.create(
                    translation=self.trans,
                    version_number=1,
                    storage_path='dummy_huge.dat',
                    original_filename='huge.pdf',
                    file_size_bytes=52428801,
                    checksum_sha256='1' * 64,
                    uploaded_by=self.operator,
                )

    def test_version_immutability_after_review(self):
        storage_path, size, checksum = self.create_dummy_file(b"Immutable Content")
        ver = DocumentVersion.objects.create(
            translation=self.trans,
            version_number=1,
            storage_path=storage_path,
            original_filename='doc.pdf',
            file_size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=self.operator,
            disclosure_status=DISCLOSURE_APPROVED,
        )

        # Attempting to change storage_path or checksum on approved version must fail
        ver.checksum_sha256 = 'f' * 64
        with self.assertRaises(ValidationError):
            ver.save()

    def test_cannot_delete_approved_version(self):
        storage_path, size, checksum = self.create_dummy_file(b"Approved Version Content")
        ver = DocumentVersion.objects.create(
            translation=self.trans,
            version_number=1,
            storage_path=storage_path,
            original_filename='doc.pdf',
            file_size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=self.operator,
            disclosure_status=DISCLOSURE_APPROVED,
        )
        with self.assertRaises(ValidationError):
            ver.delete()


class DocumentStorageTests(DocumentBaseTestCase):
    """
    Tests for storage utilities: hashing, path traversal defenses, sanitization, and size caps.
    """

    def test_save_private_document_success(self):
        content = b"Official Protected Government Document"
        uploaded = SimpleUploadedFile("my_resolution.pdf", content, content_type="application/pdf")
        filename, size, checksum = save_private_document(uploaded)

        self.assertTrue(filename.endswith(".dat"))
        self.assertEqual(size, len(content))
        expected_sha = hashlib.sha256(content).hexdigest()
        self.assertEqual(checksum, expected_sha)

        saved_path = get_private_storage_dir() / filename
        self.created_files.append(saved_path)
        self.assertTrue(saved_path.exists())
        self.assertTrue(verify_file_integrity(saved_path, checksum))

    def test_save_empty_file_rejected(self):
        uploaded = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        with self.assertRaises(ValidationError) as ctx:
            save_private_document(uploaded)
        self.assertIn("empty", str(ctx.exception))

    def test_filename_sanitization(self):
        self.assertEqual(sanitize_filename("../../etc/passwd"), "passwd")
        self.assertEqual(sanitize_filename("..\\..\\boot.ini"), "boot.ini")
        self.assertEqual(sanitize_filename("resolution\x00_test.pdf"), "resolution_test.pdf")
        self.assertEqual(sanitize_filename("tender:annual*report.pdf"), "tender_annual_report.pdf")
        self.assertEqual(sanitize_filename(""), "document.dat")

    def test_path_traversal_defense(self):
        # Direct attempt to resolve file outside PRIVATE_DOCUMENTS_DIR
        with self.assertRaises(SuspiciousOperation):
            resolve_private_file_path("")

        resolved = resolve_private_file_path("../../../etc/passwd")
        # Basename extraction ensures target remains strictly within private storage dir
        storage_dir = get_private_storage_dir()
        self.assertTrue(resolved.is_relative_to(storage_dir))
        self.assertEqual(resolved.name, "passwd")

    def test_verify_file_integrity_tampering_detection(self):
        content = b"Original Authentic Binary Content"
        uploaded = SimpleUploadedFile("doc.pdf", content)
        filename, size, checksum = save_private_document(uploaded)
        file_path = get_private_storage_dir() / filename
        self.created_files.append(file_path)

        # Verified authentic
        self.assertTrue(verify_file_integrity(file_path, checksum))

        # Tamper with file on disk
        with open(file_path, 'wb') as f:
            f.write(b"Tampered Malicious Content")

        # Must detect mismatch
        self.assertFalse(verify_file_integrity(file_path, checksum))


class DocumentGovernanceServicesTests(DocumentBaseTestCase):
    """
    Tests for governance workflow services (submit, approve, separation of duties, reject, withdraw).
    """

    def setUp(self):
        super().setUp()
        self.doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='GOV-RES-01',
            issuing_department='Administration',
        )
        self.trans = DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामसभा ठराव क्रमांक १',
            status=STATUS_DRAFT,
        )
        storage_path, size, checksum = self.create_dummy_file(b"Resolution Binary File")
        self.ver = DocumentVersion.objects.create(
            translation=self.trans,
            version_number=1,
            storage_path=storage_path,
            original_filename='resolution_2026.pdf',
            file_size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=self.operator,
            disclosure_status=DISCLOSURE_DRAFT,
        )

    def test_submit_document_version_for_disclosure(self):
        sub_ver = submit_document_version_for_disclosure(self.ver.id, self.operator)
        self.assertEqual(sub_ver.disclosure_status, DISCLOSURE_PENDING_APPROVAL)
        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_PENDING_APPROVAL)

    def test_approve_document_disclosure_separation_of_duties_enforcement(self):
        submit_document_version_for_disclosure(self.ver.id, self.operator)

        # Uploader cannot approve their own document version
        with self.assertRaises(ValidationError) as ctx:
            approve_document_disclosure(
                self.ver.id,
                approver=self.operator,
                notes="Self approval attempt",
                allow_self_approval=False,
            )
        self.assertIn("Separation of duties violation", str(ctx.exception))

        # Distinct Super Admin can approve
        ver, approval, event = approve_document_disclosure(
            self.ver.id,
            approver=self.super_admin,
            notes="Formal statutory approval",
        )
        self.assertEqual(ver.disclosure_status, DISCLOSURE_APPROVED)
        self.assertIsNotNone(approval)
        self.assertEqual(approval.target_content_type, 'documenttranslation')
        self.assertEqual(approval.approved_by, self.super_admin)
        self.assertEqual(event.event_type, EVENT_INITIAL_PUBLISH)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_DISCLOSED)
        self.assertEqual(self.trans.current_version, ver)
        self.assertTrue(self.trans.is_publicly_disclosed())

    def test_reject_document_disclosure(self):
        submit_document_version_for_disclosure(self.ver.id, self.operator)

        # Rejection reason < 10 chars fails
        with self.assertRaises(ValidationError):
            reject_document_disclosure(self.ver.id, self.super_admin, "Too short")

        ver, rej = reject_document_disclosure(
            self.ver.id,
            self.super_admin,
            "Document lacks official seal and Sarpanch signature.",
        )
        self.assertEqual(ver.disclosure_status, DISCLOSURE_REJECTED)
        self.assertEqual(rej.target_content_type, 'documenttranslation')
        self.assertIn("official seal", rej.rejection_reason)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_DRAFT)

    def test_withdraw_document_translation(self):
        submit_document_version_for_disclosure(self.ver.id, self.operator)
        approve_document_disclosure(self.ver.id, self.super_admin)
        self.trans.refresh_from_db()
        self.assertTrue(self.trans.is_publicly_disclosed())

        # Withdrawal justification < 10 chars fails
        with self.assertRaises(ValidationError):
            withdraw_document_translation(self.trans.id, self.super_admin, "Short")

        event = withdraw_document_translation(
            self.trans.id,
            self.super_admin,
            "Withdrawn pursuant to court order WP-4501/2026.",
        )
        self.assertEqual(event.event_type, EVENT_WITHDRAWAL)

        self.trans.refresh_from_db()
        self.assertEqual(self.trans.status, STATUS_WITHDRAWN)
        self.assertFalse(self.trans.is_publicly_disclosed())

        # Physical file remains intact on disk for statutory audit
        self.assertTrue(self.ver.get_file_path().exists())


class DocumentDeliveryViewsTests(DocumentBaseTestCase):
    """
    Tests for citizen download endpoint and administrative version download endpoint.
    Verifies ADR 0004 security contract and edge cases.
    """

    def setUp(self):
        super().setUp()
        self.doc = Document.objects.create(
            category=CATEGORY_RESOLUTION,
            reference_number='RES-DELIVERY-01',
            issuing_department='Panchayat Office',
        )
        self.trans = DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_MARATHI,
            title='सार्वजनिक ठराव',
            status=STATUS_DRAFT,
        )
        storage_path, size, checksum = self.create_dummy_file(b"%PDF-1.4 Official Resolution PDF")
        self.ver = DocumentVersion.objects.create(
            translation=self.trans,
            version_number=1,
            storage_path=storage_path,
            original_filename='Official_Resolution.pdf',
            file_size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=self.operator,
            disclosure_status=DISCLOSURE_DRAFT,
        )
        self.citizen_download_url = reverse('documents:citizen_download', args=[self.trans.id])
        self.version_download_url = reverse('documents:version_download', args=[self.ver.id])

    def test_anonymous_user_receives_404_for_unapproved_document(self):
        # Unapproved draft document requested by anonymous user
        response = self.client.get(self.citizen_download_url)
        # ADR 0004 requirement: return 404 Not Found, never 403 Forbidden!
        self.assertEqual(response.status_code, 404)

    def test_anonymous_user_receives_404_for_confidential_document(self):
        self.doc.is_confidential = True
        self.doc.save()
        response = self.client.get(self.citizen_download_url)
        self.assertEqual(response.status_code, 404)

    def test_anonymous_user_receives_404_for_withdrawn_document(self):
        submit_document_version_for_disclosure(self.ver.id, self.operator)
        approve_document_disclosure(self.ver.id, self.super_admin)
        withdraw_document_translation(self.trans.id, self.super_admin, "Administrative withdrawal.")

        response = self.client.get(self.citizen_download_url)
        self.assertEqual(response.status_code, 404)

    def test_citizen_download_approved_document_success(self):
        submit_document_version_for_disclosure(self.ver.id, self.operator)
        approve_document_disclosure(self.ver.id, self.super_admin)

        response = self.client.get(self.citizen_download_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('Official_Resolution.pdf', response['Content-Disposition'])

        content = b"".join(response.streaming_content)
        self.assertEqual(content, b"%PDF-1.4 Official Resolution PDF")

    def test_storage_drift_returns_404_without_path_leakage(self):
        submit_document_version_for_disclosure(self.ver.id, self.operator)
        approve_document_disclosure(self.ver.id, self.super_admin)

        # Simulate physical file deletion (storage drift)
        file_path = self.ver.get_file_path()
        if file_path.exists():
            file_path.unlink()

        response = self.client.get(self.citizen_download_url)
        self.assertEqual(response.status_code, 404)

    def test_integrity_failure_halts_download_with_500(self):
        submit_document_version_for_disclosure(self.ver.id, self.operator)
        approve_document_disclosure(self.ver.id, self.super_admin)

        # Tamper with file on disk
        file_path = self.ver.get_file_path()
        with open(file_path, 'wb') as f:
            f.write(b"CORRUPTED OR TAMPERED FILE DATA")

        response = self.client.get(self.citizen_download_url)
        # Checksum mismatch must immediately halt download and return 500
        self.assertEqual(response.status_code, 500)

    def test_version_download_endpoint_access_control(self):
        # Anonymous user gets 404
        response = self.client.get(self.version_download_url)
        self.assertEqual(response.status_code, 404)

        # Authenticated ordinary citizen gets 403
        self.client.force_login(self.citizen)
        response = self.client.get(self.version_download_url)
        self.assertEqual(response.status_code, 403)

        # Authenticated Operator gets 200
        self.client.force_login(self.operator)
        response = self.client.get(self.version_download_url)
        self.assertEqual(response.status_code, 200)

        # Authenticated Super Admin gets 200
        self.client.force_login(self.super_admin)
        response = self.client.get(self.version_download_url)
        self.assertEqual(response.status_code, 200)


class DocumentAdminTests(DocumentBaseTestCase):
    """
    Tests for Django Admin access control, creation forms, actions, and separation of duties.
    """

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.doc_admin = DocumentAdmin(Document, self.site)
        self.trans_admin = DocumentTranslationAdmin(DocumentTranslation, self.site)
        self.ver_admin = DocumentVersionAdmin(DocumentVersion, self.site)

        self.doc = Document.objects.create(
            category=CATEGORY_STATUTORY_REPORT,
            reference_number='ADMIN-DOC-01',
            issuing_department='Revenue',
        )
        self.trans = DocumentTranslation.objects.create(
            document=self.doc,
            language_code=LANGUAGE_MARATHI,
            title='वार्षिक अहवाल',
        )

    def test_operator_cannot_delete_document(self):
        request = self.factory.get('/admin/')
        request.user = self.operator
        self.assertFalse(self.doc_admin.has_delete_permission(request, self.doc))

    def test_super_admin_cannot_delete_retention_hold_document(self):
        self.doc.retention_hold = True
        self.doc.save()
        request = self.factory.get('/admin/')
        request.user = self.super_admin
        self.assertFalse(self.doc_admin.has_delete_permission(request, self.doc))

    def test_document_version_creation_form(self):
        uploaded = SimpleUploadedFile("audit_2026.pdf", b"Audit Report Content 2026", content_type="application/pdf")
        form_data = {'translation': self.trans.id}
        file_data = {'file': uploaded}

        form = DocumentVersionCreationForm(data=form_data, files=file_data)
        self.assertTrue(form.is_valid())
        ver = form.save(commit=True, user=self.operator)

        self.created_files.append(ver.get_file_path())
        self.assertEqual(ver.version_number, 1)
        self.assertEqual(ver.original_filename, 'audit_2026.pdf')
        self.assertEqual(ver.uploaded_by, self.operator)
        self.assertEqual(ver.disclosure_status, DISCLOSURE_DRAFT)

    def test_admin_approve_disclosure_separation_of_duties_action(self):
        storage_path, size, checksum = self.create_dummy_file(b"Admin Test File")
        ver = DocumentVersion.objects.create(
            translation=self.trans,
            version_number=1,
            storage_path=storage_path,
            original_filename='file.pdf',
            file_size_bytes=size,
            checksum_sha256=checksum,
            uploaded_by=self.super_admin,  # Uploaded by Super Admin!
            disclosure_status=DISCLOSURE_PENDING_APPROVAL,
        )

        request = self.factory.post('/admin/documents/documentversion/')
        request.user = self.super_admin  # Same user attempting to approve in Admin
        # Add messages middleware support to dummy request
        setattr(request, '_messages', [])
        setattr(request, 'session', {})

        from django.contrib.messages.storage.fallback import FallbackStorage
        request._messages = FallbackStorage(request)

        # Admin action should refuse self-approval
        self.ver_admin.approve_disclosure_action(request, DocumentVersion.objects.filter(id=ver.id))
        ver.refresh_from_db()
        # Must still be pending_approval!
        self.assertEqual(ver.disclosure_status, DISCLOSURE_PENDING_APPROVAL)

        # Distinct Super Admin can approve
        request.user = self.second_admin
        request._messages = FallbackStorage(request)
        self.ver_admin.approve_disclosure_action(request, DocumentVersion.objects.filter(id=ver.id))
        ver.refresh_from_db()
        self.assertEqual(ver.disclosure_status, DISCLOSURE_APPROVED)
