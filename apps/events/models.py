"""
Events and Meetings domain models for GramSetu platform.

Implements PanchayatEvent (canonical logical anchor) and EventTranslation (multilingual explicit entity)
in accordance with approved architectural specifications in docs/data-model.md Section 4.7 and Section 8.
Covers Gram Sabha meetings, Ward meetings, public health camps, and administrative hearings.
"""

import hashlib
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from apps.core.utils import generate_uuid7

# Language constants (Marathi statutory primary)
LANGUAGE_MARATHI = 'mr'
LANGUAGE_HINDI = 'hi'
LANGUAGE_ENGLISH = 'en'

LANGUAGE_CHOICES = [
    (LANGUAGE_MARATHI, 'Marathi / मराठी'),
    (LANGUAGE_HINDI, 'Hindi / हिंदी'),
    (LANGUAGE_ENGLISH, 'English / इंग्रजी'),
]

# Statutory Event Types (Section 4.7)
EVENT_GRAM_SABHA = 'gram_sabha'
EVENT_WARD_MEETING = 'ward_meeting'
EVENT_HEALTH_CAMP = 'health_camp'
EVENT_HEARING = 'hearing'
EVENT_CULTURAL = 'cultural'

EVENT_TYPE_CHOICES = [
    (EVENT_GRAM_SABHA, 'Gram Sabha Meeting / ग्रामसभा बैठक'),
    (EVENT_WARD_MEETING, 'Ward Sabha Meeting / वॉर्ड सभा बैठक'),
    (EVENT_HEALTH_CAMP, 'Public Health / Vaccination Camp / आरोग्य / लसीकरण शिबिर'),
    (EVENT_HEARING, 'Administrative Grievance Hearing / प्रशासकीय तक्रार निवारण सुनावणी'),
    (EVENT_CULTURAL, 'National / Cultural Event / राष्ट्रीय / सांस्कृतिक कार्यक्रम'),
]

# Event Publication & Lifecycle Status
STATUS_DRAFT = 'draft'
STATUS_PENDING_APPROVAL = 'pending_approval'
STATUS_APPROVED = 'approved'
STATUS_PUBLISHED = 'published'
STATUS_CANCELLED = 'cancelled'
STATUS_COMPLETED = 'completed'
STATUS_ARCHIVED = 'archived'

STATUS_CHOICES = [
    (STATUS_DRAFT, 'Draft / मसुदा'),
    (STATUS_PENDING_APPROVAL, 'Pending Review / मंजुरी प्रलंबित'),
    (STATUS_APPROVED, 'Approved / मंजूर'),
    (STATUS_PUBLISHED, 'Published / प्रकाशित'),
    (STATUS_CANCELLED, 'Cancelled / रद्द'),
    (STATUS_COMPLETED, 'Completed / संपन्न'),
    (STATUS_ARCHIVED, 'Archived / संग्रहित'),
]


class PanchayatEventQuerySet(models.QuerySet):
    def public_eligible(self, allow_archived: bool = False):
        """
        Returns events eligible for public citizen viewing:
        - is_published is True
        - status is in ('published', 'completed', 'cancelled') (or 'archived' if allow_archived)
        """
        allowed_statuses = [STATUS_PUBLISHED, STATUS_COMPLETED, STATUS_CANCELLED]
        if allow_archived:
            allowed_statuses.append(STATUS_ARCHIVED)

        return self.filter(
            is_published=True,
            status__in=allowed_statuses,
        )

    def upcoming(self):
        """
        Returns active scheduled events that have not yet concluded,
        or cancelled events whose active alert window (6 hours) is still active.
        """
        now = timezone.now()
        expiry_hours = getattr(settings, 'MEETING_CANCELLATION_ALERT_HOURS', 6)
        cancellation_cutoff = now - timezone.timedelta(hours=expiry_hours)
        return self.filter(
            Q(end_datetime__gte=now, status__in=[STATUS_PUBLISHED, STATUS_APPROVED]) |
            Q(
                status=STATUS_CANCELLED,
                end_datetime__gte=now,
                cancelled_at__gte=cancellation_cutoff,
            ) |
            Q(
                status=STATUS_CANCELLED,
                end_datetime__gte=now,
                cancelled_at__isnull=True,
                updated_at__gte=cancellation_cutoff,
            )
        )

    def past(self):
        """
        Returns concluded historical events, plus cancelled events whose alert window has expired.
        """
        now = timezone.now()
        expiry_hours = getattr(settings, 'MEETING_CANCELLATION_ALERT_HOURS', 6)
        cancellation_cutoff = now - timezone.timedelta(hours=expiry_hours)
        return self.filter(
            Q(end_datetime__lt=now) |
            Q(
                status=STATUS_CANCELLED,
                cancelled_at__lt=cancellation_cutoff,
            ) |
            Q(
                status=STATUS_CANCELLED,
                cancelled_at__isnull=True,
                updated_at__lt=cancellation_cutoff,
            )
        )

    def for_language(self, language_code: str = LANGUAGE_MARATHI):
        """
        Filters events having an explicit translation in the requested language.
        No silent language fallback.
        """
        return self.filter(translations__language_code=language_code).distinct()


class PanchayatEventManager(models.Manager.from_queryset(PanchayatEventQuerySet)):
    pass


class PanchayatEvent(models.Model):
    """
    Canonical logical anchor for a Panchayat meeting, Gram Sabha, or public event.
    Tracks schedule, venues, statutory status, and cancellation history.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    event_type = models.CharField(
        max_length=30,
        choices=EVENT_TYPE_CHOICES,
        help_text="Official statutory category of the meeting or event",
    )
    status = models.CharField(
        max_length=20,
        default=STATUS_DRAFT,
        choices=STATUS_CHOICES,
        help_text="Lifecycle and publication status",
    )
    start_datetime = models.DateTimeField(
        help_text="Scheduled start date and time",
    )
    end_datetime = models.DateTimeField(
        help_text="Scheduled end date and time",
    )
    venue_mr = models.CharField(
        max_length=255,
        help_text="Primary statutory venue description in Marathi (e.g. ग्रामपंचायत सभागृह)",
    )
    venue_en = models.CharField(
        max_length=255,
        blank=True,
        help_text="Venue description in English",
    )
    venue_hi = models.CharField(
        max_length=255,
        blank=True,
        help_text="Venue description in Hindi",
    )
    is_published = models.BooleanField(
        default=False,
        help_text="Flag indicating whether this event has been approved and published to the public portal",
    )
    requires_registration = models.BooleanField(
        default=False,
        help_text="Flag indicating whether citizens require prior registration or must bring statutory credentials",
    )
    registration_instructions = models.TextField(
        blank=True,
        help_text="Citizen attendance and documentation instructions (e.g. bring Ration Card, register at GP office)",
    )
    cancellation_reason = models.TextField(
        blank=True,
        help_text="Mandatory statutory explanation if the meeting or event is cancelled",
    )
    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the event was officially cancelled",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_panchayat_events',
        help_text="Staff member who created the event",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PanchayatEventManager()

    class Meta:
        db_table = 'events_event'
        verbose_name = 'Panchayat Event / कार्यक्रम'
        verbose_name_plural = 'Panchayat Events / कार्यक्रम'
        ordering = ['-start_datetime']
        indexes = [
            models.Index(fields=['-start_datetime'], name='idx_event_start_dt'),
            models.Index(fields=['event_type', '-start_datetime'], name='idx_event_type_start'),
            models.Index(fields=['status', '-start_datetime'], name='idx_event_status_start'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_datetime__gte=F('start_datetime')),
                name='check_event_dates',
            ),
            models.CheckConstraint(
                condition=Q(event_type__in=[c[0] for c in EVENT_TYPE_CHOICES]),
                name='chk_valid_panchayat_event_type',
            ),
            models.CheckConstraint(
                condition=Q(status__in=[c[0] for c in STATUS_CHOICES]),
                name='chk_valid_event_status',
            ),
        ]

    def __str__(self):
        title = self.get_title(LANGUAGE_MARATHI) or self.get_event_type_display()
        return f"{title} ({self.start_datetime.strftime('%d-%m-%Y %H:%M')})"

    def clean(self):
        super().clean()
        if self.start_datetime and self.end_datetime:
            if self.end_datetime < self.start_datetime:
                raise ValidationError("End datetime must be greater than or equal to start datetime.")

        if self.status == STATUS_CANCELLED:
            if not self.cancellation_reason or len(self.cancellation_reason.strip()) < 10:
                raise ValidationError("A cancellation reason of at least 10 characters is mandatory when cancelling an event.")

        if self.is_published and self.status == STATUS_DRAFT:
            raise ValidationError("Draft events cannot be marked as published.")

    def calculate_hash(self) -> str:
        """
        Calculates a deterministic SHA-256 digest of event metadata and its translations
        for cryptographic binding in ApprovalRecord.
        """
        translations_data = []
        if self.pk:
            for t in self.translations.all().order_by('language_code'):
                translations_data.append(f"{t.language_code}:{t.title.strip()}:{t.agenda.strip()}")

        trans_str = "|".join(translations_data)
        payload = (
            f"{self.event_type}:{self.start_datetime.isoformat()}:{self.end_datetime.isoformat()}:"
            f"{self.venue_mr.strip()}:{trans_str}"
        ).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()

    def get_title(self, language_code: str = LANGUAGE_MARATHI) -> str:
        """
        Returns localized title for the requested language.
        Does not perform silent fallback across languages; returns empty string if not found.
        """
        t = self.translations.filter(language_code=language_code).first()
        return t.title if t else ""

    def get_venue(self, language_code: str = LANGUAGE_MARATHI) -> str:
        """
        Returns localized venue.
        """
        t = self.translations.filter(language_code=language_code).first()
        if t and t.venue_override:
            return t.venue_override
        if language_code == LANGUAGE_ENGLISH and self.venue_en:
            return self.venue_en
        if language_code == LANGUAGE_HINDI and self.venue_hi:
            return self.venue_hi
        return self.venue_mr

    def is_cancellation_alert_active(self, now=None) -> bool:
        """
        Returns True if the event is cancelled and the cancellation alert window
        has not yet expired. Configurable via MEETING_CANCELLATION_ALERT_HOURS (default 6).
        """
        if self.status != STATUS_CANCELLED:
            return False
        if now is None:
            now = timezone.now()
        expiry_hours = getattr(settings, 'MEETING_CANCELLATION_ALERT_HOURS', 6)
        reference_time = self.cancelled_at or self.updated_at
        if not reference_time:
            return False
        return now <= reference_time + timezone.timedelta(hours=expiry_hours)

    def is_publicly_visible(self, allow_archived: bool = False) -> bool:
        """
        Evaluates whether event is eligible for citizen public viewing.
        """
        if not self.is_published:
            return False
        if self.status in (STATUS_DRAFT, STATUS_PENDING_APPROVAL):
            return False
        if self.status == STATUS_ARCHIVED and not allow_archived:
            return False
        return self.status in (STATUS_PUBLISHED, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_ARCHIVED)

    def delete(self, *args, **kwargs):
        if self.is_published or self.status in (STATUS_PUBLISHED, STATUS_COMPLETED):
            raise ValidationError(
                "Published or completed events cannot be deleted. "
                "Use cancellation to preserve statutory public records."
            )
        return super().delete(*args, **kwargs)


class EventTranslation(models.Model):
    """
    Language-specific translation row for a PanchayatEvent.
    Enforces the Explicit Translation Entity pattern (ADR 0001).
    """
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(
        PanchayatEvent,
        on_delete=models.CASCADE,
        related_name='translations',
    )
    language_code = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    agenda = models.TextField(
        blank=True,
        help_text="Statutory meeting agenda, resolutions to be discussed, or event schedule",
    )
    venue_override = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional localized venue name override for this translation",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'events_event_translation'
        verbose_name = 'Event Translation / कार्यक्रम भाषांतर'
        verbose_name_plural = 'Event Translations / कार्यक्रम भाषांतरे'
        ordering = ['event', 'language_code']
        indexes = [
            models.Index(fields=['language_code'], name='idx_event_trans_lang'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'language_code'],
                name='uq_event_lang',
            ),
            models.CheckConstraint(
                condition=Q(language_code__in=['mr', 'hi', 'en']),
                name='chk_valid_event_lang',
            ),
        ]

    def __str__(self):
        return f"{self.title} [{self.language_code}]"
