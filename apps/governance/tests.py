"""
Unit and integration tests for apps.governance models and constraints.
"""

from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from apps.identity.models import User
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_ROLLBACK,
    EVENT_WITHDRAWAL,
)


class GovernanceModelTests(TestCase):
    """
    Tests for ApprovalRecord, RejectionRecord, and PublicationEvent constraints.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            email='superadmin@gramsetu.in',
            full_name='Super Administrator',
            is_staff=True,
        )

    def test_approval_record_valid_hash_and_creation(self):
        valid_hash = 'a' * 64
        record = ApprovalRecord.objects.create(
            target_content_type='pagetranslation',
            target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
            revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
            revision_hash=valid_hash,
            approved_by=self.admin,
            notes='Approved without conditions.',
            is_self_approval=False,
        )
        self.assertIsNotNone(record.id)
        self.assertEqual(len(record.revision_hash), 64)
        self.assertIn('Approval for pagetranslation', str(record))

    def test_approval_record_clean_rejects_invalid_hash_length(self):
        short_hash = 'a' * 32
        record = ApprovalRecord(
            target_content_type='pagetranslation',
            target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
            revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
            revision_hash=short_hash,
            approved_by=self.admin,
        )
        with self.assertRaises(ValidationError) as ctx:
            record.clean()
        self.assertIn("64-character SHA-256", str(ctx.exception))

    def test_rejection_record_mandatory_reason_constraint(self):
        # Valid rejection record
        record = RejectionRecord.objects.create(
            target_content_type='pagetranslation',
            target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
            revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
            rejected_by=self.admin,
            rejection_reason='Inaccurate statistics provided for ward 3.',
        )
        self.assertIsNotNone(record.id)
        self.assertIn('Rejection for pagetranslation', str(record))

        # Rejection reason < 10 chars rejected by clean()
        short_record = RejectionRecord(
            target_content_type='pagetranslation',
            target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
            revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
            rejected_by=self.admin,
            rejection_reason='Short',
        )
        with self.assertRaises(ValidationError) as ctx:
            short_record.clean()
        self.assertIn("at least 10 non-whitespace characters", str(ctx.exception))

        # Rejection reason < 10 chars rejected by DB constraint
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                RejectionRecord.objects.create(
                    target_content_type='pagetranslation',
                    target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
                    revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
                    rejected_by=self.admin,
                    rejection_reason='Short',
                )

    def test_publication_event_date_constraint(self):
        now = timezone.now()
        # Invalid: effective_until <= effective_from
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PublicationEvent.objects.create(
                    target_content_type='pagetranslation',
                    target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
                    revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
                    event_type=EVENT_INITIAL_PUBLISH,
                    effective_from=now,
                    effective_until=now - timedelta(hours=1),
                    actor=self.admin,
                )

    def test_publication_event_justification_mandatory_for_rollback_and_withdrawal(self):
        now = timezone.now()
        # Rollback without justification fails in clean()
        event = PublicationEvent(
            target_content_type='pagetranslation',
            target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
            revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
            event_type=EVENT_ROLLBACK,
            effective_from=now,
            actor=self.admin,
            justification='',
        )
        with self.assertRaises(ValidationError) as ctx:
            event.clean()
        self.assertIn("requires a justification of at least 10", str(ctx.exception))

        # Rollback without justification fails in DB constraint
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PublicationEvent.objects.create(
                    target_content_type='pagetranslation',
                    target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
                    revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
                    event_type=EVENT_ROLLBACK,
                    effective_from=now,
                    actor=self.admin,
                    justification='',
                )

        # Withdrawal without justification fails in DB constraint
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PublicationEvent.objects.create(
                    target_content_type='pagetranslation',
                    target_id='0192a83f-42e1-7d31-89e4-c78216314abc',
                    revision_id='0192a83f-42e1-7d31-89e4-c78216314abd',
                    event_type=EVENT_WITHDRAWAL,
                    effective_from=now,
                    actor=self.admin,
                    justification='',
                )
