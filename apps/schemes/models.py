"""
Welfare Schemes and Public Links domain models for GramSetu platform.

Implements WelfareScheme (canonical logical anchor), SchemeTranslation (multilingual explicit entity),
and SchemeRevision (immutable editorial snapshot) in accordance with approved architectural
specifications in docs/data-model.md Section 4.8 and ADRs 0001, 0002, 0003, and 0006.

Covers Central, Maharashtra State, and Zilla Parishad welfare schemes, eligibility criteria,
benefits, required documents, and informational application procedures.
"""

import hashlib
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone
from apps.core.utils import generate_uuid7
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_UPDATE_PUBLISH,
    EVENT_SCHEDULED_PUBLISH,
    EVENT_ROLLBACK,
    EVENT_WITHDRAWAL,
    EVENT_ARCHIVAL,
)

# Language constants (Marathi statutory primary)
LANGUAGE_MARATHI = 'mr'
LANGUAGE_HINDI = 'hi'
LANGUAGE_ENGLISH = 'en'

LANGUAGE_CHOICES = [
    (LANGUAGE_MARATHI, 'Marathi / मराठी'),
    (LANGUAGE_HINDI, 'Hindi / हिंदी'),
    (LANGUAGE_ENGLISH, 'English / इंग्रजी'),
]

# Scheme Level Constants (Section 4.8)
LEVEL_CENTRAL = 'central'
LEVEL_STATE = 'state'
LEVEL_DISTRICT = 'district'

SCHEME_LEVEL_CHOICES = [
    (LEVEL_CENTRAL, 'Central Government / केंद्र शासन'),
    (LEVEL_STATE, 'Maharashtra State Government / महाराष्ट्र राज्य शासन'),
    (LEVEL_DISTRICT, 'Zilla Parishad / District / जिल्हा परिषद / स्थानिक'),
]

# Target Beneficiary Constants (Section 4.8)
BENEFICIARY_FARMERS = 'farmers'
BENEFICIARY_WOMEN = 'women'
BENEFICIARY_YOUTH = 'youth'
BENEFICIARY_SENIOR_CITIZENS = 'senior_citizens'
BENEFICIARY_GENERAL = 'general'

BENEFICIARY_CHOICES = [
    (BENEFICIARY_FARMERS, 'Farmers & Agriculture / शेतकरी व कृषी'),
    (BENEFICIARY_WOMEN, 'Women & Child Welfare / महिला व बालविकास'),
    (BENEFICIARY_YOUTH, 'Youth & Education / युवक व शिक्षण'),
    (BENEFICIARY_SENIOR_CITIZENS, 'Senior Citizens / ज्येष्ठ नागरिक'),
    (BENEFICIARY_GENERAL, 'General Public / सर्वसामान्य नागरिक'),
]

# Editorial Revision Status (authoring & review lifecycle)
EDITORIAL_DRAFT = 'draft'
EDITORIAL_SUBMITTED = 'submitted'
EDITORIAL_APPROVED = 'approved'
EDITORIAL_REJECTED = 'rejected'

EDITORIAL_CHOICES = [
    (EDITORIAL_DRAFT, 'Draft / मसुदा'),
    (EDITORIAL_SUBMITTED, 'Submitted for Review / पुनरावलोकनासाठी सादर'),
    (EDITORIAL_APPROVED, 'Approved / मंजूर'),
    (EDITORIAL_REJECTED, 'Rejected / नाकारले'),
]

# Public Publication Lifecycle Status
STATUS_DRAFT = 'draft'
STATUS_SUBMITTED = 'submitted'
STATUS_APPROVED = 'approved'
STATUS_SCHEDULED = 'scheduled'
STATUS_PUBLISHED = 'published'
STATUS_WITHDRAWN = 'withdrawn'
STATUS_ARCHIVED = 'archived'

STATUS_CHOICES = [
    (STATUS_DRAFT, 'Draft / मसुदा'),
    (STATUS_SUBMITTED, 'Submitted / सादर'),
    (STATUS_APPROVED, 'Approved / मंजूर'),
    (STATUS_SCHEDULED, 'Scheduled / नियोजित'),
    (STATUS_PUBLISHED, 'Published / प्रकाशित'),
    (STATUS_WITHDRAWN, 'Withdrawn / मागे घेतले'),
    (STATUS_ARCHIVED, 'Archived / संग्रहित'),
]


class WelfareSchemeQuerySet(models.QuerySet):
    def published(self, language_code: str = LANGUAGE_MARATHI, allow_archived: bool = False):
        """
        Returns active schemes that have an approved, publicly visible translation
        in the requested language.
        """
        published_trans = SchemeTranslation.objects.for_language(language_code).published(allow_archived=allow_archived)
        return self.filter(
            is_active=True,
            translations__in=published_trans,
        ).distinct()

    def by_level(self, scheme_level: str):
        return self.filter(scheme_level=scheme_level)

    def by_beneficiary(self, target_beneficiary: str):
        return self.filter(target_beneficiary=target_beneficiary)


class WelfareSchemeManager(models.Manager.from_queryset(WelfareSchemeQuerySet)):
    pass


class WelfareScheme(models.Model):
    """
    Language-neutral logical anchor for a Government Welfare Scheme.
    Categorizes government programs by administrative level and beneficiary segment.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    slug = models.SlugField(
        max_length=150,
        unique=True,
        allow_unicode=False,
        help_text="Language-neutral ASCII identifier (e.g. 'pm-kisan-samman-nidhi')",
    )
    scheme_level = models.CharField(
        max_length=20,
        choices=SCHEME_LEVEL_CHOICES,
        db_index=True,
        help_text="Government tier sponsoring the scheme",
    )
    target_beneficiary = models.CharField(
        max_length=50,
        choices=BENEFICIARY_CHOICES,
        db_index=True,
        help_text="Target community or demographic segment",
    )
    official_portal_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Verified official government portal link (e.g. https://pmkisan.gov.in)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Administrative availability flag; if False, hidden from citizen portal",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Sorting priority within lists",
    )
    department = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text="Sponsoring department / संबंधित शासकीय विभाग",
    )
    contact_details = models.TextField(
        blank=True,
        default='',
        help_text="Nodal contact details / संपर्क माहिती व मार्गदर्शन",
    )
    supporting_documents = models.ManyToManyField(
        'documents.Document',
        blank=True,
        related_name='schemes',
        db_table='schemes_welfare_scheme_documents',
        help_text="Approved guidelines or application forms from Documents domain",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_schemes',
        help_text="Staff member who created the scheme container",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = WelfareSchemeManager()

    class Meta:
        db_table = 'schemes_welfare_scheme'
        verbose_name = 'Welfare Scheme / शासकीय योजना'
        verbose_name_plural = 'Welfare Schemes / शासकीय योजना'
        ordering = ['display_order', '-created_at']
        indexes = [
            models.Index(fields=['scheme_level', 'display_order'], name='idx_scheme_level_order'),
            models.Index(fields=['target_beneficiary'], name='idx_scheme_beneficiary'),
            models.Index(fields=['is_active', 'display_order'], name='idx_scheme_active_order'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(scheme_level__in=[c[0] for c in SCHEME_LEVEL_CHOICES]),
                name='chk_valid_scheme_level',
            ),
            models.CheckConstraint(
                condition=Q(target_beneficiary__in=[c[0] for c in BENEFICIARY_CHOICES]),
                name='chk_valid_target_beneficiary',
            ),
        ]

    def __str__(self):
        title = self.get_name(LANGUAGE_MARATHI) or self.slug
        return f"{title} ({self.get_scheme_level_display()})"

    def get_name(self, language_code: str = LANGUAGE_MARATHI) -> str:
        """
        Returns localized scheme name. Strict translation entity: zero silent fallback.
        """
        t = self.translations.filter(language_code=language_code).first()
        return t.scheme_name if t else ""

    def get_translation(self, language_code: str = LANGUAGE_MARATHI):
        """
        Returns the child SchemeTranslation for the given language.
        """
        return self.translations.filter(language_code=language_code).first()

    def is_publicly_visible(self, language_code: str = LANGUAGE_MARATHI, allow_archived: bool = False) -> bool:
        """
        Evaluates whether this scheme has an approved, publicly visible translation
        in the requested language.
        """
        if not self.is_active:
            return False
        trans = self.get_translation(language_code)
        if not trans:
            return False
        return trans.is_publicly_visible(allow_archived=allow_archived)


class SchemeTranslationQuerySet(models.QuerySet):
    def for_language(self, language_code: str):
        return self.filter(language_code=language_code)

    def published(self, allow_archived: bool = False):
        """
        Canonical 7-invariance SQL query for public scheme translation visibility (ADR 0003).
        A scheme translation is publicly visible iff:
        1. Root WelfareScheme is active (is_active = True).
        2. current_approved_revision exists and editorial_status == 'approved'.
        3. Status is 'published' or 'scheduled' with effective_from <= NOW().
        4. Status is not 'withdrawn'.
        5. Current publication event is not a withdrawal.
        """
        now = timezone.now()
        status_filter = (
            (
                Q(status=STATUS_PUBLISHED)
                & (Q(current_publication_event__effective_from__lte=now) | Q(current_publication_event__isnull=True))
                & (Q(current_publication_event__effective_until__isnull=True) | Q(current_publication_event__effective_until__gt=now))
            )
            | (
                Q(status=STATUS_SCHEDULED)
                & Q(current_publication_event__effective_from__lte=now)
                & (Q(current_publication_event__effective_until__isnull=True) | Q(current_publication_event__effective_until__gt=now))
            )
        )
        if allow_archived:
            status_filter |= Q(status=STATUS_ARCHIVED)

        return (
            self.filter(
                scheme__is_active=True,
                current_approved_revision__isnull=False,
                current_approved_revision__editorial_status=EDITORIAL_APPROVED,
            )
            .filter(status_filter)
            .exclude(status=STATUS_WITHDRAWN)
            .exclude(current_publication_event__event_type=EVENT_WITHDRAWAL)
        )


class SchemeTranslationManager(models.Manager.from_queryset(SchemeTranslationQuerySet)):
    pass


class SchemeTranslation(models.Model):
    """
    Language-specific translation entity for an official WelfareScheme.
    Enforces the Explicit Translation Entity pattern (ADR 0001).
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    scheme = models.ForeignKey(
        WelfareScheme,
        on_delete=models.CASCADE,
        related_name='translations',
    )
    language_code = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
    )
    localized_slug = models.SlugField(
        max_length=200,
        allow_unicode=True,
        help_text="Devanagari-capable localized slug for clean public URLs",
    )
    status = models.CharField(
        max_length=20,
        default=STATUS_DRAFT,
        choices=STATUS_CHOICES,
    )
    current_approved_revision = models.ForeignKey(
        'SchemeRevision',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text="Pointer to the currently active, immutable approved revision",
    )
    current_publication_event = models.ForeignKey(
        'governance.PublicationEvent',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text="Pointer to the most recent publication or withdrawal event",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SchemeTranslationManager()

    class Meta:
        db_table = 'schemes_scheme_translation'
        verbose_name = 'Scheme Translation / योजना भाषांतर'
        verbose_name_plural = 'Scheme Translations / योजना भाषांतरे'
        ordering = ['scheme', 'language_code']
        indexes = [
            models.Index(fields=['language_code', 'status'], name='idx_scheme_trans_lang_stat'),
            models.Index(fields=['scheme', 'language_code'], name='idx_scheme_trans_scheme_lang'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['scheme', 'language_code'],
                name='uq_scheme_lang',
            ),
            models.CheckConstraint(
                condition=Q(language_code__in=[c[0] for c in LANGUAGE_CHOICES]),
                name='chk_valid_scheme_lang',
            ),
            models.CheckConstraint(
                condition=Q(status__in=[c[0] for c in STATUS_CHOICES]),
                name='chk_valid_scheme_trans_status',
            ),
        ]

    def __str__(self):
        return f"{self.scheme.slug} [{self.language_code}] - {self.scheme_name or self.localized_slug}"

    def clean(self):
        super().clean()
        if self.current_approved_revision_id:
            if self.current_approved_revision.translation_id != self.id:
                raise ValidationError("The approved revision must belong to this translation.")
            if self.current_approved_revision.editorial_status != EDITORIAL_APPROVED:
                raise ValidationError("The active approved revision must be in 'approved' status.")

    @property
    def active_revision(self):
        """
        Returns the active approved revision, or latest draft revision if not yet published.
        """
        if self.current_approved_revision:
            return self.current_approved_revision
        return self.revisions.order_by('-revision_number').first()

    @property
    def scheme_name(self) -> str:
        rev = self.active_revision
        return rev.scheme_name if rev else ""

    @property
    def short_summary(self) -> str:
        rev = self.active_revision
        return rev.short_summary if rev else ""

    @property
    def eligibility_criteria(self) -> str:
        rev = self.active_revision
        return rev.eligibility_criteria if rev else ""

    @property
    def benefits(self) -> str:
        rev = self.active_revision
        return rev.benefits if rev else ""

    @property
    def required_documents(self) -> str:
        rev = self.active_revision
        return rev.required_documents if rev else ""

    @property
    def application_process(self) -> str:
        rev = self.active_revision
        return rev.application_process if rev else ""

    def is_publicly_visible(self, allow_archived: bool = False) -> bool:
        """
        Evaluates the canonical public availability invariants in Python.
        """
        if not self.scheme_id or not self.scheme.is_active:
            return False
        if not self.current_approved_revision_id or self.current_approved_revision.editorial_status != EDITORIAL_APPROVED:
            return False
        if self.status == STATUS_WITHDRAWN:
            return False
        if self.status == STATUS_ARCHIVED and not allow_archived:
            return False
        if self.status not in (STATUS_PUBLISHED, STATUS_SCHEDULED, STATUS_ARCHIVED):
            return False

        now = timezone.now()
        pe = self.current_publication_event
        if pe:
            if pe.event_type == EVENT_WITHDRAWAL:
                return False
            if pe.effective_from and pe.effective_from > now:
                return False
            if pe.effective_until and pe.effective_until <= now:
                return False
        else:
            if self.status == STATUS_SCHEDULED:
                return False

        return True

    def create_next_revision(
        self,
        author,
        scheme_name=None,
        short_summary=None,
        eligibility_criteria=None,
        benefits=None,
        required_documents=None,
        application_process=None,
    ):
        """
        Branches a new draft revision with an incremented revision sequence number.
        """
        latest = self.revisions.order_by('-revision_number').first()
        next_num = (latest.revision_number + 1) if latest else 1

        new_name = scheme_name if scheme_name is not None else (latest.scheme_name if latest else '')
        new_summary = short_summary if short_summary is not None else (latest.short_summary if latest else '')
        new_eligibility = eligibility_criteria if eligibility_criteria is not None else (latest.eligibility_criteria if latest else '')
        new_benefits = benefits if benefits is not None else (latest.benefits if latest else '')
        new_docs = required_documents if required_documents is not None else (latest.required_documents if latest else '')
        new_process = application_process if application_process is not None else (latest.application_process if latest else '')

        return SchemeRevision.objects.create(
            translation=self,
            revision_number=next_num,
            scheme_name=new_name,
            short_summary=new_summary,
            eligibility_criteria=new_eligibility,
            benefits=new_benefits,
            required_documents=new_docs,
            application_process=new_process,
            editorial_status=EDITORIAL_DRAFT,
            created_by=author,
        )


class SchemeRevisionQuerySet(models.QuerySet):
    def delete(self):
        if self.exclude(editorial_status=EDITORIAL_DRAFT).exists():
            raise ValidationError(
                "Bulk deletion blocked: cannot delete submitted or approved scheme revisions. "
                "Only unsubmitted draft revisions may be discarded."
            )
        return super().delete()


class SchemeRevisionManager(models.Manager.from_queryset(SchemeRevisionQuerySet)):
    pass


class SchemeRevision(models.Model):
    """
    Immutable content row storing a specific revision snapshot of a Scheme translation (ADR 0002).
    Once submitted or reviewed, content fields are strictly immutable.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    objects = SchemeRevisionManager()
    translation = models.ForeignKey(
        SchemeTranslation,
        on_delete=models.CASCADE,
        related_name='revisions',
    )
    revision_number = models.PositiveIntegerField()
    scheme_name = models.CharField(
        max_length=255,
        help_text="Official name of the scheme in this language (e.g. प्रधानमंत्री किसान सन्मान निधी)",
    )
    short_summary = models.CharField(
        max_length=500,
        help_text="Brief summary of the scheme's purpose and scope",
    )
    eligibility_criteria = models.TextField(
        help_text="Detailed statutory eligibility requirements / पात्रता निकष",
    )
    benefits = models.TextField(
        blank=True,
        help_text="Financial or material benefits / योजनेचे लाभ",
    )
    required_documents = models.TextField(
        help_text="Mandatory documents for application / आवश्यक कागदपत्रे (उदा. ७/१२ उतारा, आधार कार्ड)",
    )
    application_process = models.TextField(
        help_text="Informational application steps and official channels / अर्ज करण्याची प्रक्रिया",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 digest of normalized payload",
    )
    editorial_status = models.CharField(
        max_length=20,
        default=EDITORIAL_DRAFT,
        choices=EDITORIAL_CHOICES,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_scheme_revisions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'schemes_scheme_revision'
        verbose_name = 'Scheme Revision / योजना आवृत्ती'
        verbose_name_plural = 'Scheme Revisions / योजना आवृत्त्या'
        ordering = ['translation', 'revision_number']
        constraints = [
            models.UniqueConstraint(
                fields=['translation', 'revision_number'],
                name='uq_scheme_rev_seq',
            ),
            models.CheckConstraint(
                condition=Q(editorial_status__in=[c[0] for c in EDITORIAL_CHOICES]),
                name='chk_valid_scheme_editorial_status',
            ),
        ]

    def __str__(self):
        return f"{self.translation.scheme.slug} [{self.translation.language_code}] rev #{self.revision_number} ({self.editorial_status})"

    def calculate_hash(self) -> str:
        """
        Computes SHA-256 digest over normalized scheme content fields (ADR 0002).
        """
        payload = (
            f"name:{self.scheme_name.strip()}|"
            f"summary:{self.short_summary.strip()}|"
            f"eligibility:{self.eligibility_criteria.strip()}|"
            f"benefits:{self.benefits.strip()}|"
            f"docs:{self.required_documents.strip()}|"
            f"process:{self.application_process.strip()}"
        ).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def verify_integrity(self) -> bool:
        """
        Verifies that current content matches the recorded cryptographic hash.
        """
        if not self.content_hash:
            return False
        return self.calculate_hash() == self.content_hash

    def submit_for_review(self):
        """
        Freezes content, computes cryptographic hash, and transitions to submitted status.
        """
        if self.editorial_status != EDITORIAL_DRAFT:
            raise ValidationError("Only draft revisions can be submitted for review.")
        if not self.scheme_name or len(self.scheme_name.strip()) < 3:
            raise ValidationError("Scheme name must be at least 3 characters.")
        if not self.eligibility_criteria or len(self.eligibility_criteria.strip()) < 10:
            raise ValidationError("Eligibility criteria must be at least 10 characters.")
        if not self.required_documents or len(self.required_documents.strip()) < 5:
            raise ValidationError("Required documents must be specified (minimum 5 characters)..")
        if not self.application_process or len(self.application_process.strip()) < 10:
            raise ValidationError("Application process must be specified (minimum 10 characters).")

        self.content_hash = self.calculate_hash()
        self.editorial_status = EDITORIAL_SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=['content_hash', 'editorial_status', 'submitted_at'])

    def save(self, *args, **kwargs):
        # Auto-compute hash for draft rows if not set
        if not self.content_hash:
            self.content_hash = self.calculate_hash()

        # Enforce revision immutability after submission (ADR 0002)
        if self.pk:
            orig = SchemeRevision.objects.filter(pk=self.pk).first()
            if orig and orig.editorial_status != EDITORIAL_DRAFT:
                content_changed = (
                    orig.scheme_name != self.scheme_name
                    or orig.short_summary != self.short_summary
                    or orig.eligibility_criteria != self.eligibility_criteria
                    or orig.benefits != self.benefits
                    or orig.required_documents != self.required_documents
                    or orig.application_process != self.application_process
                    or orig.content_hash != self.content_hash
                )
                if content_changed:
                    raise ValidationError(
                        "Submitted and approved scheme revisions are strictly immutable (ADR 0002). "
                        "Create a new revision row to introduce changes."
                    )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.editorial_status != EDITORIAL_DRAFT:
            raise ValidationError(
                f"Cannot delete scheme revision #{self.revision_number} in '{self.editorial_status}' state. "
                "Only unsubmitted draft revisions may be discarded."
            )
        return super().delete(*args, **kwargs)



