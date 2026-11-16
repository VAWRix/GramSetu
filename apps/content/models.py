"""
Informational Content models for GramSetu platform.

Implements Page (canonical anchor), PageTranslation, and PageRevision in accordance with
approved architectural specifications in docs/data-model.md and ADRs 0001, 0002, and 0003.
"""

import hashlib
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
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
)

# Language constants (Marathi-first)
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


class PageQuerySet(models.QuerySet):
    def published(self, language_code: str = LANGUAGE_MARATHI, allow_archived: bool = False):
        """
        Returns Pages that have an eligible published translation in the requested language.
        """
        published_translations = PageTranslation.objects.for_language(language_code).published(allow_archived=allow_archived)
        return self.filter(translations__in=published_translations).distinct()

    def delete(self):
        if self.filter(is_system_page=True).exists():
            raise ValidationError("Bulk deletion blocked: system pages are protected and cannot be deleted.")
        return super().delete()



class PageManager(models.Manager.from_queryset(PageQuerySet)):
    pass


class Page(models.Model):
    """
    Language-neutral logical anchor for an informational page (e.g. 'about-panchayat', 'village-history').
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    slug = models.SlugField(
        max_length=100,
        unique=True,
        allow_unicode=False,
        help_text="Language-neutral ASCII identifier (e.g., 'about-panchayat')",
    )
    is_system_page = models.BooleanField(
        default=False,
        help_text="If true, this page is required by system navigation and cannot be deleted.",
    )
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PageManager()

    class Meta:
        db_table = 'content_page'
        verbose_name = 'Page / पान'
        verbose_name_plural = 'Pages / पाने'
        ordering = ['display_order', 'slug']

    def __str__(self):
        return f"Page: {self.slug}"

    def delete(self, *args, **kwargs):
        if self.is_system_page:
            raise ValidationError("System pages are protected and cannot be deleted.")
        return super().delete(*args, **kwargs)


class PageTranslationQuerySet(models.QuerySet):
    def for_language(self, language_code: str):
        return self.filter(language_code=language_code)

    def published(self, allow_archived: bool = False):
        """
        Canonical 7-invariance SQL query for public eligibility (Section 3.3).
        A page translation is publicly visible iff:
        1. Root Page exists.
        2. current_approved_revision exists and editorial_status == 'approved'.
        3. Lifecycle status allows visibility:
           - 'published' AND effective_from <= NOW() AND (effective_until IS NULL OR effective_until > NOW())
           - 'scheduled' AND effective_from <= NOW() AND (effective_until IS NULL OR effective_until > NOW())
           - 'archived' ONLY IF allow_archived == True
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
                current_approved_revision__isnull=False,
                current_approved_revision__editorial_status=EDITORIAL_APPROVED,
            )
            .filter(status_filter)
            .exclude(status=STATUS_WITHDRAWN)
            .exclude(current_publication_event__event_type=EVENT_WITHDRAWAL)
        )


class PageTranslationManager(models.Manager.from_queryset(PageTranslationQuerySet)):
    pass


class PageTranslation(models.Model):
    """
    Language-specific translation row for a logical Page.
    Enforces the Explicit Translation Entity pattern (ADR 0001).
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name='translations',
    )
    language_code = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
    )
    localized_slug = models.SlugField(
        max_length=150,
        allow_unicode=True,
        help_text="Devanagari-capable localized slug for clean public URLs",
    )
    status = models.CharField(
        max_length=20,
        default=STATUS_DRAFT,
        choices=STATUS_CHOICES,
    )
    current_approved_revision = models.ForeignKey(
        'PageRevision',
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
        related_name='active_page_translations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PageTranslationManager()

    class Meta:
        db_table = 'content_page_translation'
        verbose_name = 'Page Translation / पान भाषांतर'
        verbose_name_plural = 'Page Translations / पान भाषांतरे'
        ordering = ['page', 'language_code']
        indexes = [
            models.Index(fields=['language_code', 'status'], name='idx_page_trans_lang_status'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['page', 'language_code'],
                name='uq_page_lang',
            ),
            models.UniqueConstraint(
                fields=['language_code', 'localized_slug'],
                name='uq_page_lang_localized_slug',
            ),
            models.CheckConstraint(
                condition=Q(language_code__in=['mr', 'hi', 'en']),
                name='chk_valid_page_lang',
            ),
            models.CheckConstraint(
                condition=Q(status__in=[c[0] for c in STATUS_CHOICES]),
                name='chk_valid_page_status',
            ),
        ]

    def __str__(self):
        return f"{self.page.slug} [{self.language_code}] ({self.status})"

    def clean(self):
        super().clean()
        if self.current_approved_revision_id:
            if self.current_approved_revision.translation_id != self.id:
                raise ValidationError("The approved revision must belong to this translation.")
            if self.current_approved_revision.editorial_status != EDITORIAL_APPROVED:
                raise ValidationError("The active approved revision must be in 'approved' status.")

    def is_publicly_visible(self, allow_archived: bool = False) -> bool:
        """
        Evaluates the 7 public availability invariants in Python.
        """
        if not self.page_id:
            return False
        if not self.current_approved_revision_id or self.current_approved_revision.editorial_status != EDITORIAL_APPROVED:
            return False
        if self.status == STATUS_WITHDRAWN:
            return False
        if self.status == STATUS_ARCHIVED and not allow_archived:
            return False
        if self.status not in (STATUS_PUBLISHED, STATUS_SCHEDULED, STATUS_ARCHIVED):
            return False

        pe = self.current_publication_event
        now = timezone.now()
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

    def create_next_revision(self, author, title=None, summary=None, body_markdown=None, sections_data=None, references_data=None):
        """
        Branches a new draft revision with an incremented revision sequence number.
        """
        latest = self.revisions.order_by('-revision_number').first()
        next_num = (latest.revision_number + 1) if latest else 1

        new_title = title if title is not None else (latest.title if latest else '')
        new_summary = summary if summary is not None else (latest.summary if latest else '')
        new_body = body_markdown if body_markdown is not None else (latest.body_markdown if latest else '')
        new_sections = sections_data if sections_data is not None else (latest.sections_data if latest else [])
        new_references = references_data if references_data is not None else (latest.references_data if latest else [])

        return PageRevision.objects.create(
            translation=self,
            revision_number=next_num,
            title=new_title,
            summary=new_summary,
            body_markdown=new_body,
            sections_data=new_sections,
            references_data=new_references,
            editorial_status=EDITORIAL_DRAFT,
            created_by=author,
        )


class PageRevisionQuerySet(models.QuerySet):
    def delete(self):
        if self.exclude(editorial_status=EDITORIAL_DRAFT).exists():
            raise ValidationError(
                "Bulk deletion blocked: cannot delete submitted or approved page revisions. "
                "Only unsubmitted draft revisions may be discarded."
            )
        return super().delete()


class PageRevisionManager(models.Manager.from_queryset(PageRevisionQuerySet)):
    pass


class PageRevision(models.Model):
    """
    Immutable content row storing a specific revision snapshot (ADR 0002).
    Once submitted or reviewed, content fields are strictly immutable.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    objects = PageRevisionManager()
    translation = models.ForeignKey(
        PageTranslation,
        on_delete=models.CASCADE,
        related_name='revisions',
    )
    revision_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    body_markdown = models.TextField()
    sections_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Structured Wikipedia-style sections (key, title, body_markdown, images, status, data_year, references)",
    )
    references_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Statutory research references (id, title, url, organization, data_year, verified)",
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
        related_name='created_page_revisions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'content_page_revision'
        verbose_name = 'Page Revision / पान आवृत्ती'
        verbose_name_plural = 'Page Revisions / पान आवृत्त्या'
        ordering = ['translation', '-revision_number']
        constraints = [
            models.UniqueConstraint(
                fields=['translation', 'revision_number'],
                name='uq_page_rev_seq',
            ),
            models.CheckConstraint(
                condition=Q(editorial_status__in=[c[0] for c in EDITORIAL_CHOICES]),
                name='chk_valid_page_editorial_status',
            ),
            models.CheckConstraint(
                condition=Q(revision_number__gt=0),
                name='chk_page_rev_number_positive',
            ),
        ]

    def __str__(self):
        return f"{self.translation.page.slug} [rev {self.revision_number}] ({self.editorial_status})"

    def calculate_hash(self) -> str:
        import json
        if not self.sections_data and not self.references_data:
            payload = f"{self.title.strip()}\n{self.summary.strip()}\n{self.body_markdown.strip()}".encode('utf-8')
        else:
            sec_str = json.dumps(self.sections_data, sort_keys=True)
            ref_str = json.dumps(self.references_data, sort_keys=True)
            payload = f"{self.title.strip()}\n{self.summary.strip()}\n{self.body_markdown.strip()}\n{sec_str}\n{ref_str}".encode('utf-8')
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
            orig = PageRevision.objects.filter(pk=self.pk).first()
            if orig and orig.editorial_status != EDITORIAL_DRAFT:
                if (
                    self.title != orig.title
                    or self.summary != orig.summary
                    or self.body_markdown != orig.body_markdown
                    or (self.sections_data != orig.sections_data)
                    or (self.references_data != orig.references_data)
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
            orig = PageRevision.objects.filter(pk=self.pk).first()
            if orig and orig.editorial_status != EDITORIAL_DRAFT:
                if (
                    self.title != orig.title
                    or self.summary != orig.summary
                    or self.body_markdown != orig.body_markdown
                    or (self.sections_data != orig.sections_data)
                    or (self.references_data != orig.references_data)
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


@receiver(pre_delete, sender=Page)
def prevent_system_page_deletion(sender, instance, **kwargs):
    if instance.is_system_page:
        raise ValidationError("System pages are protected and cannot be deleted.")


