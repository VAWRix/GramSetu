"""
Notices and Announcements domain models for GramSetu platform.

Implements Notice (canonical anchor), NoticeTranslation, NoticeRevision, and NoticeUrgentLog
in accordance with approved architectural specifications in docs/data-model.md (Section 4.5 and Section 6)
and ADRs 0001, 0002, 0003, and 0006.
"""

import hashlib
import json
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThanOrEqual
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
    EVENT_URGENT_PUBLISH,
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

# Notice Category / Type Constants
TYPE_GENERAL = 'general'
TYPE_TENDER = 'tender'
TYPE_STATUTORY = 'statutory'
TYPE_GRAM_SABHA = 'gram_sabha'
TYPE_EMERGENCY_ALERT = 'emergency_alert'

NOTICE_TYPE_CHOICES = [
    (TYPE_GENERAL, 'General Notice / सामान्य सूचना'),
    (TYPE_TENDER, 'Tender Notice / निविदा सूचना'),
    (TYPE_STATUTORY, 'Statutory / Legal Notice / वैधानिक सूचना'),
    (TYPE_GRAM_SABHA, 'Gram Sabha Announcement / ग्रामसभा जाहीर सूचना'),
    (TYPE_EMERGENCY_ALERT, 'Emergency Public Alert / आपत्कालीन जाहीर सूचना'),
]

# Urgency / Priority Constants
URGENCY_STANDARD = 'standard'
URGENCY_URGENT = 'urgent'

URGENCY_CHOICES = [
    (URGENCY_STANDARD, 'Standard Urgency / सर्वसाधारण'),
    (URGENCY_URGENT, 'Urgent / Priority / तातडीचे'),
]

# Post-Publication Ratification Status for Urgent Notices
RATIFICATION_PENDING = 'pending_review'
RATIFICATION_RATIFIED = 'ratified'
RATIFICATION_RETRACTED = 'retracted'

RATIFICATION_CHOICES = [
    (RATIFICATION_PENDING, 'Pending Post-Publication Review / पुनरावलोकन प्रलंबित'),
    (RATIFICATION_RATIFIED, 'Ratified by Super Admin / मंजूर (मान्यता प्राप्त)'),
    (RATIFICATION_RETRACTED, 'Retracted by Super Admin / मागे घेण्यात आले (रद्द)'),
]


class NoticeQuerySet(models.QuerySet):
    def published(self, language_code: str = LANGUAGE_MARATHI, allow_archived: bool = False):
        """
        Returns Notices that have an eligible published translation in the requested language.
        """
        published_translations = NoticeTranslation.objects.for_language(language_code).published(allow_archived=allow_archived)
        return self.filter(translations__in=published_translations).distinct()


class NoticeManager(models.Manager.from_queryset(NoticeQuerySet)):
    pass


class Notice(models.Model):
    """
    Logical anchor container for an official Notice or Announcement.
    Tracks notice category, urgency, reference number, effective window, and expiry.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    notice_type = models.CharField(
        max_length=30,
        choices=NOTICE_TYPE_CHOICES,
        default=TYPE_GENERAL,
        help_text="Category of notice",
    )
    urgency = models.CharField(
        max_length=20,
        choices=URGENCY_CHOICES,
        default=URGENCY_STANDARD,
        help_text="Priority level of notice",
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Official dispatch or reference number (जावक क्रमांक)",
    )
    issue_date = models.DateField(
        default=timezone.now,
        null=True,
        blank=True,
        help_text="Official date of notice issuance (जारी केल्याची तारीख)",
    )
    is_urgent_published = models.BooleanField(
        default=False,
        help_text="True if published via emergency bypass workflow without prior review",
    )
    effective_from = models.DateTimeField(
        default=timezone.now,
        help_text="Publication effective timestamp",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Automatic expiry timestamp (after which notice moves to archive)",
    )
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Submission or response deadline / अंतिम मुदत",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = NoticeManager()

    class Meta:
        db_table = 'notices_notice'
        verbose_name = 'Notice / सूचना'
        verbose_name_plural = 'Notices / सूचना'
        ordering = ['-effective_from', '-created_at']
        indexes = [
            models.Index(fields=['effective_from', 'expires_at'], name='idx_notice_dates'),
            models.Index(fields=['notice_type'], name='idx_notice_type'),
            models.Index(fields=['urgency'], name='idx_notice_urgency'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(expires_at__gt=F('effective_from')),
                name='chk_notice_dates',
            ),
        ]

    def __str__(self):
        ref = f" ({self.reference_number})" if self.reference_number else ""
        return f"{self.get_notice_type_display()}{ref} - {str(self.id)[:8]}"

    def clean(self):
        super().clean()
        if self.expires_at and self.effective_from:
            if self.expires_at <= self.effective_from:
                raise ValidationError("Expiry date must be strictly after the effective date.")

    def is_expired(self, now=None) -> bool:
        """
        Returns True if this notice has passed its configured expires_at timestamp.
        """
        current_time = now or timezone.now()
        return self.expires_at is not None and self.expires_at <= current_time

    def is_effective(self, now=None) -> bool:
        """
        Returns True if current time is within [effective_from, expires_at).
        """
        current_time = now or timezone.now()
        if self.effective_from > current_time:
            return False
        return not self.is_expired(current_time)

    @property
    def has_deadline(self) -> bool:
        return self.deadline is not None

    @property
    def is_deadline_passed(self) -> bool:
        if self.deadline is None:
            return False
        return self.deadline <= timezone.now()


class NoticeTranslationQuerySet(models.QuerySet):
    def for_language(self, language_code: str):
        return self.filter(language_code=language_code)

    def published(self, allow_archived: bool = False):
        """
        Canonical 7-invariance SQL query for public eligibility (Section 3.3).
        A notice translation is publicly visible iff:
        1. Root Notice exists.
        2. current_approved_revision exists and editorial_status == 'approved'.
        3. Root notice effective window reached: notice__effective_from <= NOW().
        4. Root notice not expired: notice__expires_at IS NULL OR notice__expires_at > NOW().
        5. Lifecycle status allows visibility:
           - 'published' AND effective_from <= NOW() AND (effective_until IS NULL OR effective_until > NOW())
           - 'scheduled' AND effective_from <= NOW() AND (effective_until IS NULL OR effective_until > NOW())
           - 'archived' ONLY IF allow_archived == True
        6. Status is not 'withdrawn'.
        7. Current publication event is not a withdrawal.
        """
        now = timezone.now()
        status_filter = (
            (
                Q(status=STATUS_PUBLISHED)
                & Q(notice__effective_from__lte=now)
                & (Q(notice__expires_at__isnull=True) | Q(notice__expires_at__gt=now))
                & (Q(current_publication_event__effective_from__lte=now) | Q(current_publication_event__isnull=True))
                & (Q(current_publication_event__effective_until__isnull=True) | Q(current_publication_event__effective_until__gt=now))
            )
            | (
                Q(status=STATUS_SCHEDULED)
                & Q(notice__effective_from__lte=now)
                & (Q(notice__expires_at__isnull=True) | Q(notice__expires_at__gt=now))
                & Q(current_publication_event__effective_from__lte=now)
                & (Q(current_publication_event__effective_until__isnull=True) | Q(current_publication_event__effective_until__gt=now))
            )
        )
        if allow_archived:
            status_filter |= (
                Q(status=STATUS_ARCHIVED)
                & Q(notice__effective_from__lte=now)
            )

        return (
            self.filter(
                current_approved_revision__isnull=False,
                current_approved_revision__editorial_status=EDITORIAL_APPROVED,
            )
            .filter(status_filter)
            .exclude(status=STATUS_WITHDRAWN)
            .exclude(current_publication_event__event_type=EVENT_WITHDRAWAL)
        )


class NoticeTranslationManager(models.Manager.from_queryset(NoticeTranslationQuerySet)):
    pass


class NoticeTranslation(models.Model):
    """
    Language-specific translation entity for an official Notice.
    Enforces the Explicit Translation Entity pattern (ADR 0001).
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    notice = models.ForeignKey(
        Notice,
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
        help_text="Devanagari-capable localized slug for clean public URLs",
    )
    status = models.CharField(
        max_length=20,
        default=STATUS_DRAFT,
        choices=STATUS_CHOICES,
    )
    current_approved_revision = models.ForeignKey(
        'NoticeRevision',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_for_translations',
    )
    current_publication_event = models.ForeignKey(
        'governance.PublicationEvent',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_notice_translations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = NoticeTranslationManager()

    class Meta:
        db_table = 'notices_notice_translation'
        verbose_name = 'Notice Translation / सूचना भाषांतर'
        verbose_name_plural = 'Notice Translations / सूचना भाषांतरे'
        ordering = ['notice', 'language_code']
        indexes = [
            models.Index(fields=['language_code', 'status'], name='idx_noticetrans_lang_status'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['notice', 'language_code'],
                name='uq_notice_lang',
            ),
            models.UniqueConstraint(
                fields=['language_code', 'slug'],
                name='uq_notice_lang_slug',
            ),
            models.UniqueConstraint(
                fields=['notice', 'language_code'],
                condition=Q(status=STATUS_PUBLISHED),
                name='uq_notice_active_published',
            ),
            models.CheckConstraint(
                condition=Q(language_code__in=['mr', 'hi', 'en']),
                name='chk_valid_notice_lang',
            ),
            models.CheckConstraint(
                condition=Q(status__in=[c[0] for c in STATUS_CHOICES]),
                name='chk_valid_notice_status',
            ),
        ]

    def __str__(self):
        return f"Notice [{self.language_code}] - {self.slug} ({self.status})"

    def clean(self):
        super().clean()
        if self.current_approved_revision_id:
            if self.current_approved_revision.translation_id != self.id:
                raise ValidationError("The approved revision must belong to this translation.")
            if self.current_approved_revision.editorial_status != EDITORIAL_APPROVED:
                raise ValidationError("The active approved revision must be in 'approved' status.")

    def is_publicly_visible(self, allow_archived: bool = False) -> bool:
        """
        Evaluates the canonical 7 public availability invariants in Python.
        """
        if not self.notice_id:
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

        # Check root notice effective and expiry window
        if self.notice.effective_from > now:
            return False
        if self.notice.expires_at and self.notice.expires_at <= now and not allow_archived:
            return False

        # Check publication event
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

    def create_next_revision(self, author, title=None, summary=None, body_markdown=None, attachments_metadata=None):
        """
        Branches a new draft revision with an incremented revision sequence number.
        """
        latest = self.revisions.order_by('-revision_number').first()
        next_num = (latest.revision_number + 1) if latest else 1

        new_title = title if title is not None else (latest.title if latest else '')
        new_summary = summary if summary is not None else (latest.summary if latest else '')
        new_body = body_markdown if body_markdown is not None else (latest.body_markdown if latest else '')
        new_att = attachments_metadata if attachments_metadata is not None else (latest.attachments_metadata if latest else [])

        return NoticeRevision.objects.create(
            translation=self,
            revision_number=next_num,
            title=new_title,
            summary=new_summary,
            body_markdown=new_body,
            attachments_metadata=new_att,
            editorial_status=EDITORIAL_DRAFT,
            created_by=author,
        )


class NoticeRevisionQuerySet(models.QuerySet):
    def delete(self):
        if self.exclude(editorial_status=EDITORIAL_DRAFT).exists():
            raise ValidationError(
                "Bulk deletion blocked: cannot delete submitted or approved notice revisions. "
                "Only unsubmitted draft revisions may be discarded."
            )
        return super().delete()


class NoticeRevisionManager(models.Manager.from_queryset(NoticeRevisionQuerySet)):
    pass


class NoticeRevision(models.Model):
    """
    Immutable content row storing a specific revision snapshot of a Notice translation (ADR 0002).
    Once submitted or reviewed, content fields are strictly immutable.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    objects = NoticeRevisionManager()
    translation = models.ForeignKey(
        NoticeTranslation,
        on_delete=models.CASCADE,
        related_name='revisions',
    )
    revision_number = models.PositiveIntegerField()
    title = models.CharField(max_length=300)
    summary = models.TextField(blank=True)
    body_markdown = models.TextField()
    attachments_metadata = models.JSONField(
        default=list,
        blank=True,
        help_text="Metadata list for attachments: title, original_filename, mime_type, file_size_bytes, checksum_sha256",
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
    is_urgent_bypass = models.BooleanField(
        default=False,
        help_text="True if this revision was created via urgent publication bypass",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_notice_revisions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notices_notice_revision'
        verbose_name = 'Notice Revision / सूचना आवृत्ती'
        verbose_name_plural = 'Notice Revisions / सूचना आवृत्त्या'
        ordering = ['translation', '-revision_number']
        constraints = [
            models.UniqueConstraint(
                fields=['translation', 'revision_number'],
                name='uq_notice_rev_seq',
            ),
            models.CheckConstraint(
                condition=Q(editorial_status__in=[c[0] for c in EDITORIAL_CHOICES]),
                name='chk_valid_notice_editorial_status',
            ),
            models.CheckConstraint(
                condition=Q(revision_number__gt=0),
                name='chk_notice_rev_number_positive',
            ),
        ]

    def __str__(self):
        return f"{self.translation} [rev {self.revision_number}] ({self.editorial_status})"

    def calculate_hash(self) -> str:
        att_norm = json.dumps(self.attachments_metadata, sort_keys=True) if self.attachments_metadata else ""
        payload = f"{self.title.strip()}\n{self.summary.strip()}\n{self.body_markdown.strip()}\n{att_norm}".encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def submit_for_review(self):
        """
        Transitions revision from draft to submitted. Locks editing and computes hash.
        """
        if self.editorial_status != EDITORIAL_DRAFT:
            raise ValidationError(f"Cannot submit revision in '{self.editorial_status}' status.")
        self.editorial_status = EDITORIAL_SUBMITTED
        self.content_hash = self.calculate_hash()
        self.submitted_at = timezone.now()
        self.save()

    def clean(self):
        super().clean()
        if self.pk:
            orig = NoticeRevision.objects.filter(pk=self.pk).first()
            if orig and orig.editorial_status != EDITORIAL_DRAFT:
                if (
                    self.title != orig.title
                    or self.summary != orig.summary
                    or self.body_markdown != orig.body_markdown
                    or self.attachments_metadata != orig.attachments_metadata
                    or (self.content_hash and self.content_hash != orig.content_hash)
                ):
                    raise ValidationError(
                        "Submitted and reviewed revisions are strictly immutable. "
                        "Create a new revision row instead."
                    )

    def save(self, *args, **kwargs):
        if not self.content_hash:
            self.content_hash = self.calculate_hash()
        if self.editorial_status == EDITORIAL_SUBMITTED and not self.submitted_at:
            self.submitted_at = timezone.now()
        if self.pk:
            orig = NoticeRevision.objects.filter(pk=self.pk).first()
            if orig and orig.editorial_status != EDITORIAL_DRAFT:
                if (
                    self.title != orig.title
                    or self.summary != orig.summary
                    or self.body_markdown != orig.body_markdown
                    or self.attachments_metadata != orig.attachments_metadata
                    or (self.content_hash and self.content_hash != orig.content_hash)
                ):
                    raise ValidationError(
                        "Submitted and reviewed revisions are strictly immutable. "
                        "Create a new revision row instead."
                    )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.editorial_status != EDITORIAL_DRAFT:
            raise ValidationError(
                f"Cannot delete revision #{self.revision_number} in '{self.editorial_status}' state. "
                "Only unsubmitted draft revisions may be discarded."
            )
        return super().delete(*args, **kwargs)


class NoticeUrgentLogQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError("Notice urgent audit logs are immutable records and cannot be deleted.")


class NoticeUrgentLogManager(models.Manager.from_queryset(NoticeUrgentLogQuerySet)):
    pass


class NoticeUrgentLog(models.Model):
    """
    Detailed operational audit record when an authorized Operator publishes an urgent notice
    without prior Super Administrator review (docs/data-model.md Section 4.5 and Section 6.2).
    """
    id = models.BigAutoField(primary_key=True)
    objects = NoticeUrgentLogManager()
    notice = models.ForeignKey(
        Notice,
        on_delete=models.PROTECT,
        related_name='urgent_logs',
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='urgent_notices_published',
    )
    urgent_authorization = models.ForeignKey(
        'identity.OperatorUrgentAuthorization',
        on_delete=models.PROTECT,
        related_name='notice_urgent_logs',
    )
    justification = models.TextField(
        help_text="Mandatory rationale explaining the emergency, minimum 15 characters",
    )
    published_at = models.DateTimeField(auto_now_add=True)
    ratified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='ratified_urgent_notices',
    )
    ratified_at = models.DateTimeField(null=True, blank=True)
    ratification_status = models.CharField(
        max_length=20,
        default=RATIFICATION_PENDING,
        choices=RATIFICATION_CHOICES,
    )
    ratification_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'notices_notice_urgent_log'
        verbose_name = 'Notice Urgent Log / तातडीची सूचना नोंद'
        verbose_name_plural = 'Notice Urgent Logs / तातडीच्या सूचना नोंदी'
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['ratification_status'], name='idx_urgent_ratification'),
            models.Index(fields=['notice', 'published_at'], name='idx_urgent_notice_pub'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length(Trim(F('justification'))), 15),
                name='chk_urgent_just',
            ),
        ]

    def __str__(self):
        return f"Urgent Notice {self.notice_id} by {self.operator} ({self.get_ratification_status_display()})"

    def clean(self):
        super().clean()
        cleaned_just = self.justification.strip() if self.justification else ""
        if len(cleaned_just) < 15:
            raise ValidationError("Urgent publication justification must be at least 15 non-whitespace characters.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Notice urgent audit logs are immutable records and cannot be deleted.")


@receiver(pre_delete, sender=NoticeUrgentLog)
def prevent_urgent_log_deletion(sender, instance, **kwargs):
    raise ValidationError("Notice urgent audit logs are immutable records and cannot be deleted.")

