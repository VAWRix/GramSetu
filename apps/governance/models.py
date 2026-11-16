"""
Governance and workflow models for GramSetu platform.

Implements ApprovalRecord, RejectionRecord, and PublicationEvent in accordance with
approved architectural specifications in docs/data-model.md and ADRs 0002 and 0003.
"""

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

# Publication event type constants
EVENT_INITIAL_PUBLISH = 'initial_publish'
EVENT_UPDATE_PUBLISH = 'update_publish'
EVENT_SCHEDULED_PUBLISH = 'scheduled_publish'
EVENT_URGENT_PUBLISH = 'urgent_publish'
EVENT_ROLLBACK = 'rollback'
EVENT_WITHDRAWAL = 'withdrawal'
EVENT_ARCHIVAL = 'archival'

PUBLICATION_EVENT_CHOICES = [
    (EVENT_INITIAL_PUBLISH, 'Initial Publication'),
    (EVENT_UPDATE_PUBLISH, 'Update Publication'),
    (EVENT_SCHEDULED_PUBLISH, 'Scheduled Publication'),
    (EVENT_URGENT_PUBLISH, 'Urgent Publication Bypass'),
    (EVENT_ROLLBACK, 'Rollback to Previous Revision'),
    (EVENT_WITHDRAWAL, 'Administrative Withdrawal'),
    (EVENT_ARCHIVAL, 'Automatic Expiry Archival'),
]


class ImmutableRecordQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError("Audit and governance records are append-only immutable ledgers and cannot be deleted.")


class ImmutableRecordManager(models.Manager.from_queryset(ImmutableRecordQuerySet)):
    pass


class ApprovalRecord(models.Model):
    """
    Formal sign-off by a Super Administrator binding to an exact, immutable content revision.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    objects = ImmutableRecordManager()
    target_content_type = models.CharField(
        max_length=100,
        help_text="Target entity type, e.g. pagetranslation, noticetranslation",
    )
    target_id = models.UUIDField(help_text="Primary key of target translation or entity")
    revision_id = models.UUIDField(help_text="Primary key of specific approved revision")
    revision_hash = models.CharField(max_length=64, help_text="SHA-256 digest of approved revision")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='approved_records',
    )
    approved_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    is_self_approval = models.BooleanField(default=False)
    content_title_snapshot = models.CharField(
        max_length=300,
        blank=True,
        default='',
        help_text="Historical content title snapshot at time of approval",
    )

    class Meta:
        db_table = 'governance_approval_record'
        verbose_name = 'Approval Record / मंजुरी नोंद'
        verbose_name_plural = 'Approval Records / मंजुरी नोंदी'
        ordering = ['-approved_at']
        indexes = [
            models.Index(fields=['target_id', '-approved_at'], name='idx_approval_target_date'),
            models.Index(fields=['revision_id'], name='idx_approval_revision'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length(F('revision_hash')), 64),
                name='chk_approval_hash_length',
            ),
        ]

    def __str__(self):
        return f"Approval for {self.target_content_type}:{self.revision_id} by {self.approved_by}"

    def clean(self):
        super().clean()
        if not self.revision_hash or len(self.revision_hash) != 64:
            raise ValidationError("Approval record must include a valid 64-character SHA-256 revision hash.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Approval records are immutable audit logs and cannot be deleted.")


class RejectionRecord(models.Model):
    """
    Mandatory administrative record when a submitted revision is rejected by a Super Administrator.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    objects = ImmutableRecordManager()
    target_content_type = models.CharField(max_length=100)
    target_id = models.UUIDField()
    revision_id = models.UUIDField()
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='rejection_records',
    )
    rejected_at = models.DateTimeField(auto_now_add=True)
    rejection_reason = models.TextField(
        help_text="Mandatory rationale for why content was rejected (min 10 characters)",
    )
    content_title_snapshot = models.CharField(
        max_length=300,
        blank=True,
        default='',
        help_text="Historical content title snapshot at time of rejection",
    )

    class Meta:
        db_table = 'governance_rejection_record'
        verbose_name = 'Rejection Record / नकार नोंद'
        verbose_name_plural = 'Rejection Records / नकार नोंदी'
        ordering = ['-rejected_at']
        indexes = [
            models.Index(fields=['target_id', '-rejected_at'], name='idx_rejection_target_date'),
            models.Index(fields=['revision_id'], name='idx_rejection_revision'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=GreaterThanOrEqual(Length(Trim(F('rejection_reason'))), 10),
                name='chk_rejection_reason',
            ),
        ]

    def __str__(self):
        return f"Rejection for {self.target_content_type}:{self.revision_id} by {self.rejected_by}"

    def clean(self):
        super().clean()
        if not self.rejection_reason or len(self.rejection_reason.strip()) < 10:
            raise ValidationError("Rejection reason must be at least 10 non-whitespace characters.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Rejection records are immutable audit logs and cannot be deleted.")


class PublicationEvent(models.Model):
    """
    Append-only historical ledger capturing every change in public visibility.
    """
    EVENT_INITIAL_PUBLISH = EVENT_INITIAL_PUBLISH
    EVENT_UPDATE_PUBLISH = EVENT_UPDATE_PUBLISH
    EVENT_SCHEDULED_PUBLISH = EVENT_SCHEDULED_PUBLISH
    EVENT_URGENT_PUBLISH = EVENT_URGENT_PUBLISH
    EVENT_ROLLBACK = EVENT_ROLLBACK
    EVENT_WITHDRAWAL = EVENT_WITHDRAWAL
    EVENT_ARCHIVAL = EVENT_ARCHIVAL
    EVENT_CHOICES = PUBLICATION_EVENT_CHOICES

    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    objects = ImmutableRecordManager()
    target_content_type = models.CharField(max_length=100)
    target_id = models.UUIDField()
    revision_id = models.UUIDField(help_text="The revision made live by this event")
    event_type = models.CharField(max_length=30, choices=PUBLICATION_EVENT_CHOICES)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='publication_events',
    )
    justification = models.TextField(
        blank=True,
        help_text="Mandatory for rollbacks, urgent publishes, and early withdrawals (min 10 characters)",
    )
    superseded_event = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='superseding_events',
    )
    content_title_snapshot = models.CharField(
        max_length=300,
        blank=True,
        default='',
        help_text="Historical content title snapshot at time of publication event",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governance_publication_event'
        verbose_name = 'Publication Event / प्रकाशन घटना'
        verbose_name_plural = 'Publication Events / प्रकाशन घटना'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['target_id', '-created_at'], name='idx_pub_event_target_date'),
            models.Index(fields=['target_content_type', 'target_id'], name='idx_pub_event_target_ct'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_until__isnull=True) | Q(effective_until__gt=F('effective_from')),
                name='chk_pub_dates',
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(event_type__in=['rollback', 'urgent_publish', 'withdrawal']) |
                    (Q(justification__isnull=False) & GreaterThanOrEqual(Length(Trim(F('justification'))), 10))
                ),
                name='chk_justification_mandatory',
            ),
            models.CheckConstraint(
                condition=Q(event_type__in=[c[0] for c in PUBLICATION_EVENT_CHOICES]),
                name='chk_valid_event_type',
            ),
        ]

    def __str__(self):
        return f"PublicationEvent [{self.event_type}] on {self.target_content_type}:{self.target_id} by {self.actor}"

    def clean(self):
        super().clean()
        if self.effective_until and self.effective_from and self.effective_until <= self.effective_from:
            raise ValidationError("Effective until must be strictly greater than effective from.")
        if self.event_type in (EVENT_ROLLBACK, EVENT_URGENT_PUBLISH, EVENT_WITHDRAWAL):
            if not self.justification or len(self.justification.strip()) < 10:
                raise ValidationError(
                    f"Event type '{self.event_type}' requires a justification of at least 10 non-whitespace characters."
                )

    def delete(self, *args, **kwargs):
        raise ValidationError("Publication events are append-only audit records and cannot be deleted.")


@receiver(pre_delete, sender=ApprovalRecord)
@receiver(pre_delete, sender=RejectionRecord)
@receiver(pre_delete, sender=PublicationEvent)
def prevent_governance_record_deletion(sender, instance, **kwargs):
    raise ValidationError(f"{sender.__name__} records are immutable audit logs and cannot be deleted.")

