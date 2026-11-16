"""
Documents and Downloads domain models for GramSetu platform.

Implements Document (canonical anchor), DocumentTranslation, and DocumentVersion
in accordance with approved architectural specifications in docs/data-model.md
(Section 4.6, Section 7, and Section 8) and ADR 0004.
"""

from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone
from apps.core.utils import generate_uuid7
from apps.documents.storage import resolve_private_file_path, verify_file_integrity
from apps.governance.models import EVENT_WITHDRAWAL

# Language constants (Marathi statutory primary)
LANGUAGE_MARATHI = 'mr'
LANGUAGE_HINDI = 'hi'
LANGUAGE_ENGLISH = 'en'

LANGUAGE_CHOICES = [
    (LANGUAGE_MARATHI, 'Marathi / मराठी'),
    (LANGUAGE_HINDI, 'Hindi / हिंदी'),
    (LANGUAGE_ENGLISH, 'English / इंग्रजी'),
]

# Document Categories / Document Types
CATEGORY_RESOLUTION = 'resolution'
CATEGORY_TENDER = 'tender'
CATEGORY_BUDGET = 'budget'
CATEGORY_CITIZEN_CHARTER = 'citizen_charter'
CATEGORY_STATUTORY_REPORT = 'statutory_report'

CATEGORY_CHOICES = [
    (CATEGORY_RESOLUTION, 'Gram Sabha Resolution / ग्रामसभा ठराव'),
    (CATEGORY_TENDER, 'Tender Document / निविदा दस्तऐवज'),
    (CATEGORY_BUDGET, 'Annual Budget / Audit Report / वार्षिक अंदाजपत्रक / लेखापरीक्षण अहवाल'),
    (CATEGORY_CITIZEN_CHARTER, 'Citizen Charter / Form / नागरिक सनद / अर्ज नमुना'),
    (CATEGORY_STATUTORY_REPORT, 'Statutory / Administrative Report / वैधानिक / प्रशासकीय अहवाल'),
]

# Public Publication Lifecycle Status for Translations
STATUS_DRAFT = 'draft'
STATUS_PENDING_APPROVAL = 'pending_approval'
STATUS_DISCLOSED = 'disclosed'
STATUS_WITHDRAWN = 'withdrawn'
STATUS_ARCHIVED = 'archived'

STATUS_CHOICES = [
    (STATUS_DRAFT, 'Draft / Ingestion / मसुदा'),
    (STATUS_PENDING_APPROVAL, 'Pending Disclosure Approval / मंजुरी प्रलंबित'),
    (STATUS_DISCLOSED, 'Publicly Disclosed / सार्वजनिकपणे खुला'),
    (STATUS_WITHDRAWN, 'Withdrawn from Public View / मागे घेतलेला'),
    (STATUS_ARCHIVED, 'Archived / संग्रहित'),
]

# Disclosure Review Lifecycle Status for Document Versions
DISCLOSURE_DRAFT = 'draft'
DISCLOSURE_PENDING_APPROVAL = 'pending_approval'
DISCLOSURE_APPROVED = 'approved_for_disclosure'
DISCLOSURE_REJECTED = 'rejected'
DISCLOSURE_WITHDRAWN = 'withdrawn'

DISCLOSURE_CHOICES = [
    (DISCLOSURE_DRAFT, 'Private Draft / मसुदा'),
    (DISCLOSURE_PENDING_APPROVAL, 'Pending Disclosure Review / पुनरावलोकनासाठी प्रलंबित'),
    (DISCLOSURE_APPROVED, 'Approved for Public Disclosure / प्रकटीकरणासाठी मंजूर'),
    (DISCLOSURE_REJECTED, 'Disclosure Rejected / प्रकटीकरण नाकारले'),
    (DISCLOSURE_WITHDRAWN, 'Withdrawn / मागे घेतलेले'),
]


class DocumentQuerySet(models.QuerySet):
    def disclosed(self, language_code: str = LANGUAGE_MARATHI):
        """
        Returns Documents that have an eligible publicly disclosed translation in the requested language.
        """
        disclosed_translations = DocumentTranslation.objects.for_language(language_code).disclosed()
        return self.filter(translations__in=disclosed_translations).distinct()

    def delete(self):
        if self.filter(retention_hold=True).exists():
            raise ValidationError("Bulk deletion blocked: one or more documents are under statutory retention hold.")
        return super().delete()



class DocumentManager(models.Manager.from_queryset(DocumentQuerySet)):
    pass


class Document(models.Model):
    """
    Canonical logical anchor for a government document, meeting minutes, resolution, or tender.
    Tracks metadata, confidentiality, and statutory retention hold.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        help_text="Official statutory category",
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Official dispatch or file reference number (e.g., GP/2026/RES-42)",
    )
    issuing_department = models.CharField(
        max_length=150,
        help_text="Issuing authority or department (e.g., ग्रामपंचायत सामान्य प्रशासन विभाग)",
    )
    issue_date = models.DateField(
        default=timezone.now,
        null=True,
        blank=True,
        help_text="Official date of issue or enactment",
    )
    is_confidential = models.BooleanField(
        default=False,
        help_text="Restricts workflow; confidential items cannot be marked for public disclosure",
    )
    retention_hold = models.BooleanField(
        default=False,
        help_text="Statutory legal hold; blocks deletion even by Super Administrators",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentManager()

    class Meta:
        db_table = 'documents_document'
        verbose_name = 'Document / दस्तऐवज'
        verbose_name_plural = 'Documents / दस्तऐवज'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['category', '-created_at'], name='idx_doc_cat_created'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(category__in=[c[0] for c in CATEGORY_CHOICES]),
                name='chk_valid_doc_category',
            ),
        ]

    def __str__(self):
        ref = f" [{self.reference_number}]" if self.reference_number else ""
        return f"{self.get_category_display()}{ref} ({self.issuing_department})"

    def clean(self):
        super().clean()
        if self.is_confidential and self.pk:
            # If confidential, cannot have disclosed translations
            disclosed = self.translations.filter(status=STATUS_DISCLOSED).exists()
            if disclosed:
                raise ValidationError("Confidential documents cannot have publicly disclosed translations.")

    def delete(self, *args, **kwargs):
        if self.retention_hold:
            raise ValidationError(
                f"Document '{self.reference_number or self.id}' is under statutory retention hold and cannot be deleted."
            )
        return super().delete(*args, **kwargs)


class DocumentTranslationQuerySet(models.QuerySet):
    def for_language(self, language_code: str):
        return self.filter(language_code=language_code)

    def disclosed(self):
        """
        Returns translations eligible for public citizen download:
        1. Parent document is NOT confidential.
        2. Translation status is 'disclosed'.
        3. current_version is present and disclosure_status is 'approved_for_disclosure'.
        4. Not administratively withdrawn.
        """
        return (
            self.filter(
                document__is_confidential=False,
                status=STATUS_DISCLOSED,
                current_version__isnull=False,
                current_version__disclosure_status=DISCLOSURE_APPROVED,
            )
            .exclude(status=STATUS_WITHDRAWN)
            .exclude(current_publication_event__event_type=EVENT_WITHDRAWAL)
        )

    def delete(self):
        if self.filter(document__retention_hold=True).exists():
            raise ValidationError("Bulk deletion blocked: parent document is under statutory retention hold.")
        return super().delete()



class DocumentTranslationManager(models.Manager.from_queryset(DocumentTranslationQuerySet)):
    pass


class DocumentTranslation(models.Model):
    """
    Language-specific metadata and disclosure state for a Document.
    Enforces the Explicit Translation Entity pattern (ADR 0001) and ADR 0004.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='translations',
    )
    language_code = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
    )
    slug = models.SlugField(
        max_length=200,
        allow_unicode=True,
        blank=True,
        help_text="Optional clean localized slug for public access",
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    current_version = models.ForeignKey(
        'DocumentVersion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_for_translations',
    )
    status = models.CharField(
        max_length=20,
        default=STATUS_DRAFT,
        choices=STATUS_CHOICES,
    )
    current_publication_event = models.ForeignKey(
        'governance.PublicationEvent',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_document_translations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentTranslationManager()

    class Meta:
        db_table = 'documents_document_translation'
        verbose_name = 'Document Translation / दस्तऐवज भाषांतर'
        verbose_name_plural = 'Document Translations / दस्तऐवज भाषांतरे'
        ordering = ['document', 'language_code']
        indexes = [
            models.Index(fields=['language_code', 'status'], name='idx_doc_trans_lang_status'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'language_code'],
                name='uq_doc_lang',
            ),
            models.CheckConstraint(
                condition=Q(language_code__in=['mr', 'hi', 'en']),
                name='chk_valid_doc_lang',
            ),
            models.CheckConstraint(
                condition=Q(status__in=[c[0] for c in STATUS_CHOICES]),
                name='chk_valid_doc_status',
            ),
        ]

    def __str__(self):
        return f"{self.title} [{self.language_code}] ({self.status})"

    def clean(self):
        super().clean()
        if self.document.is_confidential and self.status == STATUS_DISCLOSED:
            raise ValidationError("Confidential documents cannot be publicly disclosed.")

        if self.current_version_id:
            if self.current_version.translation_id != self.id:
                raise ValidationError("The active document version must belong to this translation.")
            if self.status == STATUS_DISCLOSED and self.current_version.disclosure_status != DISCLOSURE_APPROVED:
                raise ValidationError(
                    "Cannot set status to 'disclosed' unless current_version is 'approved_for_disclosure'."
                )

    def is_publicly_disclosed(self) -> bool:
        """
        Evaluates the strict disclosure gate (ADR 0004 Section 3):
        - Parent document is NOT confidential.
        - Status is 'disclosed'.
        - Current version exists and is approved for disclosure.
        - Not withdrawn.
        """
        if self.document.is_confidential:
            return False
        if self.status != STATUS_DISCLOSED:
            return False
        if not self.current_version_id:
            return False
        if self.current_version.disclosure_status != DISCLOSURE_APPROVED:
            return False
        if self.current_publication_event and self.current_publication_event.event_type == EVENT_WITHDRAWAL:
            return False
        return True

    def delete(self, *args, **kwargs):
        if self.document.retention_hold:
            raise ValidationError(
                f"Document is under statutory retention hold; translation '{self.title}' cannot be deleted."
            )
        return super().delete(*args, **kwargs)


class DocumentVersionQuerySet(models.QuerySet):
    def delete(self):
        if self.exclude(disclosure_status=DISCLOSURE_DRAFT).exists():
            raise ValidationError(
                "Bulk deletion blocked: cannot delete document versions submitted or approved for disclosure. "
                "Only unsubmitted private draft versions may be discarded."
            )
        if self.filter(translation__document__retention_hold=True).exists():
            raise ValidationError(
                "Bulk deletion blocked: parent document is under statutory retention hold."
            )
        return super().delete()


class DocumentVersionManager(models.Manager.from_queryset(DocumentVersionQuerySet)):
    pass


class DocumentVersion(models.Model):
    """
    Physical binary file version and disclosure metadata.
    Enforces private storage outside web root and immutable checksums (ADR 0004).
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    objects = DocumentVersionManager()
    translation = models.ForeignKey(
        DocumentTranslation,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    version_number = models.PositiveIntegerField()
    storage_path = models.CharField(
        max_length=500,
        unique=True,
        help_text="Internal unguessable storage path on disk (e.g. 0192a83f-...dat)",
    )
    original_filename = models.CharField(
        max_length=255,
        help_text="Original filename preserved for citizen download Content-Disposition",
    )
    file_size_bytes = models.BigIntegerField(
        help_text="Size of file in bytes (max 50 MB)",
    )
    mime_type = models.CharField(
        max_length=100,
        default='application/pdf',
        help_text="MIME content type (e.g. application/pdf)",
    )
    checksum_sha256 = models.CharField(
        max_length=64,
        help_text="Cryptographic SHA-256 digest of physical binary file",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='uploaded_document_versions',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    disclosure_status = models.CharField(
        max_length=30,
        default=DISCLOSURE_DRAFT,
        choices=DISCLOSURE_CHOICES,
    )
    approval_record = models.ForeignKey(
        'governance.ApprovalRecord',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_document_versions',
    )

    class Meta:
        db_table = 'documents_document_version'
        verbose_name = 'Document Version / दस्तऐवज आवृत्ती'
        verbose_name_plural = 'Document Versions / दस्तऐवज आवृत्त्या'
        ordering = ['translation', '-version_number']
        indexes = [
            models.Index(fields=['translation', '-version_number'], name='idx_doc_ver_trans_num'),
            models.Index(fields=['disclosure_status'], name='idx_doc_ver_status'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['translation', 'version_number'],
                name='uq_doc_version_seq',
            ),
            models.CheckConstraint(
                condition=Q(file_size_bytes__gt=0) & Q(file_size_bytes__lte=52428800),
                name='chk_file_size',
            ),
            models.CheckConstraint(
                condition=Q(version_number__gt=0),
                name='chk_doc_version_number_positive',
            ),
            models.CheckConstraint(
                condition=Q(disclosure_status__in=[c[0] for c in DISCLOSURE_CHOICES]),
                name='chk_valid_disclosure_status',
            ),
        ]

    def __str__(self):
        return f"{self.translation.title} [v{self.version_number}] ({self.disclosure_status})"

    def get_file_path(self) -> Path:
        """
        Resolves the private file path on disk with strict path traversal defenses.
        """
        return resolve_private_file_path(self.storage_path)

    def verify_integrity(self) -> bool:
        """
        Verifies that the physical file exists and matches checksum_sha256.
        """
        try:
            file_path = self.get_file_path()
            return verify_file_integrity(file_path, self.checksum_sha256)
        except Exception:
            return False

    def clean(self):
        super().clean()
        if self.pk:
            orig = DocumentVersion.objects.filter(pk=self.pk).first()
            if orig and orig.disclosure_status != DISCLOSURE_DRAFT:
                if (
                    self.storage_path != orig.storage_path
                    or self.checksum_sha256 != orig.checksum_sha256
                    or self.file_size_bytes != orig.file_size_bytes
                    or self.original_filename != orig.original_filename
                ):
                    raise ValidationError(
                        "Submitted, reviewed, or approved document versions are immutable. "
                        "Create a new document version row instead."
                    )

    def save(self, *args, **kwargs):
        if self.pk:
            orig = DocumentVersion.objects.filter(pk=self.pk).first()
            if orig and orig.disclosure_status != DISCLOSURE_DRAFT:
                if (
                    self.storage_path != orig.storage_path
                    or self.checksum_sha256 != orig.checksum_sha256
                    or self.file_size_bytes != orig.file_size_bytes
                    or self.original_filename != orig.original_filename
                ):
                    raise ValidationError(
                        "Submitted, reviewed, or approved document versions are immutable. "
                        "Create a new document version row instead."
                    )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.translation.document.retention_hold:
            raise ValidationError(
                "Document is under statutory retention hold; versions cannot be deleted."
            )
        if self.disclosure_status != DISCLOSURE_DRAFT:
            raise ValidationError(
                f"Cannot delete document version v{self.version_number} in '{self.disclosure_status}' status. "
                "Only unsubmitted private draft versions may be discarded."
            )
        # Attempt to remove disk file if draft
        try:
            p = self.get_file_path()
            if p.exists() and p.is_file():
                p.unlink()
        except Exception:
            pass
        return super().delete(*args, **kwargs)


@receiver(pre_delete, sender=Document)
def prevent_retention_hold_document_deletion(sender, instance, **kwargs):
    if instance.retention_hold:
        raise ValidationError(
            f"Document '{instance.reference_number or instance.id}' is under statutory retention hold and cannot be deleted."
        )


@receiver(pre_delete, sender=DocumentTranslation)
def prevent_retention_hold_doc_translation_deletion(sender, instance, **kwargs):
    if instance.document.retention_hold:
        raise ValidationError(
            f"Document is under statutory retention hold; translation '{instance.title}' cannot be deleted."
        )


