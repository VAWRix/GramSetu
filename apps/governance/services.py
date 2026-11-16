"""
Governance and editorial publication workflow services for GramSetu platform.

Implements approval, rejection, publication, scheduling, withdrawal, and rollback workflows
using pessimistic row locking (SELECT FOR UPDATE) in accordance with ADR 0002, ADR 0003, and ADR 0006.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
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
)
from apps.content.models import (
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
    EDITORIAL_REJECTED,
    STATUS_SCHEDULED,
    STATUS_PUBLISHED,
    STATUS_WITHDRAWN,
)

LANGUAGE_MARATHI = 'mr'



def submit_page_revision(revision_id, author):
    """
    Submits a draft PageRevision for administrative review.
    - Locks revision row using select_for_update.
    - Verifies revision is in 'draft' status.
    - Calculates and stores SHA-256 content hash.
    - Transitions revision to 'submitted'.
    """
    with transaction.atomic():
        revision = PageRevision.objects.select_for_update().get(id=revision_id)
        if revision.editorial_status != EDITORIAL_DRAFT:
            raise ValidationError(
                f"Only revisions in 'draft' status can be submitted for review. Current status: '{revision.editorial_status}'."
            )
        revision.submit_for_review()
        return revision


def approve_page_revision(revision_id, approver, notes="", allow_self_approval=False):
    """
    Formally approves a PageRevision.
    - Locks the revision row using select_for_update.
    - Verifies revision is in 'submitted' status.
    - Verifies cryptographic hash integrity.
    - Enforces separation of duties (authors cannot approve their own revisions unless explicitly allowed).
    - Transitions revision to 'approved'.
    - Generates and returns an immutable ApprovalRecord.
    """
    with transaction.atomic():
        revision = PageRevision.objects.select_for_update().get(id=revision_id)
        from apps.identity.permissions import is_super_admin
        is_admin = is_super_admin(approver)

        if revision.editorial_status != EDITORIAL_SUBMITTED:
            if is_admin and revision.editorial_status == 'draft':
                pass
            else:
                raise ValidationError(
                    f"Only revisions in 'submitted' status can be approved. Current status: '{revision.editorial_status}'."
                )

        # Hash verification
        computed_hash = revision.calculate_hash()
        if not revision.content_hash and is_admin:
            revision.content_hash = computed_hash
        elif revision.content_hash != computed_hash:
            raise ValidationError("Revision hash mismatch. Content payload does not match submission digest.")

        is_self = (revision.created_by_id == approver.pk)
        if is_self and not allow_self_approval:
            raise ValidationError("Separation of duties violation: authors cannot approve their own content revision.")

        revision.editorial_status = EDITORIAL_APPROVED
        revision.save(update_fields=['editorial_status'])

        approval = ApprovalRecord.objects.create(
            target_content_type='pagetranslation',
            target_id=revision.translation_id,
            revision_id=revision.id,
            revision_hash=revision.content_hash,
            approved_by=approver,
            notes=notes,
            is_self_approval=is_self,
            content_title_snapshot=revision.title,
        )
        return approval


def reject_page_revision(revision_id, rejected_by, reason):
    """
    Formally rejects a submitted PageRevision.
    - Locks the revision row using select_for_update.
    - Verifies revision is in 'submitted' status.
    - Enforces mandatory reason >= 10 non-whitespace chars.
    - Transitions revision to 'rejected'.
    - Generates and returns an immutable RejectionRecord.
    """
    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Rejection reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        revision = PageRevision.objects.select_for_update().get(id=revision_id)
        if revision.editorial_status != EDITORIAL_SUBMITTED:
            raise ValidationError(
                f"Only revisions in 'submitted' status can be rejected. Current status: '{revision.editorial_status}'."
            )

        revision.editorial_status = EDITORIAL_REJECTED
        revision.save(update_fields=['editorial_status'])

        rejection = RejectionRecord.objects.create(
            target_content_type='pagetranslation',
            target_id=revision.translation_id,
            revision_id=revision.id,
            rejected_by=rejected_by,
            rejection_reason=cleaned_reason,
            content_title_snapshot=revision.title,
        )
        return rejection


def publish_page_translation(translation_id, revision_id, actor, effective_from=None, effective_until=None, justification=""):
    """
    Publishes or schedules a PageTranslation with an approved PageRevision.
    - Locks translation and revision rows using select_for_update.
    - Verifies revision belongs to translation and is 'approved'.
    - Verifies justification if this is a rollback or update.
    - Sets current_approved_revision pointer and updates status (published or scheduled).
    - Records an append-only PublicationEvent referencing any superseded event.
    """
    now = timezone.now()
    eff_from = effective_from or now

    with transaction.atomic():
        translation = PageTranslation.objects.select_for_update().get(id=translation_id)
        revision = PageRevision.objects.select_for_update().get(id=revision_id)
        from apps.identity.permissions import is_super_admin
        is_admin = is_super_admin(actor)

        if revision.translation_id != translation.id:
            raise ValidationError("The revision does not belong to the target translation.")

        is_scheduled = eff_from > now
        new_status = STATUS_SCHEDULED if is_scheduled else STATUS_PUBLISHED

        # Idempotency check: prevent duplicate publication events if already published with this revision
        if (
            translation.current_approved_revision_id == revision.id
            and translation.status == new_status
            and translation.current_publication_event is not None
        ):
            return translation.current_publication_event

        if revision.editorial_status != EDITORIAL_APPROVED:
            if is_admin:
                approve_page_revision(
                    revision_id=revision.id,
                    approver=actor,
                    notes=justification or "Direct publication approval by Super Administrator",
                    allow_self_approval=True,
                )
                revision.refresh_from_db()
            else:
                raise ValidationError("Cannot publish a revision that has not been approved.")

        # Determine event type
        if translation.current_approved_revision_id is None:
            event_type = EVENT_SCHEDULED_PUBLISH if eff_from > now else EVENT_INITIAL_PUBLISH
        elif translation.current_approved_revision_id != revision.id:
            # Check if this is a rollback to an older revision
            if revision.revision_number < translation.current_approved_revision.revision_number:
                event_type = EVENT_ROLLBACK
                if not justification or len(justification.strip()) < 10:
                    raise ValidationError("Rollback requires a justification of at least 10 characters.")
            else:
                event_type = EVENT_UPDATE_PUBLISH
        else:
            event_type = EVENT_UPDATE_PUBLISH

        is_scheduled = eff_from > now
        new_status = STATUS_SCHEDULED if is_scheduled else STATUS_PUBLISHED

        event = PublicationEvent.objects.create(
            target_content_type='pagetranslation',
            target_id=translation.id,
            revision_id=revision.id,
            event_type=event_type,
            scheduled_for=eff_from if is_scheduled else None,
            effective_from=eff_from,
            effective_until=effective_until,
            actor=actor,
            justification=justification.strip() if justification else "",
            superseded_event=translation.current_publication_event,
            content_title_snapshot=revision.title,
        )

        translation.current_approved_revision = revision
        translation.current_publication_event = event
        translation.status = new_status
        translation.save(update_fields=['current_approved_revision', 'current_publication_event', 'status', 'updated_at'])

        return event


def withdraw_page_translation(translation_id, actor, justification):
    """
    Administratively withdraws a PageTranslation, immediately severing public visibility.
    - Locks translation row using select_for_update.
    - Requires mandatory justification >= 10 chars.
    - Sets status to 'withdrawn'.
    - Records a PublicationEvent of type 'withdrawal'.
    """
    cleaned_justification = justification.strip() if justification else ""
    if len(cleaned_justification) < 10:
        raise ValidationError("Withdrawal requires a justification of at least 10 non-whitespace characters.")

    with transaction.atomic():
        translation = PageTranslation.objects.select_for_update().get(id=translation_id)
        rev_id = translation.current_approved_revision_id or translation.id

        title_snap = translation.current_approved_revision.title if translation.current_approved_revision else translation.localized_slug
        event = PublicationEvent.objects.create(
            target_content_type='pagetranslation',
            target_id=translation.id,
            revision_id=rev_id,
            event_type=EVENT_WITHDRAWAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=cleaned_justification,
            superseded_event=translation.current_publication_event,
            content_title_snapshot=title_snap,
        )

        translation.status = STATUS_WITHDRAWN
        translation.current_publication_event = event
        translation.save(update_fields=['status', 'current_publication_event', 'updated_at'])

        return event


# ------------------------------------------------------------------------------
# Notice Domain Governance Services
# ------------------------------------------------------------------------------

def submit_notice_revision(revision_id, author):
    """
    Submits a draft NoticeRevision for administrative review.
    - Locks revision row using select_for_update.
    - Verifies revision is in 'draft' status.
    - Calculates and stores SHA-256 content hash.
    - Transitions revision to 'submitted'.
    """
    from apps.notices.models import NoticeRevision, EDITORIAL_DRAFT
    with transaction.atomic():
        revision = NoticeRevision.objects.select_for_update().get(id=revision_id)
        if revision.editorial_status != EDITORIAL_DRAFT:
            raise ValidationError(
                f"Only revisions in 'draft' status can be submitted for review. Current status: '{revision.editorial_status}'."
            )
        revision.submit_for_review()
        return revision


def approve_notice_revision(revision_id, approver, notes="", allow_self_approval=False):
    """
    Formally approves a NoticeRevision.
    - Locks the revision row using select_for_update.
    - Verifies revision is in 'submitted' status.
    - Verifies cryptographic hash integrity.
    - Enforces separation of duties (authors cannot approve their own revisions unless explicitly allowed).
    - Transitions revision to 'approved'.
    - Generates and returns an immutable ApprovalRecord.
    """
    from apps.notices.models import NoticeRevision, EDITORIAL_SUBMITTED, EDITORIAL_APPROVED
    from apps.identity.permissions import is_super_admin
    with transaction.atomic():
        revision = NoticeRevision.objects.select_for_update().get(id=revision_id)
        is_admin = is_super_admin(approver)

        if revision.editorial_status != EDITORIAL_SUBMITTED:
            if is_admin and revision.editorial_status == 'draft':
                pass
            else:
                raise ValidationError(
                    f"Only revisions in 'submitted' status can be approved. Current status: '{revision.editorial_status}'."
                )

        # Hash verification
        computed_hash = revision.calculate_hash()
        if not revision.content_hash and is_admin:
            revision.content_hash = computed_hash
        elif revision.content_hash != computed_hash:
            raise ValidationError("Revision hash mismatch. Content payload does not match submission digest.")

        is_self = (revision.created_by_id == approver.pk)
        if is_self and not allow_self_approval:
            raise ValidationError("Separation of duties violation: authors cannot approve their own content revision.")

        revision.editorial_status = EDITORIAL_APPROVED
        revision.save(update_fields=['editorial_status'])

        approval = ApprovalRecord.objects.create(
            target_content_type='noticetranslation',
            target_id=revision.translation_id,
            revision_id=revision.id,
            revision_hash=revision.content_hash,
            approved_by=approver,
            notes=notes,
            is_self_approval=is_self,
            content_title_snapshot=revision.title,
        )
        return approval


def reject_notice_revision(revision_id, rejected_by, reason):
    """
    Formally rejects a submitted NoticeRevision.
    - Locks the revision row using select_for_update.
    - Verifies revision is in 'submitted' status.
    - Enforces mandatory reason >= 10 non-whitespace chars.
    - Transitions revision to 'rejected'.
    - Generates and returns an immutable RejectionRecord.
    """
    from apps.notices.models import NoticeRevision, EDITORIAL_SUBMITTED, EDITORIAL_REJECTED
    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Rejection reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        revision = NoticeRevision.objects.select_for_update().get(id=revision_id)
        if revision.editorial_status != EDITORIAL_SUBMITTED:
            raise ValidationError(
                f"Only revisions in 'submitted' status can be rejected. Current status: '{revision.editorial_status}'."
            )

        revision.editorial_status = EDITORIAL_REJECTED
        revision.save(update_fields=['editorial_status'])

        rejection = RejectionRecord.objects.create(
            target_content_type='noticetranslation',
            target_id=revision.translation_id,
            revision_id=revision.id,
            rejected_by=rejected_by,
            rejection_reason=cleaned_reason,
            content_title_snapshot=revision.title,
        )
        return rejection


def publish_notice_translation(translation_id, revision_id, actor, effective_from=None, effective_until=None, justification=""):
    """
    Publishes or schedules a NoticeTranslation with an approved NoticeRevision.
    - Locks translation and revision rows using select_for_update.
    - Verifies revision belongs to translation and is 'approved'.
    - Verifies justification if this is a rollback or update.
    - Sets current_approved_revision pointer and updates status (published or scheduled).
    - Records an append-only PublicationEvent referencing any superseded event.
    """
    from apps.notices.models import NoticeTranslation, NoticeRevision, EDITORIAL_APPROVED, STATUS_SCHEDULED, STATUS_PUBLISHED
    now = timezone.now()
    eff_from = effective_from or now

    from apps.identity.permissions import is_super_admin
    is_admin = is_super_admin(actor)

    with transaction.atomic():
        translation = NoticeTranslation.objects.select_for_update().get(id=translation_id)
        revision = NoticeRevision.objects.select_for_update().get(id=revision_id)

        if revision.translation_id != translation.id:
            raise ValidationError("The revision does not belong to the target translation.")

        is_scheduled = eff_from > now
        new_status = STATUS_SCHEDULED if is_scheduled else STATUS_PUBLISHED

        # Idempotency check: prevent duplicate publication events if already published with this revision
        if (
            translation.current_approved_revision_id == revision.id
            and translation.status == new_status
            and translation.current_publication_event is not None
        ):
            return translation.current_publication_event

        if revision.editorial_status != EDITORIAL_APPROVED:
            if is_admin:
                approve_notice_revision(
                    revision_id=revision.id,
                    approver=actor,
                    notes=justification or "Direct publication approval by Super Administrator",
                    allow_self_approval=True,
                )
                revision.refresh_from_db()
            else:
                raise ValidationError("Cannot publish a revision that has not been approved.")

        # Determine event type
        if translation.current_approved_revision_id is None:
            event_type = EVENT_SCHEDULED_PUBLISH if eff_from > now else EVENT_INITIAL_PUBLISH
        elif translation.current_approved_revision_id != revision.id:
            # Check if this is a rollback to an older revision
            if revision.revision_number < translation.current_approved_revision.revision_number:
                event_type = EVENT_ROLLBACK
                if not justification or len(justification.strip()) < 10:
                    raise ValidationError("Rollback requires a justification of at least 10 characters.")
            else:
                event_type = EVENT_UPDATE_PUBLISH
        else:
            event_type = EVENT_UPDATE_PUBLISH

        is_scheduled = eff_from > now
        new_status = STATUS_SCHEDULED if is_scheduled else STATUS_PUBLISHED

        event = PublicationEvent.objects.create(
            target_content_type='noticetranslation',
            target_id=translation.id,
            revision_id=revision.id,
            event_type=event_type,
            scheduled_for=eff_from if is_scheduled else None,
            effective_from=eff_from,
            effective_until=effective_until,
            actor=actor,
            justification=justification.strip() if justification else "",
            superseded_event=translation.current_publication_event,
            content_title_snapshot=revision.title,
        )

        translation.current_approved_revision = revision
        translation.current_publication_event = event
        translation.status = new_status
        translation.save(update_fields=['current_approved_revision', 'current_publication_event', 'status', 'updated_at'])

        return event


def withdraw_notice_translation(translation_id, actor, justification):
    """
    Administratively withdraws a NoticeTranslation, immediately severing public visibility.
    - Locks translation row using select_for_update.
    - Requires mandatory justification >= 10 chars.
    - Sets status to 'withdrawn'.
    - Records a PublicationEvent of type 'withdrawal'.
    """
    from apps.notices.models import NoticeTranslation, STATUS_WITHDRAWN
    cleaned_justification = justification.strip() if justification else ""
    if len(cleaned_justification) < 10:
        raise ValidationError("Withdrawal requires a justification of at least 10 non-whitespace characters.")

    with transaction.atomic():
        translation = NoticeTranslation.objects.select_for_update().get(id=translation_id)
        rev_id = translation.current_approved_revision_id or translation.id

        title_snap = translation.current_approved_revision.title if translation.current_approved_revision else (translation.notice.reference_number or translation.slug)
        event = PublicationEvent.objects.create(
            target_content_type='noticetranslation',
            target_id=translation.id,
            revision_id=rev_id,
            event_type=EVENT_WITHDRAWAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=cleaned_justification,
            superseded_event=translation.current_publication_event,
            content_title_snapshot=title_snap,
        )

        translation.status = STATUS_WITHDRAWN
        translation.current_publication_event = event
        translation.save(update_fields=['status', 'current_publication_event', 'updated_at'])

        return event


def urgent_publish_notice(notice_id, translation_id, revision_id, operator, urgent_authorization_id, justification):
    """
    Executes urgent publication bypass for an authorized Operator (Section 6.2).
    - Locks Notice, NoticeTranslation, and NoticeRevision rows.
    - Validates operator holds an active, valid OperatorUrgentAuthorization.
    - Validates justification >= 15 non-whitespace chars.
    - Sets notice.urgency = 'urgent', is_urgent_published = True.
    - Sets revision.editorial_status = 'approved', is_urgent_bypass = True.
    - Sets translation.status = 'published', current_approved_revision = revision.
    - Creates PublicationEvent(event_type='urgent_publish', justification=justification).
    - Creates NoticeUrgentLog(ratification_status='pending_review').
    """
    from apps.notices.models import (
        Notice,
        NoticeTranslation,
        NoticeRevision,
        NoticeUrgentLog,
        EDITORIAL_APPROVED,
        STATUS_PUBLISHED,
        URGENCY_URGENT,
        RATIFICATION_PENDING,
    )
    from apps.identity.models import OperatorUrgentAuthorization

    cleaned_just = justification.strip() if justification else ""
    if len(cleaned_just) < 15:
        raise ValidationError("Urgent publication justification must be at least 15 non-whitespace characters.")

    with transaction.atomic():
        auth = OperatorUrgentAuthorization.objects.select_for_update().get(id=urgent_authorization_id)
        if not auth.is_valid:
            raise ValidationError("The operator urgent authorization is expired, revoked, or not yet active.")
        if auth.operator_id != operator.pk:
            raise ValidationError("This urgent authorization was issued to a different operator.")

        notice = Notice.objects.select_for_update().get(id=notice_id)
        translation = NoticeTranslation.objects.select_for_update().get(id=translation_id)
        revision = NoticeRevision.objects.select_for_update().get(id=revision_id)

        if translation.notice_id != notice.id:
            raise ValidationError("The translation does not belong to the target notice.")
        if revision.translation_id != translation.id:
            raise ValidationError("The revision does not belong to the target translation.")

        # Update notice
        notice.urgency = URGENCY_URGENT
        notice.is_urgent_published = True
        notice.save(update_fields=['urgency', 'is_urgent_published', 'updated_at'])

        # Update revision to approved bypass
        revision.editorial_status = EDITORIAL_APPROVED
        revision.is_urgent_bypass = True
        if not revision.content_hash:
            revision.content_hash = revision.calculate_hash()
        revision.save(update_fields=['editorial_status', 'is_urgent_bypass', 'content_hash'])

        # Create publication event
        event = PublicationEvent.objects.create(
            target_content_type='noticetranslation',
            target_id=translation.id,
            revision_id=revision.id,
            event_type=EVENT_URGENT_PUBLISH,
            effective_from=timezone.now(),
            actor=operator,
            justification=cleaned_just,
            superseded_event=translation.current_publication_event,
            content_title_snapshot=revision.title,
        )

        # Update translation
        translation.current_approved_revision = revision
        translation.current_publication_event = event
        translation.status = STATUS_PUBLISHED
        translation.save(update_fields=['current_approved_revision', 'current_publication_event', 'status', 'updated_at'])

        # Create NoticeUrgentLog
        urgent_log = NoticeUrgentLog.objects.create(
            notice=notice,
            operator=operator,
            urgent_authorization=auth,
            justification=cleaned_just,
            ratification_status=RATIFICATION_PENDING,
        )

        return urgent_log


def ratify_urgent_notice(urgent_log_id, super_admin, notes=""):
    """
    Super Administrator ratifies an urgent notice within post-publication review.
    - Sets urgent_log.ratification_status = 'ratified'
    - Creates an ApprovalRecord for statutory documentation.
    """
    from apps.notices.models import NoticeUrgentLog, RATIFICATION_PENDING, RATIFICATION_RATIFIED
    with transaction.atomic():
        urgent_log = NoticeUrgentLog.objects.select_for_update().get(id=urgent_log_id)
        if urgent_log.ratification_status != RATIFICATION_PENDING:
            raise ValidationError(
                f"Only urgent notices with status 'pending_review' can be ratified. Current: '{urgent_log.ratification_status}'."
            )

        urgent_log.ratification_status = RATIFICATION_RATIFIED
        urgent_log.ratified_by = super_admin
        urgent_log.ratified_at = timezone.now()
        urgent_log.ratification_notes = notes.strip() if notes else "Ratified by Super Administrator"
        urgent_log.save(update_fields=['ratification_status', 'ratified_by', 'ratified_at', 'ratification_notes'])

        # Statutory documentation via ApprovalRecord
        primary_trans = urgent_log.notice.translations.first()
        rev_id = primary_trans.current_approved_revision_id if primary_trans else None
        rev_hash = primary_trans.current_approved_revision.content_hash if (primary_trans and primary_trans.current_approved_revision) else '0' * 64

        notice_title = primary_trans.current_approved_revision.title if (primary_trans and primary_trans.current_approved_revision) else (urgent_log.notice.reference_number or 'Urgent Notice')
        ApprovalRecord.objects.create(
            target_content_type='noticetranslation',
            target_id=primary_trans.id if primary_trans else urgent_log.notice.id,
            revision_id=rev_id or urgent_log.notice.id,
            revision_hash=rev_hash,
            approved_by=super_admin,
            notes=f"Post-publication ratification of Urgent Notice #{urgent_log.id}: {notes}",
            is_self_approval=False,
            content_title_snapshot=notice_title,
        )
        return urgent_log


def retract_urgent_notice(urgent_log_id, super_admin, reason):
    """
    Super Administrator retracts an unjustified or obsolete urgent notice.
    - Sets urgent_log.ratification_status = 'retracted'
    - Withdraws all translations of the notice (severing public visibility).
    """
    from apps.notices.models import NoticeUrgentLog, RATIFICATION_PENDING, RATIFICATION_RETRACTED
    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Retraction reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        urgent_log = NoticeUrgentLog.objects.select_for_update().get(id=urgent_log_id)
        if urgent_log.ratification_status != RATIFICATION_PENDING:
            raise ValidationError(
                f"Only urgent notices with status 'pending_review' can be retracted. Current: '{urgent_log.ratification_status}'."
            )

        urgent_log.ratification_status = RATIFICATION_RETRACTED
        urgent_log.ratified_by = super_admin
        urgent_log.ratified_at = timezone.now()
        urgent_log.ratification_notes = cleaned_reason
        urgent_log.save(update_fields=['ratification_status', 'ratified_by', 'ratified_at', 'ratification_notes'])

        # Immediately sever public visibility for all translations of this notice
        for trans in urgent_log.notice.translations.all():
            withdraw_notice_translation(
                trans.id,
                super_admin,
                justification=f"Retraction of Urgent Notice #{urgent_log.id}: {cleaned_reason}",
            )

        return urgent_log


# ------------------------------------------------------------------------------
# Document Domain Governance Services (ADR 0004)
# ------------------------------------------------------------------------------

def submit_document_version_for_disclosure(version_id, uploader):
    """
    Submits a draft DocumentVersion for administrative disclosure review.
    - Locks DocumentVersion row using select_for_update.
    - Verifies version is in 'draft' disclosure status.
    - Verifies physical file exists and SHA-256 integrity.
    - Transitions version to 'pending_approval'.
    - Updates DocumentTranslation status to 'pending_approval' if currently in draft.
    """
    from apps.documents.models import DocumentVersion, DISCLOSURE_DRAFT, DISCLOSURE_PENDING_APPROVAL, STATUS_DRAFT, STATUS_PENDING_APPROVAL

    with transaction.atomic():
        version = DocumentVersion.objects.select_for_update().get(id=version_id)
        if version.disclosure_status != DISCLOSURE_DRAFT:
            raise ValidationError(
                f"Only document versions in 'draft' status can be submitted for disclosure review. Current: '{version.disclosure_status}'."
            )

        # Integrity verification before submission
        if not version.verify_integrity():
            raise ValidationError("File integrity check failed or physical file is missing from private storage.")

        version.disclosure_status = DISCLOSURE_PENDING_APPROVAL
        version.save(update_fields=['disclosure_status'])

        translation = version.translation
        if translation.status == STATUS_DRAFT:
            translation.status = STATUS_PENDING_APPROVAL
            translation.save(update_fields=['status', 'updated_at'])

        return version


def approve_document_disclosure(version_id, approver, notes="", justification="", allow_self_approval=False):
    """
    Formally approves a DocumentVersion for public citizen disclosure (ADR 0004).
    - Locks DocumentVersion and DocumentTranslation rows using select_for_update.
    - Verifies version is in 'pending_approval' status.
    - Verifies physical file integrity.
    - Enforces confidentiality boundary: confidential documents can NEVER be disclosed.
    - Enforces separation of duties: authors/uploaders cannot approve their own documents for disclosure.
    - Transitions version to 'approved_for_disclosure'.
    - Creates immutable ApprovalRecord.
    - Creates append-only PublicationEvent.
    - Updates translation.current_version and sets translation.status to 'disclosed'.
    """
    from apps.documents.models import (
        DocumentTranslation,
        DocumentVersion,
        DISCLOSURE_PENDING_APPROVAL,
        DISCLOSURE_APPROVED,
        STATUS_DISCLOSED,
    )

    from apps.identity.permissions import is_super_admin
    is_admin = is_super_admin(approver)

    with transaction.atomic():
        version = DocumentVersion.objects.select_for_update().get(id=version_id)
        translation = DocumentTranslation.objects.select_for_update().get(id=version.translation_id)

        # Idempotency check: prevent duplicate disclosure events
        if (
            translation.current_version_id == version.id
            and translation.status == STATUS_DISCLOSED
            and translation.current_publication_event is not None
            and translation.current_publication_event.event_type != EVENT_WITHDRAWAL
        ):
            return version, None, translation.current_publication_event

        if version.disclosure_status != DISCLOSURE_PENDING_APPROVAL:
            if is_admin and version.disclosure_status == 'draft':
                pass
            elif version.disclosure_status == DISCLOSURE_APPROVED:
                pass
            else:
                raise ValidationError(
                    f"Only versions in 'pending_approval' status can be approved for disclosure. Current: '{version.disclosure_status}'."
                )

        # Confidentiality check
        if translation.document.is_confidential:
            raise ValidationError("Confidential documents cannot be approved for public disclosure.")

        # Physical integrity check
        if not version.verify_integrity():
            raise ValidationError("File integrity check failed or physical file is missing from private storage.")

        # Separation of duties enforcement
        is_self = (version.uploaded_by_id == approver.pk)
        if is_self and not allow_self_approval:
            raise ValidationError(
                "Separation of duties violation: authors and uploaders cannot approve their own document for disclosure."
            )

        # Determine event type (initial publish, update publish, or rollback)
        if translation.current_version_id is None:
            event_type = EVENT_INITIAL_PUBLISH
        elif translation.current_version_id != version.id:
            if version.version_number < translation.current_version.version_number:
                event_type = EVENT_ROLLBACK
                if not justification or len(justification.strip()) < 10:
                    raise ValidationError("Rollback requires a justification of at least 10 characters.")
            else:
                event_type = EVENT_UPDATE_PUBLISH
        else:
            event_type = EVENT_UPDATE_PUBLISH

        version.disclosure_status = DISCLOSURE_APPROVED

        # Create or reuse ApprovalRecord
        doc_title = translation.title or translation.document.reference_number or 'Document'
        approval = version.approval_record
        if not approval:
            approval = ApprovalRecord.objects.create(
                target_content_type='documenttranslation',
                target_id=translation.id,
                revision_id=version.id,
                revision_hash=version.checksum_sha256,
                approved_by=approver,
                notes=notes,
                is_self_approval=is_self,
                content_title_snapshot=doc_title,
            )
            version.approval_record = approval
            version.save(update_fields=['disclosure_status', 'approval_record'])
        else:
            version.save(update_fields=['disclosure_status'])

        # Create PublicationEvent
        event_justification = justification.strip() if justification else (notes.strip() if notes else f"Disclosure approved for version {version.version_number}")
        event = PublicationEvent.objects.create(
            target_content_type='documenttranslation',
            target_id=translation.id,
            revision_id=version.id,
            event_type=event_type,
            effective_from=timezone.now(),
            actor=approver,
            justification=event_justification,
            superseded_event=translation.current_publication_event,
            content_title_snapshot=doc_title,
        )

        # Update translation pointers and status
        translation.current_version = version
        translation.current_publication_event = event
        translation.status = STATUS_DISCLOSED
        translation.save(update_fields=['current_version', 'current_publication_event', 'status', 'updated_at'])

        return version, approval, event


def reject_document_disclosure(version_id, rejected_by, reason):
    """
    Formally rejects a submitted DocumentVersion for disclosure.
    - Locks DocumentVersion row using select_for_update.
    - Verifies version is in 'pending_approval' status.
    - Enforces mandatory reason >= 10 non-whitespace characters.
    - Transitions version to 'rejected'.
    - Generates immutable RejectionRecord.
    - If translation has no live disclosed version, resets translation status to 'draft'.
    """
    from apps.documents.models import (
        DocumentTranslation,
        DocumentVersion,
        DISCLOSURE_PENDING_APPROVAL,
        DISCLOSURE_REJECTED,
        STATUS_DRAFT,
    )

    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Rejection reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        version = DocumentVersion.objects.select_for_update().get(id=version_id)
        if version.disclosure_status != DISCLOSURE_PENDING_APPROVAL:
            raise ValidationError(
                f"Only versions in 'pending_approval' status can be rejected. Current: '{version.disclosure_status}'."
            )

        version.disclosure_status = DISCLOSURE_REJECTED
        version.save(update_fields=['disclosure_status'])

        translation = version.translation
        doc_title = translation.title or translation.document.reference_number or 'Document'
        rejection = RejectionRecord.objects.create(
            target_content_type='documenttranslation',
            target_id=translation.id,
            revision_id=version.id,
            rejected_by=rejected_by,
            rejection_reason=cleaned_reason,
            content_title_snapshot=doc_title,
        )

        if translation.current_version_id is None:
            translation.status = STATUS_DRAFT
            translation.save(update_fields=['status', 'updated_at'])

        return version, rejection


def withdraw_document_translation(translation_id, actor, justification):
    """
    Administratively withdraws a DocumentTranslation, immediately severing public citizen access (ADR 0004).
    - Locks DocumentTranslation row using select_for_update.
    - Requires mandatory justification >= 10 characters.
    - Sets translation status to 'withdrawn'.
    - Creates a PublicationEvent of type 'withdrawal'.
    - Physical files on disk remain strictly preserved for statutory legal and audit integrity.
    """
    from apps.documents.models import DocumentTranslation, STATUS_WITHDRAWN

    cleaned_justification = justification.strip() if justification else ""
    if len(cleaned_justification) < 10:
        raise ValidationError("Withdrawal requires a justification of at least 10 non-whitespace characters.")

    with transaction.atomic():
        translation = DocumentTranslation.objects.select_for_update().get(id=translation_id)
        rev_id = translation.current_version_id or translation.id

        doc_title = translation.title or translation.document.reference_number or 'Document'
        event = PublicationEvent.objects.create(
            target_content_type='documenttranslation',
            target_id=translation.id,
            revision_id=rev_id,
            event_type=EVENT_WITHDRAWAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=cleaned_justification,
            superseded_event=translation.current_publication_event,
            content_title_snapshot=doc_title,
        )

        translation.status = STATUS_WITHDRAWN
        translation.current_publication_event = event
        translation.save(update_fields=['status', 'current_publication_event', 'updated_at'])

        return event


# ------------------------------------------------------------------------------
# Event & Meeting Domain Governance Services (Section 4.7)
# ------------------------------------------------------------------------------

def submit_event_for_approval(event_id, actor):
    """
    Submits a draft PanchayatEvent for administrative review and publication approval.
    - Locks PanchayatEvent row using select_for_update.
    - Asserts event is in 'draft' status.
    - Asserts statutory Marathi translation exists.
    - Asserts end_datetime >= start_datetime.
    - Transitions event status to 'pending_approval'.
    """
    from apps.events.models import PanchayatEvent, STATUS_DRAFT, STATUS_PENDING_APPROVAL, LANGUAGE_MARATHI

    with transaction.atomic():
        event = PanchayatEvent.objects.select_for_update().get(id=event_id)
        if event.status != STATUS_DRAFT:
            raise ValidationError(
                f"Only events in 'draft' status can be submitted for review. Current status: '{event.status}'."
            )

        if not event.translations.filter(language_code=LANGUAGE_MARATHI).exists():
            raise ValidationError(
                "A statutory Marathi translation (mr) is mandatory before an event can be submitted for review."
            )

        if event.end_datetime < event.start_datetime:
            raise ValidationError("End datetime must be greater than or equal to start datetime.")

        event.status = STATUS_PENDING_APPROVAL
        event.save(update_fields=['status', 'updated_at'])
        return event


def approve_and_publish_event(event_id, approver, notes="", effective_from=None, allow_self_approval=False):
    """
    Formally approves and publishes a PanchayatEvent to the official portal.
    - Locks PanchayatEvent row using select_for_update.
    - Asserts event is in 'pending_approval' or 'draft' status.
    - Enforces separation of duties (authors cannot approve their own events).
    - Supports scheduling if effective_from is in the future.
    - Creates immutable ApprovalRecord.
    - Creates append-only PublicationEvent.
    - Sets is_published = True and status = 'published'.
    """
    from apps.events.models import (
        PanchayatEvent,
        STATUS_DRAFT,
        STATUS_PENDING_APPROVAL,
        STATUS_PUBLISHED,
        LANGUAGE_MARATHI,
    )

    from apps.identity.permissions import is_super_admin
    is_admin = is_super_admin(approver)

    with transaction.atomic():
        event = PanchayatEvent.objects.select_for_update().get(id=event_id)

        # Idempotency check: prevent duplicate publication events if already published
        if event.status == STATUS_PUBLISHED and event.is_published:
            existing_event = PublicationEvent.objects.filter(
                target_content_type='panchayatevent',
                target_id=event.id,
            ).order_by('-created_at').first()
            if existing_event:
                return event, None, existing_event

        if event.status not in (STATUS_DRAFT, STATUS_PENDING_APPROVAL):
            raise ValidationError(
                f"Only events in 'draft' or 'pending_approval' status can be approved. Current: '{event.status}'."
            )

        if not event.translations.filter(language_code=LANGUAGE_MARATHI).exists():
            raise ValidationError(
                "A statutory Marathi translation (mr) is mandatory before an event can be published."
            )

        if event.end_datetime < event.start_datetime:
            raise ValidationError("End datetime must be greater than or equal to start datetime.")

        is_self = (event.created_by_id == approver.pk)
        if is_self and not allow_self_approval:
            raise ValidationError(
                "Separation of duties violation: authors cannot approve their own event for publication."
            )

        event_hash = event.calculate_hash()
        event_title = event.get_title(LANGUAGE_MARATHI) or event.get_title() or 'Panchayat Event'

        approval = ApprovalRecord.objects.create(
            target_content_type='panchayatevent',
            target_id=event.id,
            revision_id=event.id,
            revision_hash=event_hash,
            approved_by=approver,
            notes=notes,
            is_self_approval=is_self,
            content_title_snapshot=event_title,
        )

        now = timezone.now()
        eff_from = effective_from or now
        is_scheduled = eff_from > now

        if is_scheduled:
            event_type = EVENT_SCHEDULED_PUBLISH
        elif not event.is_published:
            event_type = EVENT_INITIAL_PUBLISH
        else:
            event_type = EVENT_UPDATE_PUBLISH

        event_justification = notes.strip() if notes else f"Event approved and published by {approver.email}"

        pub_event = PublicationEvent.objects.create(
            target_content_type='panchayatevent',
            target_id=event.id,
            revision_id=event.id,
            event_type=event_type,
            scheduled_for=eff_from if is_scheduled else None,
            effective_from=eff_from,
            actor=approver,
            justification=event_justification,
            content_title_snapshot=event_title,
        )

        event.status = STATUS_PUBLISHED
        event.is_published = True
        event.save(update_fields=['status', 'is_published', 'updated_at'])

        return event, approval, pub_event


def reject_event(event_id, rejected_by, reason):
    """
    Formally rejects a submitted PanchayatEvent.
    - Locks PanchayatEvent row using select_for_update.
    - Requires mandatory rationale >= 10 non-whitespace characters.
    - Resets event status to 'draft'.
    - Generates immutable RejectionRecord.
    """
    from apps.events.models import PanchayatEvent, STATUS_DRAFT, STATUS_PENDING_APPROVAL

    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Rejection reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        event = PanchayatEvent.objects.select_for_update().get(id=event_id)
        if event.status != STATUS_PENDING_APPROVAL:
            raise ValidationError(
                f"Only events in 'pending_approval' status can be rejected. Current: '{event.status}'."
            )

        event.status = STATUS_DRAFT
        event.save(update_fields=['status', 'updated_at'])
        event_title = event.get_title(LANGUAGE_MARATHI) or event.get_title() or 'Panchayat Event'

        rejection = RejectionRecord.objects.create(
            target_content_type='panchayatevent',
            target_id=event.id,
            revision_id=event.id,
            rejected_by=rejected_by,
            rejection_reason=cleaned_reason,
            content_title_snapshot=event_title,
        )

        return event, rejection


def cancel_event(event_id, actor, reason):
    """
    Formally cancels a PanchayatEvent with a mandatory statutory reason.
    - Locks PanchayatEvent row using select_for_update.
    - Requires mandatory rationale >= 10 non-whitespace characters.
    - Sets event status to 'cancelled' and stores cancellation_reason.
    - Creates a PublicationEvent recording the cancellation.
    - Preserves historical event record for citizen transparency and statutory audit.
    """
    from apps.events.models import PanchayatEvent, STATUS_CANCELLED

    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Cancellation reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        event = PanchayatEvent.objects.select_for_update().get(id=event_id)
        if event.status == STATUS_CANCELLED:
            raise ValidationError("Event is already cancelled.")

        event.status = STATUS_CANCELLED
        event.cancellation_reason = cleaned_reason
        event.cancelled_at = timezone.now()
        event.save(update_fields=['status', 'cancellation_reason', 'cancelled_at', 'updated_at'])

        event_title = event.get_title(LANGUAGE_MARATHI) or event.get_title() or 'Panchayat Event'
        pub_event = PublicationEvent.objects.create(
            target_content_type='panchayatevent',
            target_id=event.id,
            revision_id=event.id,
            event_type=EVENT_WITHDRAWAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=cleaned_reason,
            content_title_snapshot=event_title,
        )

        return event, pub_event


def withdraw_event(event_id, actor, justification):
    """
    Administratively withdraws a PanchayatEvent from public visibility.
    - Locks PanchayatEvent row using select_for_update.
    - Requires mandatory justification >= 10 characters.
    - Immediately severs public citizen visibility: is_published = False.
    - Creates a PublicationEvent of type 'withdrawal'.
    - Preserves record on database for administrative and statutory audit.
    """
    from apps.events.models import PanchayatEvent

    cleaned_justification = justification.strip() if justification else ""
    if len(cleaned_justification) < 10:
        raise ValidationError("Withdrawal requires a justification of at least 10 non-whitespace characters.")

    with transaction.atomic():
        event = PanchayatEvent.objects.select_for_update().get(id=event_id)
        if not event.is_published:
            raise ValidationError("Event is not currently published.")

        event.is_published = False
        event.save(update_fields=['is_published', 'updated_at'])
        event_title = event.get_title(LANGUAGE_MARATHI) or event.get_title() or 'Panchayat Event'

        pub_event = PublicationEvent.objects.create(
            target_content_type='panchayatevent',
            target_id=event.id,
            revision_id=event.id,
            event_type=EVENT_WITHDRAWAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=cleaned_justification,
            content_title_snapshot=event_title,
        )

        return event, pub_event


def mark_concluded_events_completed():
    """
    Idempotent maintenance task to transition published events whose end_datetime
    has passed to 'completed' status.
    Completed events remain publicly accessible in historical records.
    """
    from apps.events.models import PanchayatEvent, STATUS_PUBLISHED, STATUS_COMPLETED
    now = timezone.now()
    count = (
        PanchayatEvent.objects
        .filter(is_published=True, status=STATUS_PUBLISHED, end_datetime__lt=now)
        .update(status=STATUS_COMPLETED, updated_at=now)
    )
    return count


def archive_event(event_id, actor, justification=""):
    """
    Administratively archives a completed or cancelled PanchayatEvent to 'archived' status.
    - Locks PanchayatEvent row using select_for_update.
    - Sets event status to 'archived'.
    - Records an append-only PublicationEvent of type 'archival'.
    """
    from apps.events.models import PanchayatEvent, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_ARCHIVED
    from apps.governance.models import EVENT_ARCHIVAL

    with transaction.atomic():
        event = PanchayatEvent.objects.select_for_update().get(id=event_id)
        if event.status not in (STATUS_COMPLETED, STATUS_CANCELLED):
            raise ValidationError(
                f"Only completed or cancelled events can be archived. Current status: '{event.status}'."
            )

        event.status = STATUS_ARCHIVED
        event.save(update_fields=['status', 'updated_at'])

        just = justification.strip() if justification else f"Statutory archival by {actor.email}"
        event_title = event.get_title(LANGUAGE_MARATHI) or event.get_title() or 'Panchayat Event'
        pub_event = PublicationEvent.objects.create(
            target_content_type='panchayatevent',
            target_id=event.id,
            revision_id=event.id,
            event_type=EVENT_ARCHIVAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=just,
            content_title_snapshot=event_title,
        )

        return event, pub_event


def archive_concluded_events(older_than_days=180):
    """
    Idempotent maintenance task to transition aged completed or cancelled events
    to 'archived' status (Section 6 & 10.2).
    Sets status = STATUS_ARCHIVED.
    """
    from datetime import timedelta
    from apps.events.models import PanchayatEvent, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_ARCHIVED
    from apps.governance.models import EVENT_ARCHIVAL

    now = timezone.now()
    cutoff = now - timedelta(days=older_than_days) if older_than_days else now

    events_to_archive = (
        PanchayatEvent.objects
        .filter(
            status__in=[STATUS_COMPLETED, STATUS_CANCELLED],
            end_datetime__lt=cutoff,
        )
    )

    count = 0
    for event in events_to_archive:
        event.status = STATUS_ARCHIVED
        event.save(update_fields=['status', 'updated_at'])
        count += 1

    return count


# ------------------------------------------------------------------------------
# Government Welfare Scheme Domain Governance Services (ADRs 0002 & 0003)
# ------------------------------------------------------------------------------

def submit_scheme_revision(revision_id, author):
    """
    Submits a draft SchemeRevision for administrative review.
    - Locks revision row using select_for_update.
    - Verifies revision is in 'draft' status.
    - Calculates and stores SHA-256 content hash.
    - Transitions revision to 'submitted'.
    """
    from apps.schemes.models import SchemeRevision, EDITORIAL_DRAFT, STATUS_DRAFT, STATUS_SUBMITTED

    with transaction.atomic():
        revision = SchemeRevision.objects.select_for_update().get(id=revision_id)
        if revision.editorial_status != EDITORIAL_DRAFT:
            raise ValidationError(
                f"Only revisions in 'draft' status can be submitted for review. Current status: '{revision.editorial_status}'."
            )
        revision.submit_for_review()

        # Update parent translation status if currently in draft
        translation = revision.translation
        if translation.status == STATUS_DRAFT:
            translation.status = STATUS_SUBMITTED
            translation.save(update_fields=['status', 'updated_at'])

        return revision


def approve_scheme_revision(revision_id, approver, notes="", allow_self_approval=False):
    """
    Formally approves a SchemeRevision.
    - Locks the revision and translation rows using select_for_update.
    - Verifies revision is in 'submitted' status.
    - Verifies cryptographic hash integrity.
    - Enforces separation of duties (authors cannot approve their own revisions unless explicitly allowed).
    - Transitions revision to 'approved'.
    - Generates and returns an immutable ApprovalRecord binding to the exact content hash.
    """
    from apps.schemes.models import SchemeRevision, EDITORIAL_SUBMITTED, EDITORIAL_APPROVED, STATUS_APPROVED
    from apps.identity.permissions import is_super_admin
    is_admin = is_super_admin(approver)

    with transaction.atomic():
        revision = SchemeRevision.objects.select_for_update().get(id=revision_id)
        translation = revision.translation

        if revision.editorial_status != EDITORIAL_SUBMITTED:
            if is_admin and revision.editorial_status == 'draft':
                pass
            else:
                raise ValidationError(
                    f"Only revisions in 'submitted' status can be approved. Current status: '{revision.editorial_status}'."
                )

        if not revision.verify_integrity():
            if is_admin and not revision.content_hash:
                revision.content_hash = revision.calculate_hash()
            else:
                raise ValidationError("Cryptographic hash integrity check failed: content does not match hash.")

        is_self = (revision.created_by_id == approver.pk)
        if is_self and not allow_self_approval:
            raise ValidationError(
                "Separation of duties violation: authors cannot approve their own scheme revisions."
            )

        revision.editorial_status = EDITORIAL_APPROVED
        revision.save(update_fields=['editorial_status'])

        approval = ApprovalRecord.objects.create(
            target_content_type='schemetranslation',
            target_id=translation.id,
            revision_id=revision.id,
            revision_hash=revision.content_hash,
            approved_by=approver,
            notes=notes,
            is_self_approval=is_self,
            content_title_snapshot=revision.scheme_name,
        )

        translation.status = STATUS_APPROVED
        translation.save(update_fields=['status', 'updated_at'])

        return revision, approval


def reject_scheme_revision(revision_id, rejected_by, reason):
    """
    Formally rejects a submitted SchemeRevision.
    - Locks the revision row using select_for_update.
    - Requires mandatory rationale >= 10 non-whitespace characters.
    - Transitions revision to 'rejected'.
    - Generates and returns an immutable RejectionRecord.
    """
    from apps.schemes.models import SchemeRevision, EDITORIAL_SUBMITTED, EDITORIAL_REJECTED, STATUS_DRAFT

    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Rejection reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        revision = SchemeRevision.objects.select_for_update().get(id=revision_id)
        if revision.editorial_status != EDITORIAL_SUBMITTED:
            raise ValidationError(
                f"Only revisions in 'submitted' status can be rejected. Current status: '{revision.editorial_status}'."
            )

        revision.editorial_status = EDITORIAL_REJECTED
        revision.save(update_fields=['editorial_status'])

        translation = revision.translation
        if not translation.current_approved_revision_id:
            translation.status = STATUS_DRAFT
            translation.save(update_fields=['status', 'updated_at'])

        rejection = RejectionRecord.objects.create(
            target_content_type='schemetranslation',
            target_id=translation.id,
            revision_id=revision.id,
            rejected_by=rejected_by,
            rejection_reason=cleaned_reason,
            content_title_snapshot=revision.scheme_name,
        )
        return revision, rejection


def publish_scheme_translation(translation_id, revision_id, actor, effective_from=None, effective_until=None, justification=""):
    """
    Publishes or schedules a SchemeTranslation with an approved SchemeRevision.
    - Locks translation and revision rows using select_for_update.
    - Verifies revision belongs to translation and is 'approved'.
    - Sets current_approved_revision pointer and updates status (published or scheduled).
    - Records an append-only PublicationEvent.
    """
    from apps.schemes.models import SchemeTranslation, SchemeRevision, EDITORIAL_APPROVED, STATUS_PUBLISHED, STATUS_SCHEDULED
    from apps.identity.permissions import is_super_admin
    is_admin = is_super_admin(actor)

    now = timezone.now()
    eff_from = effective_from or now

    with transaction.atomic():
        translation = SchemeTranslation.objects.select_for_update().get(id=translation_id)
        revision = SchemeRevision.objects.select_for_update().get(id=revision_id)

        if revision.translation_id != translation.id:
            raise ValidationError("The revision does not belong to the target translation.")

        is_scheduled = eff_from > now
        new_status = STATUS_SCHEDULED if is_scheduled else STATUS_PUBLISHED

        # Idempotency check: prevent duplicate publication events if already published
        if (
            translation.current_approved_revision_id == revision.id
            and translation.status == new_status
            and translation.current_publication_event is not None
        ):
            return translation.current_publication_event

        if revision.editorial_status != EDITORIAL_APPROVED:
            if is_admin:
                approve_scheme_revision(
                    revision_id=revision.id,
                    approver=actor,
                    notes=justification or "Direct publication approval by Super Administrator",
                    allow_self_approval=True,
                )
                revision.refresh_from_db()
            else:
                raise ValidationError("Cannot publish a revision that has not been approved.")

        is_scheduled = eff_from > now

        # Determine event type
        if translation.current_approved_revision_id is None:
            event_type = EVENT_SCHEDULED_PUBLISH if is_scheduled else EVENT_INITIAL_PUBLISH
        elif translation.current_approved_revision_id != revision.id:
            if revision.revision_number < translation.current_approved_revision.revision_number:
                event_type = EVENT_ROLLBACK
                if not justification or len(justification.strip()) < 10:
                    raise ValidationError("Rollback requires a justification of at least 10 characters.")
            else:
                event_type = EVENT_UPDATE_PUBLISH
        else:
            event_type = EVENT_SCHEDULED_PUBLISH if is_scheduled else EVENT_UPDATE_PUBLISH

        new_status = STATUS_SCHEDULED if is_scheduled else STATUS_PUBLISHED

        event = PublicationEvent.objects.create(
            target_content_type='schemetranslation',
            target_id=translation.id,
            revision_id=revision.id,
            event_type=event_type,
            scheduled_for=eff_from if is_scheduled else None,
            effective_from=eff_from,
            effective_until=effective_until,
            actor=actor,
            justification=justification.strip() if justification else "",
            superseded_event=translation.current_publication_event,
            content_title_snapshot=revision.scheme_name,
        )

        translation.current_approved_revision = revision
        translation.current_publication_event = event
        translation.status = new_status
        translation.save(update_fields=['current_approved_revision', 'current_publication_event', 'status', 'updated_at'])

        return event


def withdraw_scheme_translation(translation_id, actor, justification):
    """
    Administratively withdraws a SchemeTranslation, immediately severing public visibility.
    - Locks translation row using select_for_update.
    - Requires mandatory justification >= 10 chars.
    - Sets status to 'withdrawn'.
    - Records an append-only PublicationEvent of type 'withdrawal'.
    """
    from apps.schemes.models import SchemeTranslation, STATUS_WITHDRAWN

    cleaned_justification = justification.strip() if justification else ""
    if len(cleaned_justification) < 10:
        raise ValidationError("Withdrawal requires a justification of at least 10 non-whitespace characters.")

    with transaction.atomic():
        translation = SchemeTranslation.objects.select_for_update().get(id=translation_id)
        rev_id = translation.current_approved_revision_id or translation.id

        title_snap = translation.current_approved_revision.scheme_name if translation.current_approved_revision else translation.localized_slug
        event = PublicationEvent.objects.create(
            target_content_type='schemetranslation',
            target_id=translation.id,
            revision_id=rev_id,
            event_type=EVENT_WITHDRAWAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=cleaned_justification,
            superseded_event=translation.current_publication_event,
            content_title_snapshot=title_snap,
        )

        translation.status = STATUS_WITHDRAWN
        translation.current_publication_event = event
        translation.save(update_fields=['status', 'current_publication_event', 'updated_at'])

        return event


def rollback_scheme_translation(translation_id, target_revision_id, actor, justification):
    """
    Rolls back a SchemeTranslation to an earlier approved SchemeRevision (ADR 0003).
    """
    return publish_scheme_translation(
        translation_id=translation_id,
        revision_id=target_revision_id,
        actor=actor,
        justification=justification,
    )


# ------------------------------------------------------------------------------
# Approved Media Gallery Domain Governance Services (docs/data-model.md 4.9)
# ------------------------------------------------------------------------------

def submit_gallery_album_for_approval(album_id, submitter):
    """
    Submits a draft GalleryAlbum for administrative review and publication approval.
    - Locks GalleryAlbum row using select_for_update.
    - Verifies album is in 'draft' status.
    - Asserts statutory Marathi translation exists.
    - Asserts album contains at least one photograph.
    - Transitions album to 'pending_approval'.
    """
    from apps.gallery.models import GalleryAlbum, STATUS_DRAFT, STATUS_PENDING_APPROVAL, LANGUAGE_MARATHI

    with transaction.atomic():
        album = GalleryAlbum.objects.select_for_update().get(id=album_id)
        if album.status != STATUS_DRAFT:
            raise ValidationError(
                f"Only albums in 'draft' status can be submitted for approval. Current status: '{album.status}'."
            )

        primary_trans = album.get_primary_translation()
        if not primary_trans or not primary_trans.title.strip():
            raise ValidationError(f"A primary title in '{album.primary_language}' is mandatory before an album can be submitted.")

        if not album.items.exists():
            raise ValidationError("An album must contain at least one photograph before submission.")

        album.status = STATUS_PENDING_APPROVAL
        album.save(update_fields=['status', 'updated_at'])
        return album


def approve_and_publish_gallery_album(album_id, approver, notes="", allow_self_approval=False, effective_from=None):
    """
    Formally approves and publishes a GalleryAlbum and all its constituent photographs.
    - Locks GalleryAlbum and member GalleryItem rows using select_for_update.
    - Enforces separation of duties (authors cannot approve their own gallery albums).
    - Verifies cryptographic checksum integrity of every member photograph.
    - Stamps approval on member items (approved_by, approved_at).
    - Computes deterministic SHA-256 album digest.
    - Generates immutable ApprovalRecord and append-only PublicationEvent.
    - Transitions album to 'published' (or 'scheduled' if effective_from is in the future).
    """
    from apps.gallery.models import (
        GalleryAlbum,
        STATUS_DRAFT,
        STATUS_PENDING_APPROVAL,
        STATUS_APPROVED,
        STATUS_PUBLISHED,
        LANGUAGE_MARATHI,
    )

    from apps.identity.permissions import is_super_admin
    is_admin = is_super_admin(approver)

    with transaction.atomic():
        album = GalleryAlbum.objects.select_for_update().get(id=album_id)

        # Idempotency check: prevent duplicate publication events if already published
        if album.status == STATUS_PUBLISHED:
            existing_event = PublicationEvent.objects.filter(
                target_content_type='galleryalbum',
                target_id=album.id,
            ).order_by('-created_at').first()
            if existing_event:
                return album, None, existing_event

        if album.status not in (STATUS_DRAFT, STATUS_PENDING_APPROVAL):
            raise ValidationError(
                f"Only albums in 'draft' or 'pending_approval' status can be approved. Current status: '{album.status}'."
            )

        primary_trans = album.get_primary_translation()
        if not primary_trans or not primary_trans.title.strip():
            raise ValidationError(f"A primary title in '{album.primary_language}' is mandatory before an album can be approved.")

        items = list(album.items.select_for_update().all())
        if not items:
            raise ValidationError("An album must contain at least one photograph before approval.")

        # Separation of duties check
        is_self = (album.created_by_id == approver.pk)
        if is_self and not allow_self_approval:
            raise ValidationError(
                "Separation of duties violation: authors cannot approve their own gallery albums."
            )

        # Integrity verification of all member photographs
        now = timezone.now()
        for item in items:
            if not item.verify_integrity():
                raise ValidationError(
                    f"Integrity verification failed for photograph '{item.original_filename}' (#{item.id}). "
                    "File on disk is missing or has been tampered with."
                )
            item.approved_by = approver
            item.approved_at = now
            item.save(update_fields=['approved_by', 'approved_at'])

        album_hash = album.calculate_hash()
        album_title = album.get_title() or album.slug

        approval = ApprovalRecord.objects.create(
            target_content_type='galleryalbum',
            target_id=album.id,
            revision_id=album.id,
            revision_hash=album_hash,
            approved_by=approver,
            notes=notes,
            is_self_approval=is_self,
            content_title_snapshot=album_title,
        )

        eff_from = effective_from or now
        is_scheduled = eff_from > now

        if is_scheduled:
            event_type = EVENT_SCHEDULED_PUBLISH
        elif not album.is_published:
            event_type = EVENT_INITIAL_PUBLISH
        else:
            event_type = EVENT_UPDATE_PUBLISH

        justification = notes.strip() if notes else f"Gallery album approved and published by {approver.email}"
        pub_event = PublicationEvent.objects.create(
            target_content_type='galleryalbum',
            target_id=album.id,
            revision_id=album.id,
            event_type=event_type,
            scheduled_for=eff_from if is_scheduled else None,
            effective_from=eff_from,
            actor=approver,
            justification=justification,
            content_title_snapshot=album_title,
        )

        album.status = STATUS_PUBLISHED
        album.is_published = True
        album.save(update_fields=['status', 'is_published', 'updated_at'])

        return album, approval, pub_event


def reject_gallery_album(album_id, rejected_by, reason):
    """
    Formally rejects a submitted GalleryAlbum.
    - Locks GalleryAlbum row using select_for_update.
    - Requires mandatory rationale >= 10 non-whitespace characters.
    - Resets album status to 'draft'.
    - Generates and returns an immutable RejectionRecord.
    """
    from apps.gallery.models import GalleryAlbum, STATUS_PENDING_APPROVAL, STATUS_DRAFT

    cleaned_reason = reason.strip() if reason else ""
    if len(cleaned_reason) < 10:
        raise ValidationError("Rejection reason must be at least 10 non-whitespace characters.")

    with transaction.atomic():
        album = GalleryAlbum.objects.select_for_update().get(id=album_id)
        if album.status != STATUS_PENDING_APPROVAL:
            raise ValidationError(
                f"Only albums in 'pending_approval' status can be rejected. Current status: '{album.status}'."
            )

        album.status = STATUS_DRAFT
        album.save(update_fields=['status', 'updated_at'])
        album_title = album.get_title() or album.slug

        rejection = RejectionRecord.objects.create(
            target_content_type='galleryalbum',
            target_id=album.id,
            revision_id=album.id,
            rejected_by=rejected_by,
            rejection_reason=cleaned_reason,
            content_title_snapshot=album_title,
        )
        return album, rejection


def withdraw_gallery_album(album_id, actor, justification):
    """
    Administratively withdraws a GalleryAlbum, immediately severing public visibility.
    - Locks GalleryAlbum row using select_for_update.
    - Requires mandatory justification >= 10 non-whitespace characters.
    - Sets is_published = False, status = 'withdrawn'.
    - Generates an immutable PublicationEvent of type 'withdrawal'.
    """
    from apps.gallery.models import GalleryAlbum, STATUS_WITHDRAWN

    cleaned_justification = justification.strip() if justification else ""
    if len(cleaned_justification) < 10:
        raise ValidationError("Withdrawal requires a justification of at least 10 non-whitespace characters.")

    with transaction.atomic():
        album = GalleryAlbum.objects.select_for_update().get(id=album_id)
        if not album.is_published:
            raise ValidationError("Album is not currently published.")

        album.is_published = False
        album.status = STATUS_WITHDRAWN
        album.save(update_fields=['is_published', 'status', 'updated_at'])
        album_title = album.get_title() or album.slug

        pub_event = PublicationEvent.objects.create(
            target_content_type='galleryalbum',
            target_id=album.id,
            revision_id=album.id,
            event_type=EVENT_WITHDRAWAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=cleaned_justification,
            content_title_snapshot=album_title,
        )
        return album, pub_event


def archive_gallery_album(album_id, actor, justification=""):
    """
    Administratively archives a GalleryAlbum to 'archived' status.
    - Locks GalleryAlbum row using select_for_update.
    - Sets album status to 'archived'.
    - Records an append-only PublicationEvent of type 'archival'.
    """
    from apps.gallery.models import GalleryAlbum, STATUS_ARCHIVED, STATUS_PUBLISHED, STATUS_WITHDRAWN
    from apps.governance.models import EVENT_ARCHIVAL

    with transaction.atomic():
        album = GalleryAlbum.objects.select_for_update().get(id=album_id)
        album.status = STATUS_ARCHIVED
        album.save(update_fields=['status', 'updated_at'])

        just = justification.strip() if justification else f"Statutory archival by {actor.email}"
        album_title = album.get_title() or album.slug
        pub_event = PublicationEvent.objects.create(
            target_content_type='galleryalbum',
            target_id=album.id,
            revision_id=album.id,
            event_type=EVENT_ARCHIVAL,
            effective_from=timezone.now(),
            actor=actor,
            justification=just,
            content_title_snapshot=album_title,
        )
        return album, pub_event


