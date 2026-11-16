"""
Administrative CMS API views for GramSetu platform.

Implements unified, secure endpoints for managing all statutory domains:
- Dashboard metrics and governance queue
- Content Pages and revisions
- Notices, announcements, and urgent publication
- Documents, versions, and secure administrative inspection
- Events, meetings, cancellations, and archival
- Government welfare schemes and revisions
- Photo gallery albums and image management
- Immutable audit trail queries (ApprovalRecord, RejectionRecord, PublicationEvent)

Strict Security Controls:
- All endpoints gated by @require_cms_auth (authenticated, active, MFA verified).
- State-changing actions strictly validate CSRF and verify role authority.
- Revisions strictly enforce row locks and anti-self-approval rules via apps.governance.services.
- Zero leakage of private or draft media to unauthenticated users.
"""

import json
import logging
from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied, ObjectDoesNotExist
from django.db import transaction, IntegrityError
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.identity.permissions import (
    require_cms_auth,
    require_super_admin,
    is_super_admin,
    is_operator,
)
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
from apps.governance import services as gov_services
from apps.core.utils import generate_uuid7
from apps.content.models import (
    Page,
    PageTranslation,
    PageRevision,
    EDITORIAL_DRAFT,
    EDITORIAL_SUBMITTED,
    EDITORIAL_APPROVED,
    EDITORIAL_REJECTED,
    STATUS_DRAFT,
    STATUS_SUBMITTED,
    STATUS_APPROVED,
    STATUS_PUBLISHED,
    STATUS_WITHDRAWN,
    STATUS_ARCHIVED,
)
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    NoticeRevision,
    NoticeUrgentLog,
)
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    DISCLOSURE_DRAFT,
    DISCLOSURE_PENDING_APPROVAL,
    DISCLOSURE_APPROVED,
    DISCLOSURE_REJECTED,
)
from apps.documents.storage import (
    save_private_document,
    resolve_private_file_path,
    verify_file_integrity,
    sanitize_filename,
)
from apps.events.models import (
    PanchayatEvent,
    EventTranslation,
    EVENT_TYPE_CHOICES,
    STATUS_COMPLETED,
    STATUS_CANCELLED,
)
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    SchemeRevision,
)
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
    ALBUM_CATEGORY_CHOICES,
    LANGUAGE_CHOICES,
    LANGUAGE_MARATHI,
)
from apps.gallery.storage import (
    save_gallery_image,
    resolve_private_gallery_path,
    verify_gallery_image_integrity,
    convert_and_validate_image_url,
)

logger = logging.getLogger('gramsetu.cms')


def _parse_json(request):
    """Safely extracts JSON request body or returns (data, error_response)."""
    try:
        if not request.body:
            return {}, None
        data = json.loads(request.body.decode('utf-8'))
        if not isinstance(data, dict):
            return None, JsonResponse({'detail': 'Invalid JSON format: expected an object.'}, status=400)
        return data, None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({'detail': 'Malformed JSON payload.'}, status=400)


# ==============================================================================
# 1. CMS Dashboard & Review Queue
# ==============================================================================

@ensure_csrf_cookie
@require_GET
@require_cms_auth
def cms_dashboard_view(request):
    """
    Returns administrative overview metrics across all 6 statutory domains.
    Provides counts of drafts, pending submissions, approved items, and published content.
    """
    # Count pending review items
    pending_pages = PageRevision.objects.filter(editorial_status=EDITORIAL_SUBMITTED).count()
    pending_notices = NoticeRevision.objects.filter(editorial_status=EDITORIAL_SUBMITTED).count()
    pending_docs = DocumentVersion.objects.filter(disclosure_status=DISCLOSURE_PENDING_APPROVAL).count()
    pending_events = PanchayatEvent.objects.filter(status__in=[STATUS_SUBMITTED, 'pending_approval']).count()
    pending_schemes = SchemeRevision.objects.filter(editorial_status=EDITORIAL_SUBMITTED).count()
    pending_gallery = GalleryAlbum.objects.filter(status__in=[STATUS_SUBMITTED, 'pending_approval']).count()

    total_pending = (
        pending_pages + pending_notices + pending_docs +
        pending_events + pending_schemes + pending_gallery
    )

    # Count approved items awaiting publish
    approved_pages = PageRevision.objects.filter(editorial_status=EDITORIAL_APPROVED, translation__status__in=[STATUS_DRAFT, 'scheduled']).count()
    approved_notices = NoticeRevision.objects.filter(editorial_status=EDITORIAL_APPROVED, translation__status__in=[STATUS_DRAFT, 'scheduled']).count()
    approved_docs = DocumentVersion.objects.filter(disclosure_status=DISCLOSURE_APPROVED, translation__status__in=[STATUS_DRAFT, 'pending_approval']).count()
    approved_events = PanchayatEvent.objects.filter(status='approved').count()
    approved_schemes = SchemeRevision.objects.filter(editorial_status=EDITORIAL_APPROVED, translation__status__in=[STATUS_DRAFT, 'scheduled']).count()
    approved_gallery = GalleryAlbum.objects.filter(status='approved').count()

    total_approved = (
        approved_pages + approved_notices + approved_docs +
        approved_events + approved_schemes + approved_gallery
    )

    # Count drafts
    draft_pages = PageRevision.objects.filter(editorial_status=EDITORIAL_DRAFT).count()
    draft_notices = NoticeRevision.objects.filter(editorial_status=EDITORIAL_DRAFT).count()
    draft_docs = DocumentVersion.objects.filter(disclosure_status=DISCLOSURE_DRAFT).count()
    draft_events = PanchayatEvent.objects.filter(status=STATUS_DRAFT).count()
    draft_schemes = SchemeRevision.objects.filter(editorial_status=EDITORIAL_DRAFT).count()
    draft_gallery = GalleryAlbum.objects.filter(status=STATUS_DRAFT).count()

    total_drafts = (
        draft_pages + draft_notices + draft_docs +
        draft_events + draft_schemes + draft_gallery
    )

    # Count published
    published_pages = PageTranslation.objects.filter(status=STATUS_PUBLISHED).count()
    published_notices = NoticeTranslation.objects.filter(status=STATUS_PUBLISHED).count()
    disclosed_docs = DocumentTranslation.objects.filter(
        status='disclosed',
        current_version__isnull=False,
        current_version__disclosure_status='approved_for_disclosure',
        document__is_confidential=False,
    ).count()
    published_events = PanchayatEvent.objects.filter(status__in=[STATUS_PUBLISHED, STATUS_COMPLETED]).count()
    published_schemes = SchemeTranslation.objects.filter(status=STATUS_PUBLISHED).count()
    published_gallery = GalleryAlbum.objects.filter(status=STATUS_PUBLISHED).count()

    total_published = (
        published_pages + published_notices + disclosed_docs +
        published_events + published_schemes + published_gallery
    )

    # Recent publications & approvals
    recent_events = []
    for pe in PublicationEvent.objects.select_related('actor').order_by('-created_at')[:8]:
        recent_events.append({
            'id': str(pe.id),
            'target_type': pe.target_content_type,
            'event_type': pe.get_event_type_display(),
            'event_type_code': pe.event_type,
            'actor_name': pe.actor.full_name or pe.actor.email,
            'created_at': pe.created_at.isoformat(),
            'justification': pe.justification,
        })

    return JsonResponse({
        'overview': {
            'pending_review_count': total_pending,
            'approved_count': total_approved,
            'drafts_count': total_drafts,
            'published_count': total_published,
        },
        'domains': {
            'pages': {'pending': pending_pages, 'approved': approved_pages, 'drafts': draft_pages, 'published': published_pages},
            'notices': {'pending': pending_notices, 'approved': approved_notices, 'drafts': draft_notices, 'published': published_notices},
            'documents': {'pending': pending_docs, 'approved': approved_docs, 'drafts': draft_docs, 'published': disclosed_docs},
            'events': {'pending': pending_events, 'approved': approved_events, 'drafts': draft_events, 'published': published_events},
            'schemes': {'pending': pending_schemes, 'approved': approved_schemes, 'drafts': draft_schemes, 'published': published_schemes},
            'gallery': {'pending': pending_gallery, 'approved': approved_gallery, 'drafts': draft_gallery, 'published': published_gallery},
        },
        'recent_events': recent_events,
    })


@ensure_csrf_cookie
@require_GET
@require_cms_auth
def cms_pending_submissions_view(request):
    """
    Returns unified list of items in the review / governance queue across all domains.
    Approvers use this queue to verify, approve, reject, or publish revisions.
    Supports query parameter ?status=pending (default) | approved | published | all
    """
    status_filter = request.GET.get('status', 'pending').strip().lower()
    items = []

    # 1. Pages
    pages_qs = PageRevision.objects.select_related('translation', 'translation__page', 'created_by').order_by('-created_at')
    if status_filter == 'pending':
        pages_qs = pages_qs.filter(editorial_status=EDITORIAL_SUBMITTED)
    elif status_filter == 'approved':
        pages_qs = pages_qs.filter(editorial_status=EDITORIAL_APPROVED, translation__status__in=[STATUS_DRAFT, 'scheduled'])
    elif status_filter == 'published':
        pages_qs = pages_qs.filter(editorial_status=EDITORIAL_APPROVED, translation__status=STATUS_PUBLISHED)
    elif status_filter == 'all':
        pages_qs = pages_qs.filter(editorial_status__in=[EDITORIAL_SUBMITTED, EDITORIAL_APPROVED])

    for rev in pages_qs[:100]:
        items.append({
            'id': str(rev.id),
            'entity_type': 'page',
            'entity_id': str(rev.translation.page_id),
            'translation_id': str(rev.translation_id),
            'revision_id': str(rev.id),
            'target_id': str(rev.translation_id),
            'title': rev.title,
            'slug': rev.translation.page.slug,
            'language_code': rev.translation.language_code,
            'version_number': rev.revision_number,
            'author_id': str(rev.created_by_id) if rev.created_by_id else '',
            'author_name': rev.created_by.full_name or rev.created_by.email if rev.created_by else 'System',
            'submitted_at': rev.created_at.isoformat(),
            'content_hash': rev.content_hash,
            'summary': rev.summary,
            'body_markdown': rev.body_markdown,
            'status': rev.editorial_status,
            'translation_status': rev.translation.status,
            'can_approve': rev.editorial_status == EDITORIAL_SUBMITTED,
            'can_publish': rev.editorial_status == EDITORIAL_APPROVED and rev.translation.status != STATUS_PUBLISHED,
        })

    # 2. Notices
    notices_qs = NoticeRevision.objects.select_related('translation', 'translation__notice', 'created_by').order_by('-created_at')
    if status_filter == 'pending':
        notices_qs = notices_qs.filter(editorial_status=EDITORIAL_SUBMITTED)
    elif status_filter == 'approved':
        notices_qs = notices_qs.filter(editorial_status=EDITORIAL_APPROVED, translation__status__in=[STATUS_DRAFT, 'scheduled'])
    elif status_filter == 'published':
        notices_qs = notices_qs.filter(editorial_status=EDITORIAL_APPROVED, translation__status=STATUS_PUBLISHED)
    elif status_filter == 'all':
        notices_qs = notices_qs.filter(editorial_status__in=[EDITORIAL_SUBMITTED, EDITORIAL_APPROVED])

    for rev in notices_qs[:100]:
        notice_obj = rev.translation.notice
        items.append({
            'id': str(rev.id),
            'entity_type': 'notice',
            'entity_id': str(notice_obj.id),
            'translation_id': str(rev.translation_id),
            'revision_id': str(rev.id),
            'target_id': str(rev.translation_id),
            'title': rev.title,
            'notice_type': notice_obj.notice_type,
            'notice_type_display': notice_obj.get_notice_type_display(),
            'reference_number': notice_obj.reference_number or '',
            'effective_from': notice_obj.effective_from.isoformat() if notice_obj.effective_from else None,
            'effective_to': notice_obj.expires_at.isoformat() if notice_obj.expires_at else None,
            'expires_at': notice_obj.expires_at.isoformat() if notice_obj.expires_at else None,
            'is_urgent': getattr(notice_obj, 'is_urgent_published', False) or getattr(notice_obj, 'urgency', '') == 'urgent',
            'language_code': rev.translation.language_code,
            'version_number': rev.revision_number,
            'author_id': str(rev.created_by_id) if rev.created_by_id else '',
            'author_name': rev.created_by.full_name or rev.created_by.email if rev.created_by else 'System',
            'submitted_at': rev.created_at.isoformat(),
            'content_hash': rev.content_hash,
            'summary': rev.summary or (rev.body_markdown[:200] if rev.body_markdown else ''),
            'body_markdown': rev.body_markdown,
            'status': rev.editorial_status,
            'translation_status': rev.translation.status,
            'can_approve': rev.editorial_status == EDITORIAL_SUBMITTED,
            'can_publish': rev.editorial_status == EDITORIAL_APPROVED and rev.translation.status != STATUS_PUBLISHED,
        })

    # 3. Documents
    docs_qs = DocumentVersion.objects.select_related('translation', 'translation__document', 'uploaded_by').order_by('-uploaded_at')
    if status_filter == 'pending':
        docs_qs = docs_qs.filter(disclosure_status=DISCLOSURE_PENDING_APPROVAL)
    elif status_filter == 'approved':
        docs_qs = docs_qs.filter(disclosure_status=DISCLOSURE_APPROVED, translation__status__in=['draft', 'pending_approval'])
    elif status_filter == 'published':
        docs_qs = docs_qs.filter(disclosure_status=DISCLOSURE_APPROVED, translation__status='disclosed')
    elif status_filter == 'all':
        docs_qs = docs_qs.filter(disclosure_status__in=[DISCLOSURE_PENDING_APPROVAL, DISCLOSURE_APPROVED])

    for ver in docs_qs[:100]:
        doc_obj = ver.translation.document
        items.append({
            'id': str(ver.id),
            'entity_type': 'document',
            'entity_id': str(doc_obj.id),
            'translation_id': str(ver.translation_id),
            'version_id': str(ver.id),
            'revision_id': str(ver.id),
            'target_id': str(ver.id),
            'title': ver.translation.title,
            'reference_number': doc_obj.reference_number or '',
            'category': doc_obj.category,
            'category_display': doc_obj.get_category_display(),
            'issuing_department': doc_obj.issuing_department or '',
            'original_filename': ver.original_filename,
            'file_size_bytes': ver.file_size_bytes,
            'checksum_sha256': ver.checksum_sha256,
            'mime_type': ver.mime_type,
            'download_url': f"/api/cms/documents/versions/{ver.id}/download/",
            'description': ver.translation.description or '',
            'language_code': ver.translation.language_code,
            'version_number': ver.version_number,
            'author_id': str(ver.uploaded_by_id) if ver.uploaded_by_id else '',
            'author_name': ver.uploaded_by.full_name or ver.uploaded_by.email if ver.uploaded_by else 'System',
            'submitted_at': ver.uploaded_at.isoformat(),
            'content_hash': ver.checksum_sha256,
            'summary': f"File: {ver.original_filename} ({ver.file_size_bytes} bytes)",
            'status': ver.disclosure_status,
            'translation_status': ver.translation.status,
            'can_approve': ver.disclosure_status == DISCLOSURE_PENDING_APPROVAL,
            'can_publish': ver.disclosure_status == DISCLOSURE_APPROVED and ver.translation.status != 'disclosed',
        })

    # 4. Events
    events_qs = PanchayatEvent.objects.select_related('created_by').prefetch_related('translations').order_by('-created_at')
    if status_filter == 'pending':
        events_qs = events_qs.filter(status__in=[STATUS_SUBMITTED, 'pending_approval'])
    elif status_filter == 'approved':
        events_qs = events_qs.filter(status='approved')
    elif status_filter == 'published':
        events_qs = events_qs.filter(status__in=[STATUS_PUBLISHED, STATUS_COMPLETED])
    elif status_filter == 'all':
        events_qs = events_qs.filter(status__in=[STATUS_SUBMITTED, 'pending_approval', 'approved', STATUS_PUBLISHED])

    for ev in events_qs[:100]:
        trans_mr = ev.translations.filter(language_code='mr').first()
        title = trans_mr.title if trans_mr else f"Event ({ev.get_event_type_display()})"
        all_trans = [{
            'lang': t.language_code,
            'title': t.title,
            'description': t.description,
            'agenda': t.agenda,
        } for t in ev.translations.all()]
        items.append({
            'id': str(ev.id),
            'entity_type': 'event',
            'entity_id': str(ev.id),
            'target_id': str(ev.id),
            'revision_id': str(ev.id),
            'title': title,
            'language_code': 'mr',
            'event_type': ev.event_type,
            'event_type_display': ev.get_event_type_display(),
            'venue': ev.venue_mr,
            'venue_mr': ev.venue_mr,
            'venue_hi': ev.venue_hi,
            'venue_en': ev.venue_en,
            'start_datetime': ev.start_datetime.isoformat(),
            'end_datetime': ev.end_datetime.isoformat(),
            'meeting_chair': getattr(ev, 'meeting_chair', '') or '',
            'is_statutory': getattr(ev, 'is_statutory', False),
            'description': trans_mr.description if trans_mr else '',
            'agenda': trans_mr.agenda if trans_mr else '',
            'all_translations': all_trans,
            'author_id': str(ev.created_by_id) if ev.created_by_id else '',
            'author_name': ev.created_by.full_name or ev.created_by.email if ev.created_by else 'System',
            'submitted_at': ev.created_at.isoformat(),
            'summary': f"Venue: {ev.venue_mr} • Type: {ev.get_event_type_display()}",
            'status': ev.status,
            'can_approve': ev.status in (STATUS_SUBMITTED, 'pending_approval'),
            'can_publish': ev.status == 'approved',
        })

    # 5. Schemes
    schemes_qs = SchemeRevision.objects.select_related('translation', 'translation__scheme', 'created_by').order_by('-created_at')
    if status_filter == 'pending':
        schemes_qs = schemes_qs.filter(editorial_status=EDITORIAL_SUBMITTED)
    elif status_filter == 'approved':
        schemes_qs = schemes_qs.filter(editorial_status=EDITORIAL_APPROVED, translation__status__in=[STATUS_DRAFT, 'scheduled'])
    elif status_filter == 'published':
        schemes_qs = schemes_qs.filter(editorial_status=EDITORIAL_APPROVED, translation__status=STATUS_PUBLISHED)
    elif status_filter == 'all':
        schemes_qs = schemes_qs.filter(editorial_status__in=[EDITORIAL_SUBMITTED, EDITORIAL_APPROVED])

    for rev in schemes_qs[:100]:
        scheme_obj = rev.translation.scheme
        items.append({
            'id': str(rev.id),
            'entity_type': 'scheme',
            'entity_id': str(scheme_obj.id),
            'translation_id': str(rev.translation_id),
            'revision_id': str(rev.id),
            'target_id': str(rev.translation_id),
            'title': rev.scheme_name,
            'slug': scheme_obj.slug,
            'scheme_level': scheme_obj.scheme_level,
            'scheme_level_display': scheme_obj.get_scheme_level_display(),
            'target_beneficiary': scheme_obj.target_beneficiary,
            'target_beneficiary_display': scheme_obj.get_target_beneficiary_display(),
            'official_portal_url': scheme_obj.official_portal_url or '',
            'short_summary': rev.short_summary or '',
            'benefits': rev.benefits or '',
            'eligibility_criteria': rev.eligibility_criteria or '',
            'required_documents': rev.required_documents or '',
            'application_process': rev.application_process or '',
            'language_code': rev.translation.language_code,
            'version_number': rev.revision_number,
            'author_id': str(rev.created_by_id) if rev.created_by_id else '',
            'author_name': rev.created_by.full_name or rev.created_by.email if rev.created_by else 'System',
            'submitted_at': rev.created_at.isoformat(),
            'content_hash': rev.content_hash,
            'summary': rev.short_summary[:200] if rev.short_summary else '',
            'status': rev.editorial_status,
            'translation_status': rev.translation.status,
            'can_approve': rev.editorial_status == EDITORIAL_SUBMITTED,
            'can_publish': rev.editorial_status == EDITORIAL_APPROVED and rev.translation.status != STATUS_PUBLISHED,
        })

    # 6. Gallery
    gallery_qs = GalleryAlbum.objects.select_related('created_by').prefetch_related('translations', 'items').order_by('-created_at')
    if status_filter == 'pending':
        gallery_qs = gallery_qs.filter(status__in=[STATUS_SUBMITTED, 'pending_approval'])
    elif status_filter == 'approved':
        gallery_qs = gallery_qs.filter(status='approved')
    elif status_filter == 'published':
        gallery_qs = gallery_qs.filter(status=STATUS_PUBLISHED)
    elif status_filter == 'all':
        gallery_qs = gallery_qs.filter(status__in=[STATUS_SUBMITTED, 'pending_approval', 'approved', STATUS_PUBLISHED])

    for alb in gallery_qs[:100]:
        trans = alb.get_primary_translation() or alb.translations.first()
        title = trans.title if trans else alb.slug
        desc = trans.description if trans else ''
        sample_items = [{
            'id': str(item.id),
            'caption': item.caption,
            'alt_text': item.alt_text,
            'image_url': item.external_url if (item.source_type == 'link' and item.external_url) else f"/api/gallery/image/{item.id}/",
        } for item in alb.items.all()[:6]]
        items.append({
            'id': str(alb.id),
            'entity_type': 'gallery',
            'entity_id': str(alb.id),
            'target_id': str(alb.id),
            'revision_id': str(alb.id),
            'title': title,
            'slug': alb.slug,
            'language_code': alb.primary_language,
            'category': alb.category,
            'category_display': alb.get_category_display(),
            'description': desc,
            'items_count': alb.items.count(),
            'sample_items': sample_items,
            'author_id': str(alb.created_by_id) if alb.created_by_id else '',
            'author_name': alb.created_by.full_name or alb.created_by.email if alb.created_by else 'System',
            'submitted_at': alb.created_at.isoformat(),
            'summary': f"Category: {alb.get_category_display()} • Items: {alb.items.count()}",
            'status': alb.status,
            'can_approve': alb.status in (STATUS_SUBMITTED, 'pending_approval'),
            'can_publish': alb.status == 'approved',
        })

    return JsonResponse({
        'count': len(items),
        'filter': status_filter,
        'results': items,
    })


# ==============================================================================
# 2. Unified Governance Workflow Action Engine
# ==============================================================================

@ensure_csrf_cookie
@require_POST
@require_cms_auth
def cms_governance_action_view(request):
    """
    Executes governance state transitions across any statutory domain.
    Enforces row-locking, cryptographic verification, anti-self-approval, and Super Admin requirements.
    
    Payload schema:
    {
      "entity_type": "page" | "notice" | "document" | "event" | "scheme" | "gallery",
      "action": "submit" | "approve" | "reject" | "publish" | "withdraw" | "cancel" | "archive" | "rollback" | "urgent_publish",
      "target_id": "<uuid>",          // Translation / version / event / album ID
      "revision_id": "<uuid>",        // Revision ID (required for revision-based actions)
      "notes": "string",              // Approval notes
      "reason": "string",             // Rejection / cancellation rationale (min 10 chars)
      "justification": "string",      // Withdrawal / rollback / urgent rationale (min 10 chars)
      "effective_from": "iso_dt",     // Optional publishing schedule start
      "effective_until": "iso_dt",    // Optional publishing schedule expiry
      "urgent_authorization_id": ""   // Required for urgent notices
    }
    """
    data, err = _parse_json(request)
    if err:
        return err

    entity_type = (data.get('entity_type') or '').strip().lower()
    action = (data.get('action') or '').strip().lower()
    target_id = (data.get('target_id') or '').strip()
    revision_id = (data.get('revision_id') or '').strip() or target_id
    notes = data.get('notes') or ''
    reason = (data.get('reason') or '').strip()
    justification = (data.get('justification') or '').strip()
    effective_from = data.get('effective_from') or None
    effective_until = data.get('effective_until') or None
    urgent_auth_id = (data.get('urgent_authorization_id') or '').strip()

    if not entity_type or not action or not target_id:
        return JsonResponse({'detail': 'entity_type, action, and target_id are required fields.'}, status=400)

    # Role enforcement: approvals, rejections, publications, rollbacks, and withdrawals require Super Admin
    privileged_actions = {'approve', 'reject', 'publish', 'withdraw', 'rollback', 'archive'}
    if action in privileged_actions and not is_super_admin(request.user):
        return JsonResponse({'detail': 'Access denied: Super Administrator authority required for this governance action.'}, status=403)

    user = request.user

    try:
        # ----------------------------------------------------------------------
        # PAGE DOMAIN
        # ----------------------------------------------------------------------
        if entity_type == 'page':
            if action == 'submit':
                rev = gov_services.submit_page_revision(revision_id, author=user)
                return JsonResponse({'success': True, 'editorial_status': rev.editorial_status, 'message': 'Revision submitted for review.'})
            elif action == 'approve':
                rec = gov_services.approve_page_revision(revision_id, approver=user, notes=notes, allow_self_approval=is_super_admin(user))
                return JsonResponse({'success': True, 'approval_id': str(rec.id), 'message': 'Revision formally approved.'})
            elif action == 'reject':
                rec = gov_services.reject_page_revision(revision_id, rejected_by=user, reason=reason)
                return JsonResponse({'success': True, 'rejection_id': str(rec.id), 'message': 'Revision rejected.'})
            elif action == 'publish':
                pe = gov_services.publish_page_translation(target_id, revision_id, actor=user, effective_from=effective_from, effective_until=effective_until, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Page translation published.'})
            elif action == 'withdraw':
                pe = gov_services.withdraw_page_translation(target_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Page translation withdrawn.'})

        # ----------------------------------------------------------------------
        # NOTICE DOMAIN
        # ----------------------------------------------------------------------
        elif entity_type == 'notice':
            if action == 'submit':
                rev = gov_services.submit_notice_revision(revision_id, author=user)
                return JsonResponse({'success': True, 'editorial_status': rev.editorial_status, 'message': 'Notice revision submitted for review.'})
            elif action == 'approve':
                rec = gov_services.approve_notice_revision(revision_id, approver=user, notes=notes, allow_self_approval=is_super_admin(user))
                return JsonResponse({'success': True, 'approval_id': str(rec.id), 'message': 'Notice revision approved.'})
            elif action == 'reject':
                rec = gov_services.reject_notice_revision(revision_id, rejected_by=user, reason=reason)
                return JsonResponse({'success': True, 'rejection_id': str(rec.id), 'message': 'Notice revision rejected.'})
            elif action == 'publish':
                pe = gov_services.publish_notice_translation(target_id, revision_id, actor=user, effective_from=effective_from, effective_until=effective_until, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Notice published.'})
            elif action == 'withdraw':
                pe = gov_services.withdraw_notice_translation(target_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Notice withdrawn.'})
            elif action == 'urgent_publish':
                notice_id = data.get('notice_id') or target_id
                ul = gov_services.urgent_publish_notice(notice_id, target_id, revision_id, operator=user, urgent_authorization_id=urgent_auth_id, justification=justification)
                return JsonResponse({'success': True, 'urgent_log_id': ul.id, 'message': 'Urgent notice published under audit protocol.'})

        # ----------------------------------------------------------------------
        # DOCUMENT DOMAIN
        # ----------------------------------------------------------------------
        elif entity_type == 'document':
            version_id = data.get('version_id') or data.get('revision_id') or target_id
            if action == 'submit':
                ver = gov_services.submit_document_version_for_disclosure(version_id, uploader=user)
                return JsonResponse({'success': True, 'disclosure_status': ver.disclosure_status, 'message': 'Document version submitted for disclosure.'})
            elif action in ('approve', 'publish'):
                ver, rec, pe = gov_services.approve_document_disclosure(version_id, approver=user, notes=notes, justification=justification, allow_self_approval=is_super_admin(user))
                approval_id = str(rec.id) if rec else (str(pe.id) if pe else '')
                return JsonResponse({'success': True, 'approval_id': approval_id, 'message': 'Document disclosure approved and published.'})
            elif action == 'reject':
                ver, rec = gov_services.reject_document_disclosure(version_id, rejected_by=user, reason=reason)
                return JsonResponse({'success': True, 'rejection_id': str(rec.id), 'message': 'Document disclosure rejected.'})
            elif action == 'withdraw':
                pe = gov_services.withdraw_document_translation(target_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Document translation withdrawn from disclosure.'})

        # ----------------------------------------------------------------------
        # EVENT DOMAIN
        # ----------------------------------------------------------------------
        elif entity_type == 'event':
            event_id = target_id
            if action == 'submit':
                ev = gov_services.submit_event_for_approval(event_id, actor=user)
                return JsonResponse({'success': True, 'status': ev.status, 'message': 'Event submitted for approval.'})
            elif action in ('approve', 'publish'):
                ev, rec, pe = gov_services.approve_and_publish_event(event_id, approver=user, notes=notes, effective_from=effective_from, allow_self_approval=is_super_admin(user))
                return JsonResponse({'success': True, 'status': ev.status, 'approval_id': str(rec.id) if rec else (str(pe.id) if pe else ''), 'message': 'Event approved and published.'})
            elif action == 'reject':
                ev, rec = gov_services.reject_event(event_id, rejected_by=user, reason=reason)
                return JsonResponse({'success': True, 'status': ev.status, 'rejection_id': str(rec.id), 'message': 'Event rejected.'})
            elif action == 'cancel':
                ev, pe = gov_services.cancel_event(event_id, actor=user, reason=reason)
                return JsonResponse({'success': True, 'status': ev.status, 'message': 'Event cancelled.'})
            elif action == 'withdraw':
                ev, pe = gov_services.withdraw_event(event_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'status': ev.status, 'message': 'Event withdrawn.'})
            elif action == 'archive':
                ev, pe = gov_services.archive_event(event_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'status': ev.status, 'message': 'Event archived.'})

        # ----------------------------------------------------------------------
        # SCHEME DOMAIN
        # ----------------------------------------------------------------------
        elif entity_type == 'scheme':
            if action == 'submit':
                rev = gov_services.submit_scheme_revision(revision_id, author=user)
                return JsonResponse({'success': True, 'editorial_status': rev.editorial_status, 'message': 'Scheme revision submitted for review.'})
            elif action == 'approve':
                rev, rec = gov_services.approve_scheme_revision(revision_id, approver=user, notes=notes, allow_self_approval=is_super_admin(user))
                return JsonResponse({'success': True, 'approval_id': str(rec.id), 'message': 'Scheme revision approved.'})
            elif action == 'reject':
                rev, rec = gov_services.reject_scheme_revision(revision_id, rejected_by=user, reason=reason)
                return JsonResponse({'success': True, 'rejection_id': str(rec.id), 'message': 'Scheme revision rejected.'})
            elif action == 'publish':
                pe = gov_services.publish_scheme_translation(target_id, revision_id, actor=user, effective_from=effective_from, effective_until=effective_until, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Scheme translation published.'})
            elif action == 'withdraw':
                pe = gov_services.withdraw_scheme_translation(target_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Scheme translation withdrawn.'})
            elif action == 'rollback':
                pe = gov_services.rollback_scheme_translation(target_id, target_revision_id=revision_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'publication_id': str(pe.id), 'message': 'Scheme translation rolled back to revision.'})

        # ----------------------------------------------------------------------
        # GALLERY DOMAIN
        # ----------------------------------------------------------------------
        elif entity_type == 'gallery':
            album_id = target_id
            if action == 'submit':
                alb = gov_services.submit_gallery_album_for_approval(album_id, submitter=user)
                return JsonResponse({'success': True, 'status': alb.status, 'message': 'Gallery album submitted for review.'})
            elif action in ('approve', 'publish'):
                alb, rec, pe = gov_services.approve_and_publish_gallery_album(album_id, approver=user, notes=notes, effective_from=effective_from, allow_self_approval=is_super_admin(user))
                return JsonResponse({'success': True, 'status': alb.status, 'approval_id': str(rec.id) if rec else (str(pe.id) if pe else ''), 'message': 'Gallery album approved and published.'})
            elif action == 'reject':
                alb, rec = gov_services.reject_gallery_album(album_id, rejected_by=user, reason=reason)
                return JsonResponse({'success': True, 'status': alb.status, 'rejection_id': str(rec.id), 'message': 'Gallery album rejected.'})
            elif action == 'withdraw':
                alb, pe = gov_services.withdraw_gallery_album(album_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'status': alb.status, 'message': 'Gallery album withdrawn.'})
            elif action == 'archive':
                alb = gov_services.archive_gallery_album(album_id, actor=user, justification=justification)
                return JsonResponse({'success': True, 'status': alb.status, 'message': 'Gallery album archived.'})

        else:
            return JsonResponse({'detail': f"Unsupported entity_type '{entity_type}'."}, status=400)

        return JsonResponse({'detail': f"Unsupported action '{action}' for entity '{entity_type}'."}, status=400)

    except (ValidationError, ObjectDoesNotExist) as exc:
        msg = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
        logger.warning("Governance action validation error: %s", msg)
        return JsonResponse({'detail': msg}, status=400)
    except PermissionDenied as exc:
        return JsonResponse({'detail': str(exc)}, status=403)
    except Exception as exc:
        logger.error("Governance action failure [%s:%s]: %s", entity_type, action, exc, exc_info=True)
        return JsonResponse({'detail': f"Operation failed: {str(exc)}"}, status=500)


# ==============================================================================
# 3. Immutable Audit Trail Queries
# ==============================================================================

def resolve_actor_role(user):
    """
    Determines role and human-friendly display label for an audit log actor.
    """
    if not user:
        return {'role': 'system', 'role_display': 'प्रणाली (System)'}
    if is_super_admin(user):
        return {'role': 'super_admin', 'role_display': 'मुख्य प्रशासक (Super Admin)'}
    if is_operator(user):
        return {'role': 'operator', 'role_display': 'ऑपरेटर (Operator)'}
    return {'role': 'admin', 'role_display': 'प्रशासक (Admin)'}


def resolve_audit_content_info(target_type, target_id, revision_id=None, snapshot_title=''):
    """
    Resolves human-readable content domain, title snapshot, category, and CMS link for audit trail entries.
    Backfills titles from target records for legacy audit entries where content_title_snapshot is empty.
    """
    tt = str(target_type or '').lower()
    t_id = str(target_id) if target_id else ''

    category = 'other'
    display_mr = 'इतर'
    display_en = 'Other'
    cms_link = '/cms'

    if any(k in tt for k in ('page', 'content')):
        category = 'page'
        display_mr = 'माहिती पृष्ठ (Page)'
        display_en = 'Page'
        cms_link = '/cms/content'
    elif 'notice' in tt:
        category = 'notice'
        display_mr = 'सूचना (Notice)'
        display_en = 'Notice'
        cms_link = '/cms/notices'
    elif 'document' in tt:
        category = 'document'
        display_mr = 'दस्तऐवज (Document)'
        display_en = 'Document'
        cms_link = '/cms/documents'
    elif any(k in tt for k in ('event', 'panchayat', 'meeting')):
        category = 'event'
        display_mr = 'बैठक / कार्यक्रम (Meeting)'
        display_en = 'Meeting / Event'
        cms_link = '/cms/events'
    elif 'scheme' in tt:
        category = 'scheme'
        display_mr = 'शासकीय योजना (Scheme)'
        display_en = 'Welfare Scheme'
        cms_link = '/cms/schemes'
    elif any(k in tt for k in ('gallery', 'album')):
        category = 'gallery'
        display_mr = 'छायाचित्र अल्बम (Gallery Album)'
        display_en = 'Gallery Album'
        cms_link = '/cms/gallery'

    title = (snapshot_title or '').strip()

    # Backfill title from database if snapshot is missing
    if not title and t_id:
        try:
            if category == 'page':
                from apps.content.models import Page, PageTranslation, PageRevision
                p_trans = PageTranslation.objects.filter(page_id=t_id, language_code='mr').first() or PageTranslation.objects.filter(page_id=t_id).first()
                if p_trans:
                    rev = p_trans.current_approved_revision or p_trans.revisions.order_by('-revision_number').first()
                    title = rev.title if rev else p_trans.page.slug
                elif revision_id:
                    rev = PageRevision.objects.filter(id=revision_id).first()
                    if rev:
                        title = rev.title
                if not title:
                    p = Page.objects.filter(id=t_id).first()
                    if p:
                        title = p.slug
            elif category == 'notice':
                from apps.notices.models import Notice, NoticeTranslation, NoticeRevision
                n_trans = NoticeTranslation.objects.filter(notice_id=t_id, language_code='mr').first() or NoticeTranslation.objects.filter(notice_id=t_id).first()
                if n_trans:
                    rev = n_trans.current_approved_revision or n_trans.revisions.order_by('-revision_number').first()
                    title = rev.title if rev else 'Notice'
                elif revision_id:
                    rev = NoticeRevision.objects.filter(id=revision_id).first()
                    if rev:
                        title = rev.title
            elif category == 'document':
                from apps.documents.models import Document, DocumentTranslation
                d_trans = DocumentTranslation.objects.filter(document_id=t_id, language_code='mr').first() or DocumentTranslation.objects.filter(document_id=t_id).first()
                if d_trans:
                    title = d_trans.title
                else:
                    doc = Document.objects.filter(id=t_id).first()
                    if doc:
                        title = doc.reference_number or doc.get_category_display()
            elif category == 'event':
                from apps.events.models import PanchayatEvent, EventTranslation
                e_trans = EventTranslation.objects.filter(event_id=t_id, language_code='mr').first() or EventTranslation.objects.filter(event_id=t_id).first()
                if e_trans:
                    title = e_trans.title
                else:
                    ev = PanchayatEvent.objects.filter(id=t_id).first()
                    if ev:
                        title = ev.get_event_type_display()
            elif category == 'scheme':
                from apps.schemes.models import WelfareScheme, SchemeTranslation, SchemeRevision
                s_trans = SchemeTranslation.objects.filter(scheme_id=t_id, language_code='mr').first() or SchemeTranslation.objects.filter(scheme_id=t_id).first()
                if s_trans:
                    rev = s_trans.current_approved_revision or s_trans.revisions.order_by('-revision_number').first()
                    title = rev.scheme_name if rev else s_trans.scheme.slug
                elif revision_id:
                    rev = SchemeRevision.objects.filter(id=revision_id).first()
                    if rev:
                        title = rev.scheme_name
                if not title:
                    s = WelfareScheme.objects.filter(id=t_id).first()
                    if s:
                        title = s.slug
            elif category == 'gallery':
                from apps.gallery.models import GalleryAlbum, AlbumTranslation
                g_trans = AlbumTranslation.objects.filter(album_id=t_id, language_code='mr').first() or AlbumTranslation.objects.filter(album_id=t_id).first()
                if g_trans:
                    title = g_trans.title
                else:
                    alb = GalleryAlbum.objects.filter(id=t_id).first()
                    if alb:
                        title = alb.slug
        except Exception as exc:
            logger.debug("Could not backfill audit content title for %s:%s - %s", tt, t_id, exc)

    if not title:
        title = f"{display_en} ({t_id[:8]})" if t_id else display_en

    return {
        'content_type': category,
        'content_type_display': display_mr,
        'content_type_en': display_en,
        'content_title': title,
        'content_link': cms_link,
    }


@ensure_csrf_cookie
@require_GET
@require_cms_auth
def cms_audit_logs_view(request):
    """
    Returns administrative audit ledger records:
    ApprovalRecords, RejectionRecords, PublicationEvents, and NoticeUrgentLogs.
    Enriched with content title snapshots, category, human roles, stable links, and filters.
    """
    log_type = request.GET.get('type', 'all').strip().lower()
    content_type_filter = request.GET.get('content_type', 'all').strip().lower()
    action_filter = request.GET.get('action', 'all').strip().lower()
    actor_filter = request.GET.get('actor', '').strip().lower()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    limit = min(int(request.GET.get('limit', 100)), 200)

    results = []

    if log_type in ('all', 'approvals'):
        apr_qs = ApprovalRecord.objects.select_related('approved_by').order_by('-approved_at')
        for apr in apr_qs[:limit * 2]:
            info = resolve_audit_content_info(
                apr.target_content_type,
                apr.target_id,
                apr.revision_id,
                snapshot_title=getattr(apr, 'content_title_snapshot', '')
            )
            role_info = resolve_actor_role(apr.approved_by)
            results.append({
                'record_type': 'approval',
                'action': 'approval',
                'action_display': 'Approved / मंजूर',
                'id': str(apr.id),
                'target_type': apr.target_content_type,
                'target_id': str(apr.target_id),
                'revision_id': str(apr.revision_id),
                'revision_hash': apr.revision_hash,
                'actor_name': apr.approved_by.full_name or apr.approved_by.email,
                'actor_email': apr.approved_by.email,
                'actor_id': str(apr.approved_by_id),
                'actor_role': role_info['role'],
                'actor_role_display': role_info['role_display'],
                'timestamp': apr.approved_at.isoformat(),
                'notes': apr.notes,
                'reason': apr.notes,
                'is_self_approval': apr.is_self_approval,
                'content_type': info['content_type'],
                'content_type_display': info['content_type_display'],
                'content_title': info['content_title'],
                'content_link': info['content_link'],
            })

    if log_type in ('all', 'rejections'):
        rej_qs = RejectionRecord.objects.select_related('rejected_by').order_by('-rejected_at')
        for rej in rej_qs[:limit * 2]:
            info = resolve_audit_content_info(
                rej.target_content_type,
                rej.target_id,
                rej.revision_id,
                snapshot_title=getattr(rej, 'content_title_snapshot', '')
            )
            role_info = resolve_actor_role(rej.rejected_by)
            results.append({
                'record_type': 'rejection',
                'action': 'rejection',
                'action_display': 'Rejected / नाकारले',
                'id': str(rej.id),
                'target_type': rej.target_content_type,
                'target_id': str(rej.target_id),
                'revision_id': str(rej.revision_id),
                'actor_name': rej.rejected_by.full_name or rej.rejected_by.email,
                'actor_email': rej.rejected_by.email,
                'actor_id': str(rej.rejected_by_id),
                'actor_role': role_info['role'],
                'actor_role_display': role_info['role_display'],
                'timestamp': rej.rejected_at.isoformat(),
                'reason': rej.rejection_reason,
                'notes': rej.rejection_reason,
                'content_type': info['content_type'],
                'content_type_display': info['content_type_display'],
                'content_title': info['content_title'],
                'content_link': info['content_link'],
            })

    if log_type in ('all', 'publications'):
        pe_qs = PublicationEvent.objects.select_related('actor').order_by('-created_at')
        for pe in pe_qs[:limit * 2]:
            info = resolve_audit_content_info(
                pe.target_content_type,
                pe.target_id,
                pe.revision_id,
                snapshot_title=getattr(pe, 'content_title_snapshot', '')
            )
            role_info = resolve_actor_role(pe.actor)
            results.append({
                'record_type': 'publication',
                'action': pe.event_type,
                'action_display': pe.get_event_type_display(),
                'id': str(pe.id),
                'target_type': pe.target_content_type,
                'target_id': str(pe.target_id),
                'revision_id': str(pe.revision_id),
                'event_type': pe.event_type,
                'event_type_display': pe.get_event_type_display(),
                'actor_name': pe.actor.full_name or pe.actor.email,
                'actor_email': pe.actor.email,
                'actor_id': str(pe.actor_id),
                'actor_role': role_info['role'],
                'actor_role_display': role_info['role_display'],
                'timestamp': pe.created_at.isoformat(),
                'effective_from': pe.effective_from.isoformat() if pe.effective_from else None,
                'effective_until': pe.effective_until.isoformat() if pe.effective_until else None,
                'justification': pe.justification,
                'reason': pe.justification,
                'content_type': info['content_type'],
                'content_type_display': info['content_type_display'],
                'content_title': info['content_title'],
                'content_link': info['content_link'],
            })

    if log_type in ('all', 'urgent_notices'):
        ul_qs = NoticeUrgentLog.objects.select_related('notice', 'operator', 'ratified_by').order_by('-published_at')
        for ul in ul_qs[:limit * 2]:
            trans_mr = ul.notice.translations.filter(language_code='mr').first()
            notice_title = trans_mr.title if trans_mr else 'Urgent Notice'
            role_info = resolve_actor_role(ul.operator)
            results.append({
                'record_type': 'urgent_notice_log',
                'action': 'urgent_publish',
                'action_display': 'Urgent Publish / तातडीचे प्रकाशन',
                'id': str(ul.id),
                'target_type': 'apps_notices_notice',
                'target_id': str(ul.notice_id),
                'notice_id': str(ul.notice_id),
                'content_type': 'notice',
                'content_type_display': 'सूचना (Notice)',
                'content_title': notice_title,
                'content_link': '/cms/notices',
                'actor_name': ul.operator.full_name or ul.operator.email,
                'actor_email': ul.operator.email,
                'actor_role': role_info['role'],
                'actor_role_display': role_info['role_display'],
                'timestamp': ul.published_at.isoformat(),
                'authorization_id': ul.urgent_authorization_id,
                'justification': ul.justification,
                'reason': ul.justification,
                'ratification_status': ul.ratification_status,
                'is_ratified': (ul.ratification_status == 'ratified'),
                'ratified_by': (ul.ratified_by.full_name or ul.ratified_by.email) if ul.ratified_by else None,
                'ratified_at': ul.ratified_at.isoformat() if ul.ratified_at else None,
            })

    # Apply Filters
    if content_type_filter and content_type_filter != 'all':
        results = [r for r in results if r.get('content_type') == content_type_filter]

    if action_filter and action_filter != 'all':
        results = [r for r in results if r.get('action') == action_filter or r.get('record_type') == action_filter]

    if actor_filter:
        results = [
            r for r in results
            if actor_filter in (r.get('actor_name') or '').lower()
            or actor_filter in (r.get('actor_email') or '').lower()
            or actor_filter in (r.get('actor_role') or '').lower()
        ]

    if start_date:
        results = [r for r in results if (r.get('timestamp') or '') >= start_date]

    if end_date:
        # Include entire end day if YYYY-MM-DD
        end_cmp = end_date + 'T23:59:59.999999' if len(end_date) == 10 else end_date
        results = [r for r in results if (r.get('timestamp') or '') <= end_cmp]

    # Sort combined results by timestamp desc
    results.sort(key=lambda x: x.get('timestamp') or '', reverse=True)
    results = results[:limit]

    return JsonResponse({
        'count': len(results),
        'results': results,
    })


# ==============================================================================
# 4. Domain Content Management: Pages
# ==============================================================================

@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_pages_collection_view(request):
    """
    GET: Lists all Pages with all translations, revisions, and status badges.
    POST: Creates a new Page with initial Marathi draft revision.
    """
    if request.method == 'GET':
        pages_qs = Page.objects.prefetch_related('translations__revisions__created_by').order_by('display_order', 'slug')
        pages_data = []

        for p in pages_qs:
            trans_list = []
            for t in p.translations.all():
                revs = []
                for r in t.revisions.all().order_by('-revision_number'):
                    revs.append({
                        'id': str(r.id),
                        'revision_number': r.revision_number,
                        'title': r.title,
                        'summary': r.summary,
                        'body_markdown': r.body_markdown or '',
                        'sections_data': r.sections_data or [],
                        'references_data': r.references_data or [],
                        'editorial_status': r.editorial_status,
                        'content_hash': r.content_hash,
                        'author_name': r.created_by.full_name or r.created_by.email if r.created_by else 'System',
                        'created_at': r.created_at.isoformat(),
                    })
                trans_list.append({
                    'id': str(t.id),
                    'language_code': t.language_code,
                    'localized_slug': t.localized_slug,
                    'status': t.status,
                    'current_approved_revision_id': str(t.current_approved_revision_id) if t.current_approved_revision_id else None,
                    'updated_at': t.updated_at.isoformat() if hasattr(t, 'updated_at') and t.updated_at else t.created_at.isoformat(),
                    'revisions': revs,
                })

            pages_data.append({
                'id': str(p.id),
                'slug': p.slug,
                'is_system_page': p.is_system_page,
                'display_order': p.display_order,
                'created_at': p.created_at.isoformat(),
                'updated_at': p.updated_at.isoformat() if hasattr(p, 'updated_at') and p.updated_at else p.created_at.isoformat(),
                'translations': trans_list,
            })

        return JsonResponse({'count': len(pages_data), 'results': pages_data})

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        slug = (data.get('slug') or '').strip().lower()
        title = (data.get('title') or '').strip()
        summary = (data.get('summary') or '').strip()
        body_markdown = (data.get('body_markdown') or '').strip()
        sections_data = data.get('sections_data') or []
        references_data = data.get('references_data') or []
        lang = (data.get('language_code') or 'mr').strip().lower()
        localized_slug = (data.get('localized_slug') or slug).strip()
        publish_now = bool(data.get('publish_now', False))

        if not slug or not title:
            return JsonResponse({'detail': 'slug and title are required.'}, status=400)

        if publish_now and not is_super_admin(request.user):
            return JsonResponse({'detail': 'Only Super Administrators can publish directly upon creation.'}, status=403)

        with transaction.atomic():
            page = Page.objects.create(
                slug=slug,
                display_order=int(data.get('display_order', 0)),
                is_system_page=bool(data.get('is_system_page', False)),
            )
            trans = PageTranslation.objects.create(
                page=page,
                language_code=lang,
                localized_slug=localized_slug,
                status=STATUS_DRAFT,
            )
            rev = PageRevision.objects.create(
                translation=trans,
                revision_number=1,
                title=title,
                summary=summary,
                body_markdown=body_markdown,
                sections_data=sections_data,
                references_data=references_data,
                editorial_status=EDITORIAL_DRAFT,
                created_by=request.user,
            )
            if publish_now:
                gov_services.approve_page_revision(
                    revision_id=rev.id,
                    approver=request.user,
                    notes='Direct publication by Super Administrator upon creation',
                    allow_self_approval=True,
                )
                gov_services.publish_page_translation(
                    translation_id=trans.id,
                    revision_id=rev.id,
                    actor=request.user,
                    justification='Direct publication by Super Administrator upon creation',
                )
                trans.refresh_from_db()
                rev.refresh_from_db()

        return JsonResponse({
            'success': True,
            'page_id': str(page.id),
            'translation_id': str(trans.id),
            'revision_id': str(rev.id),
            'status': trans.status,
            'is_published': trans.status == 'published',
            'editorial_status': rev.editorial_status,
            'message': 'Page created and published successfully.' if publish_now else 'Draft page created successfully.',
        }, status=201)


@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_page_detail_revisions_view(request, page_id):
    """
    GET: Retrieves full page detail, all translations, and complete revision history.
    POST: Adds a new draft revision to a translation OR creates a translation for another language.
    """
    try:
        page = Page.objects.get(id=page_id)
    except (Page.DoesNotExist, ValidationError):
        return JsonResponse({'detail': 'Page not found.'}, status=404)

    if request.method == 'GET':
        trans_list = []
        for t in page.translations.prefetch_related('revisions__created_by').all():
            revs = []
            for r in t.revisions.all().order_by('-revision_number'):
                revs.append({
                    'id': str(r.id),
                    'revision_number': r.revision_number,
                    'title': r.title,
                    'summary': r.summary,
                    'body_markdown': r.body_markdown,
                    'sections_data': r.sections_data or [],
                    'references_data': r.references_data or [],
                    'editorial_status': r.editorial_status,
                    'content_hash': r.content_hash,
                    'author_name': r.created_by.full_name or r.created_by.email if r.created_by else 'System',
                    'created_at': r.created_at.isoformat(),
                })
            trans_list.append({
                'id': str(t.id),
                'language_code': t.language_code,
                'localized_slug': t.localized_slug,
                'status': t.status,
                'current_approved_revision_id': str(t.current_approved_revision_id) if t.current_approved_revision_id else None,
                'revisions': revs,
            })

        return JsonResponse({
            'id': str(page.id),
            'slug': page.slug,
            'is_system_page': page.is_system_page,
            'display_order': page.display_order,
            'translations': trans_list,
        })

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        lang = (data.get('language_code') or 'mr').strip().lower()
        title = (data.get('title') or '').strip()
        summary = (data.get('summary') or '').strip()
        body_markdown = (data.get('body_markdown') or '').strip()
        sections_data = data.get('sections_data') or []
        references_data = data.get('references_data') or []

        if not title:
            return JsonResponse({'detail': 'Title is required for a revision.'}, status=400)

        publish_now = bool(data.get('publish_now', False))
        if publish_now and not is_super_admin(request.user):
            return JsonResponse({'detail': 'Only Super Administrators can publish directly upon editing.'}, status=403)

        with transaction.atomic():
            trans, created = PageTranslation.objects.get_or_create(
                page=page,
                language_code=lang,
                defaults={'localized_slug': data.get('localized_slug', f"{page.slug}-{lang}")},
            )

            rev = trans.create_next_revision(
                author=request.user,
                title=title,
                summary=summary,
                body_markdown=body_markdown,
                sections_data=sections_data,
                references_data=references_data,
            )

            if publish_now and is_super_admin(request.user):
                gov_services.approve_page_revision(
                    revision_id=rev.id,
                    approver=request.user,
                    notes=data.get('justification') or 'Direct publication of page revision by Super Administrator',
                    allow_self_approval=True,
                )
                gov_services.publish_page_translation(
                    translation_id=trans.id,
                    revision_id=rev.id,
                    actor=request.user,
                    justification=data.get('justification') or 'Direct publication of page revision by Super Administrator',
                )
                trans.refresh_from_db()
                rev.refresh_from_db()

        return JsonResponse({
            'success': True,
            'translation_id': str(trans.id),
            'revision_id': str(rev.id),
            'revision_number': rev.revision_number,
            'status': trans.status,
            'is_published': trans.status == 'published',
            'editorial_status': rev.editorial_status,
            'message': 'Page revision published directly.' if publish_now else 'New draft revision branched successfully.',
        }, status=201)


@ensure_csrf_cookie
@require_http_methods(['PUT'])
@require_cms_auth
def cms_page_revision_update_view(request, revision_id):
    """
    Updates the content of an existing draft revision.
    Rejects modification if revision is not in 'draft' status (immutability rule).
    """
    try:
        rev = PageRevision.objects.get(id=revision_id)
    except (PageRevision.DoesNotExist, ValidationError):
        return JsonResponse({'detail': 'Revision not found.'}, status=404)

    if rev.editorial_status != EDITORIAL_DRAFT:
        return JsonResponse({'detail': f"Cannot edit revision in '{rev.editorial_status}' status. Revisions are immutable once submitted."}, status=400)

    data, err = _parse_json(request)
    if err:
        return err

    if 'title' in data:
        rev.title = (data['title'] or '').strip()
    if 'summary' in data:
        rev.summary = (data['summary'] or '').strip()
    if 'body_markdown' in data:
        rev.body_markdown = (data['body_markdown'] or '').strip()
    if 'sections_data' in data:
        rev.sections_data = data['sections_data'] or []
    if 'references_data' in data:
        rev.references_data = data['references_data'] or []

    rev.save()
    return JsonResponse({'success': True, 'revision_id': str(rev.id), 'message': 'Draft revision updated.'})


@ensure_csrf_cookie
@require_http_methods(['GET'])
@require_cms_auth
def cms_page_research_view(request):
    """
    Returns verified statutory reference research facts for Narayangaon Gram Panchayat
    extracted from Census of India, LGD, and Maharashtra Rural Development repositories.
    Supports ?lang=mr|hi|en.
    """
    lang = request.GET.get('lang', 'mr').strip().lower()
    from apps.content.research_service import get_narayangaon_statutory_knowledge
    knowledge = get_narayangaon_statutory_knowledge(lang=lang)
    return JsonResponse({'success': True, 'research': knowledge})


# ==============================================================================
# 5. Domain Content Management: Notices
# ==============================================================================

@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_notices_collection_view(request):
    """
    GET: Lists all Notices with translations and statuses.
    POST: Creates a new Notice with initial draft revision.
    """
    if request.method == 'GET':
        qs = Notice.objects.prefetch_related('translations__revisions__created_by', 'translations__current_approved_revision').order_by('-created_at')
        results = []
        for n in qs:
            trans_list = []
            for t in n.translations.all():
                revs = []
                for r in t.revisions.all().order_by('-revision_number'):
                    revs.append({
                        'id': str(r.id),
                        'revision_number': r.revision_number,
                        'title': r.title,
                        'summary': r.summary or '',
                        'body_markdown': r.body_markdown or '',
                        'editorial_status': r.editorial_status,
                        'content_hash': r.content_hash,
                        'author_name': r.created_by.full_name or r.created_by.email if r.created_by else 'System',
                        'created_at': r.created_at.isoformat(),
                    })
                primary_rev = t.current_approved_revision or (t.revisions.order_by('-revision_number').first())
                trans_title = primary_rev.title if primary_rev else ''
                trans_summary = primary_rev.summary if primary_rev else ''
                trans_body = primary_rev.body_markdown if primary_rev else ''
                trans_list.append({
                    'id': str(t.id),
                    'language_code': t.language_code,
                    'title': trans_title,
                    'summary': trans_summary,
                    'body_markdown': trans_body,
                    'status': t.status,
                    'slug': t.slug,
                    'current_approved_revision_id': str(t.current_approved_revision_id) if t.current_approved_revision_id else None,
                    'revisions': revs,
                })

            results.append({
                'id': str(n.id),
                'notice_type': n.notice_type,
                'notice_type_display': n.get_notice_type_display(),
                'urgency': n.urgency,
                'urgency_display': n.get_urgency_display(),
                'reference_number': n.reference_number,
                'issue_date': n.issue_date.isoformat() if hasattr(n, 'issue_date') and n.issue_date else None,
                'effective_from': n.effective_from.isoformat() if n.effective_from else None,
                'expires_at': n.expires_at.isoformat() if n.expires_at else None,
                'deadline': n.deadline.isoformat() if n.deadline else None,
                'has_deadline': n.deadline is not None,
                'is_deadline_passed': bool(n.deadline and n.deadline <= timezone.now()),
                'created_at': n.created_at.isoformat(),
                'translations': trans_list,
            })
        return JsonResponse({'count': len(results), 'results': results})

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        title = (data.get('title') or '').strip()
        description = (data.get('description') or '').strip()
        notice_type = data.get('notice_type') or 'general'
        urgency = data.get('urgency') or 'routine'
        ref_no = (data.get('reference_number') or '').strip()
        lang = (data.get('language_code') or 'mr').strip().lower()
        publish_now = bool(data.get('publish_now', False))

        if not title:
            return JsonResponse({'detail': 'Notice title is required.'}, status=400)

        if publish_now and not is_super_admin(request.user):
            return JsonResponse({'detail': 'Only Super Administrators can publish directly upon creation.'}, status=403)

        deadline_val = data.get('deadline')
        deadline_dt = None
        if deadline_val and str(deadline_val).strip():
            from django.utils.dateparse import parse_datetime
            deadline_dt = parse_datetime(str(deadline_val).strip())
            if not deadline_dt:
                from datetime import datetime
                try:
                    deadline_dt = datetime.fromisoformat(str(deadline_val).strip())
                except ValueError:
                    return JsonResponse({'detail': 'अवैध अंतिम मुदत स्वरूप (Invalid deadline format. Expected ISO-8601).'}, status=400)
            if timezone.is_naive(deadline_dt):
                deadline_dt = timezone.make_aware(deadline_dt)

        with transaction.atomic():
            notice = Notice.objects.create(
                notice_type=notice_type,
                urgency=urgency,
                reference_number=ref_no,
                effective_from=data.get('effective_from') or timezone.now(),
                expires_at=data.get('expires_at') or None,
                deadline=deadline_dt,
            )
            notice_slug = (data.get('slug') or '').strip()
            if not notice_slug:
                notice_slug = f"notice-{notice.id.hex}-{lang}"
            trans = NoticeTranslation.objects.create(
                notice=notice,
                language_code=lang,
                slug=notice_slug,
                status=STATUS_DRAFT,
            )
            rev = NoticeRevision.objects.create(
                translation=trans,
                revision_number=1,
                title=title,
                summary=data.get('summary') or (description[:250] if description else ''),
                body_markdown=data.get('body_markdown') or description,
                editorial_status=EDITORIAL_DRAFT,
                created_by=request.user,
            )
            if publish_now:
                gov_services.approve_notice_revision(
                    revision_id=rev.id,
                    approver=request.user,
                    notes='Direct publication by Super Administrator upon creation',
                    allow_self_approval=True,
                )
                gov_services.publish_notice_translation(
                    translation_id=trans.id,
                    revision_id=rev.id,
                    actor=request.user,
                    justification='Direct publication by Super Administrator upon creation',
                )
                trans.refresh_from_db()
                rev.refresh_from_db()

        return JsonResponse({
            'success': True,
            'notice_id': str(notice.id),
            'translation_id': str(trans.id),
            'revision_id': str(rev.id),
            'status': trans.status,
            'is_published': trans.status == 'published',
            'editorial_status': rev.editorial_status,
            'message': 'Notice created and published.' if publish_now else 'Draft notice created.',
        }, status=201)


@ensure_csrf_cookie
@require_http_methods(['GET', 'POST', 'PUT'])
@require_cms_auth
def cms_notice_detail_revisions_view(request, notice_id):
    """
    GET: Notice detail with translations and revisions.
    POST: Branches new draft revision or adds translation.
    """
    try:
        notice = Notice.objects.get(id=notice_id)
    except (Notice.DoesNotExist, ValidationError):
        return JsonResponse({'detail': 'Notice not found.'}, status=404)

    if request.method == 'GET':
        trans_list = []
        for t in notice.translations.prefetch_related('revisions__created_by').all():
            revs = []
            for r in t.revisions.all().order_by('-revision_number'):
                revs.append({
                    'id': str(r.id),
                    'revision_number': r.revision_number,
                    'title': r.title,
                    'summary': r.summary,
                    'body_markdown': r.body_markdown,
                    'description': r.body_markdown or r.summary,
                    'editorial_status': r.editorial_status,
                    'content_hash': r.content_hash,
                    'author_name': r.created_by.full_name or r.created_by.email if r.created_by else 'System',
                    'created_at': r.created_at.isoformat(),
                })
            trans_list.append({
                'id': str(t.id),
                'language_code': t.language_code,
                'status': t.status,
                'revisions': revs,
            })
        return JsonResponse({
            'id': str(notice.id),
            'notice_type': notice.notice_type,
            'urgency': notice.urgency,
            'reference_number': notice.reference_number,
            'effective_from': notice.effective_from.isoformat() if notice.effective_from else None,
            'expires_at': notice.expires_at.isoformat() if notice.expires_at else None,
            'deadline': notice.deadline.isoformat() if notice.deadline else None,
            'has_deadline': notice.deadline is not None,
            'is_deadline_passed': bool(notice.deadline and notice.deadline <= timezone.now()),
            'translations': trans_list,
        })

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        lang = (data.get('language_code') or 'mr').strip().lower()
        title = (data.get('title') or '').strip()
        description = (data.get('description') or '').strip()

        if not title:
            return JsonResponse({'detail': 'Title is required.'}, status=400)

        with transaction.atomic():
            notice_slug = (data.get('slug') or '').strip()
            if not notice_slug:
                notice_slug = f"notice-{notice.id.hex}-{lang}"
            trans, created = NoticeTranslation.objects.get_or_create(
                notice=notice,
                language_code=lang,
                defaults={'status': STATUS_DRAFT, 'slug': notice_slug},
            )
            rev = trans.create_next_revision(
                author=request.user,
                title=title,
                summary=data.get('summary') or (description[:250] if description else ''),
                body_markdown=data.get('body_markdown') or description,
            )

        return JsonResponse({
            'success': True,
            'translation_id': str(trans.id),
            'revision_id': str(rev.id),
            'revision_number': rev.revision_number,
            'message': 'New notice revision branched.',
        }, status=201)

    elif request.method == 'PUT':
        data, err = _parse_json(request)
        if err:
            return err

        with transaction.atomic():
            if 'reference_number' in data:
                notice.reference_number = data['reference_number'].strip()
            if 'notice_type' in data:
                notice.notice_type = data['notice_type']
            if 'urgency' in data:
                notice.urgency = data['urgency']
            if 'deadline' in data:
                deadline_val = data['deadline']
                if deadline_val and str(deadline_val).strip():
                    from django.utils.dateparse import parse_datetime
                    deadline_dt = parse_datetime(str(deadline_val).strip())
                    if not deadline_dt:
                        from datetime import datetime
                        try:
                            deadline_dt = datetime.fromisoformat(str(deadline_val).strip())
                        except ValueError:
                            return JsonResponse({'detail': 'अवैध अंतिम मुदत स्वरूप (Invalid deadline format. Expected ISO-8601).'}, status=400)
                    if timezone.is_naive(deadline_dt):
                        deadline_dt = timezone.make_aware(deadline_dt)
                    notice.deadline = deadline_dt
                else:
                    notice.deadline = None
            notice.save()

            lang = (data.get('language_code') or 'mr').strip().lower()
            trans = notice.translations.filter(language_code=lang).first() or notice.translations.first()
            if trans:
                rev = trans.revisions.filter(editorial_status=EDITORIAL_DRAFT).order_by('-revision_number').first()
                if rev:
                    if 'title' in data and data['title'].strip():
                        rev.title = data['title'].strip()
                    if 'description' in data:
                        rev.body_markdown = data['description'].strip()
                        rev.summary = data.get('summary') or data['description'][:250].strip()
                    if 'summary' in data:
                        rev.summary = data['summary'].strip()
                    rev.save()

        return JsonResponse({'success': True, 'message': 'Notice draft updated.'})


# ==============================================================================
# 6. Domain Content Management: Documents
# ==============================================================================

@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_documents_collection_view(request):
    """
    GET: Lists all Documents with disclosure statuses, versions, and retention holds.
    POST: Creates a new Document and uploads initial version file (multipart/form-data).
    """
    if request.method == 'GET':
        docs = Document.objects.prefetch_related(
            'translations__versions__uploaded_by',
            'translations__current_version',
            'translations__current_publication_event__actor',
        ).order_by('-created_at')
        results = []
        for d in docs:
            trans_list = []
            for t in d.translations.all():
                versions = []
                for v in t.versions.all().order_by('-version_number'):
                    versions.append({
                        'id': str(v.id),
                        'version_number': v.version_number,
                        'original_filename': v.original_filename,
                        'file_size_bytes': v.file_size_bytes,
                        'mime_type': v.mime_type if hasattr(v, 'mime_type') else 'application/pdf',
                        'checksum_sha256': v.checksum_sha256,
                        'disclosure_status': v.disclosure_status,
                        'uploader_name': v.uploaded_by.full_name or v.uploaded_by.email if v.uploaded_by else 'System',
                        'created_at': v.created_at.isoformat() if hasattr(v, 'created_at') else (v.uploaded_at.isoformat() if hasattr(v, 'uploaded_at') else None),
                    })
                pub_event = t.current_publication_event
                trans_list.append({
                    'id': str(t.id),
                    'language_code': t.language_code,
                    'title': t.title,
                    'description': t.description,
                    'status': t.status,
                    'slug': t.slug,
                    'current_version_id': str(t.current_version_id) if t.current_version_id else None,
                    'publication_date': pub_event.effective_from.isoformat() if pub_event and pub_event.effective_from else None,
                    'published_by': (pub_event.actor.full_name or pub_event.actor.email) if pub_event and pub_event.actor else None,
                    'versions': versions,
                })
            results.append({
                'id': str(d.id),
                'category': d.category,
                'category_display': d.get_category_display(),
                'reference_number': d.reference_number,
                'issuing_department': d.issuing_department,
                'issue_date': d.issue_date.isoformat() if d.issue_date else None,
                'is_confidential': d.is_confidential,
                'retention_hold': d.retention_hold,
                'created_at': d.created_at.isoformat(),
                'translations': trans_list,
            })
        return JsonResponse({'count': len(results), 'results': results})

    elif request.method == 'POST':
        raw_category = request.POST.get('category', 'resolution').strip()
        category_map = {
            'meeting_minutes': 'resolution',
            'audit_report': 'budget',
            'policy': 'citizen_charter',
            'general': 'statutory_report',
        }
        category = category_map.get(raw_category, raw_category)
        valid_cats = {'resolution', 'tender', 'budget', 'citizen_charter', 'statutory_report'}
        if category not in valid_cats:
            return JsonResponse({'detail': f"Invalid category '{raw_category}'. Valid categories are: {', '.join(sorted(valid_cats))}"}, status=400)

        ref_no = request.POST.get('reference_number', '').strip()
        dept = request.POST.get('issuing_department', 'ग्रामपंचायत कार्यालय').strip()
        title = request.POST.get('title', '').strip()
        lang = request.POST.get('language_code', 'mr').strip().lower()
        is_confidential = request.POST.get('is_confidential', 'false').lower() in ('true', '1')
        retention_hold = request.POST.get('retention_hold', 'false').lower() in ('true', '1')
        publish_now = request.POST.get('publish_now', 'false').lower() in ('true', '1')

        if not title:
            return JsonResponse({'detail': 'Document title is required.'}, status=400)

        if publish_now and not is_super_admin(request.user):
            return JsonResponse({'detail': 'Only Super Administrators can publish directly upon creation.'}, status=403)

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return JsonResponse({'detail': 'Physical document file is required.'}, status=400)

        try:
            filename, file_size, checksum = save_private_document(uploaded_file)
        except ValidationError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)

        try:
            with transaction.atomic():
                doc = Document.objects.create(
                    category=category,
                    reference_number=ref_no,
                    issuing_department=dept,
                    is_confidential=is_confidential,
                    retention_hold=retention_hold,
                )
                trans = DocumentTranslation.objects.create(
                    document=doc,
                    language_code=lang,
                    title=title,
                    status='draft',
                )
                ver = DocumentVersion.objects.create(
                    translation=trans,
                    version_number=1,
                    storage_path=filename,
                    original_filename=sanitize_filename(uploaded_file.name),
                    file_size_bytes=file_size,
                    checksum_sha256=checksum,
                    uploaded_by=request.user,
                    disclosure_status=DISCLOSURE_DRAFT,
                )
                if publish_now:
                    gov_services.approve_document_disclosure(
                        version_id=ver.id,
                        approver=request.user,
                        notes='Direct disclosure by Super Administrator upon creation',
                        allow_self_approval=True,
                    )
                    trans.refresh_from_db()
                    ver.refresh_from_db()
        except ValidationError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)
        except IntegrityError as exc:
            return JsonResponse({'detail': f"Database integrity error: {str(exc)}"}, status=400)

        return JsonResponse({
            'success': True,
            'document_id': str(doc.id),
            'translation_id': str(trans.id),
            'version_id': str(ver.id),
            'checksum_sha256': checksum,
            'status': trans.status,
            'disclosure_status': ver.disclosure_status,
            'is_published': trans.status == 'disclosed',
            'message': 'Document uploaded and disclosed.' if publish_now else 'Document uploaded and draft registered.',
        }, status=201)


@ensure_csrf_cookie
@require_http_methods(['POST'])
@require_cms_auth
def cms_document_version_upload_view(request, document_id):
    """
    Uploads a new replacement version file for an existing DocumentTranslation.
    """
    try:
        doc = Document.objects.get(id=document_id)
    except (Document.DoesNotExist, ValidationError):
        return JsonResponse({'detail': 'Document not found.'}, status=404)

    lang = request.POST.get('language_code', 'mr').strip().lower()
    title = request.POST.get('title', '').strip()
    uploaded_file = request.FILES.get('file')

    if not uploaded_file:
        return JsonResponse({'detail': 'Physical document file is required.'}, status=400)

    try:
        filename, file_size, checksum = save_private_document(uploaded_file)
    except ValidationError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)

    with transaction.atomic():
        trans, created = DocumentTranslation.objects.get_or_create(
            document=doc,
            language_code=lang,
            defaults={'title': title or f"{doc.get_category_display()} [{lang}]"},
        )
        if title:
            trans.title = title
            trans.save(update_fields=['title'])

        latest = trans.versions.order_by('-version_number').first()
        next_ver = (latest.version_number + 1) if latest else 1

        ver = DocumentVersion.objects.create(
            translation=trans,
            version_number=next_ver,
            storage_path=filename,
            original_filename=sanitize_filename(uploaded_file.name),
            file_size_bytes=file_size,
            checksum_sha256=checksum,
            uploaded_by=request.user,
            disclosure_status=DISCLOSURE_DRAFT,
        )

    return JsonResponse({
        'success': True,
        'translation_id': str(trans.id),
        'version_id': str(ver.id),
        'version_number': ver.version_number,
        'checksum_sha256': checksum,
        'message': 'Replacement document version uploaded.',
    }, status=201)


@require_GET
@require_cms_auth
def cms_document_version_download_view(request, version_id):
    """
    Allows authenticated, MFA-verified administrators to inspect private/draft document files.
    Verifies SHA-256 integrity on disk before streaming.
    """
    try:
        ver = DocumentVersion.objects.get(id=version_id)
    except (DocumentVersion.DoesNotExist, ValidationError):
        raise Http404("Document version not found.")

    try:
        file_path = resolve_private_file_path(ver.storage_path)
    except Exception:
        raise Http404("Invalid storage path.")

    if not file_path.exists() or not file_path.is_file():
        logger.critical("STORAGE DRIFT: Physical file missing for DocumentVersion %s", ver.id)
        raise Http404("File missing on server storage.")

    if not verify_file_integrity(file_path, ver.checksum_sha256):
        logger.critical("INTEGRITY COMPROMISE: Checksum mismatch for DocumentVersion %s", ver.id)
        return HttpResponse("File integrity verification failed.", status=500)

    response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
    response['Content-Disposition'] = f'inline; filename="{ver.original_filename}"'
    return response


# ==============================================================================
# 7. Domain Content Management: Events & Meetings
# ==============================================================================

@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_events_collection_view(request):
    """
    GET: Lists all Panchayat meetings and events with status and schedule.
    POST: Creates a new Event with initial translation.
    """
    if request.method == 'GET':
        events = PanchayatEvent.objects.prefetch_related('translations').order_by('-start_datetime')
        results = []
        for ev in events:
            trans_list = []
            for t in ev.translations.all():
                trans_list.append({
                    'id': t.id,
                    'language_code': t.language_code,
                    'title': t.title,
                    'description': t.description,
                    'agenda': t.agenda,
                })
            results.append({
                'id': str(ev.id),
                'event_type': ev.event_type,
                'status': ev.status,
                'start_datetime': ev.start_datetime.isoformat(),
                'end_datetime': ev.end_datetime.isoformat(),
                'venue_mr': ev.venue_mr,
                'is_published': ev.is_published,
                'cancellation_reason': ev.cancellation_reason,
                'cancelled_at': ev.cancelled_at.isoformat() if ev.cancelled_at else None,
                'is_cancellation_alert_active': ev.is_cancellation_alert_active(),
                'created_at': ev.created_at.isoformat() if hasattr(ev, 'created_at') else None,
                'translations': trans_list,
            })
        return JsonResponse({'count': len(results), 'results': results})

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        title = (data.get('title') or '').strip()
        event_type = (data.get('event_type') or 'gram_sabha').strip()
        start_dt_raw = data.get('start_datetime')
        end_dt_raw = data.get('end_datetime')
        venue = (data.get('venue_mr') or 'ग्रामपंचायत कार्यालय सभागृह').strip()
        description = (data.get('description') or '').strip()
        agenda = (data.get('agenda') or '').strip()
        lang = (data.get('language_code') or 'mr').strip().lower()
        publish_now = bool(data.get('publish_now', False))

        if not title:
            return JsonResponse({'detail': 'Meeting title is required.'}, status=400)
        if not start_dt_raw or not end_dt_raw:
            return JsonResponse({'detail': 'Both start_datetime and end_datetime are required.'}, status=400)

        # Parse and validate datetimes with timezone awareness
        parsed_start = parse_datetime(str(start_dt_raw))
        if parsed_start is None:
            return JsonResponse({'detail': 'Invalid start_datetime format. Please provide a valid ISO-8601 datetime.'}, status=400)
        if timezone.is_naive(parsed_start):
            parsed_start = timezone.make_aware(parsed_start, timezone.get_current_timezone())

        parsed_end = parse_datetime(str(end_dt_raw))
        if parsed_end is None:
            return JsonResponse({'detail': 'Invalid end_datetime format. Please provide a valid ISO-8601 datetime.'}, status=400)
        if timezone.is_naive(parsed_end):
            parsed_end = timezone.make_aware(parsed_end, timezone.get_current_timezone())

        if parsed_end < parsed_start:
            return JsonResponse({'detail': 'End datetime must be greater than or equal to start datetime.'}, status=400)

        # Map legacy/alias event types to valid statutory choices
        EVENT_TYPE_ALIAS_MAP = {
            'monthly_meeting': 'ward_meeting',
            'special_meeting': 'gram_sabha',
            'standing_committee': 'ward_meeting',
        }
        event_type = EVENT_TYPE_ALIAS_MAP.get(event_type, event_type)
        valid_event_types = [c[0] for c in EVENT_TYPE_CHOICES]
        if event_type not in valid_event_types:
            return JsonResponse({
                'detail': f"Invalid event_type '{event_type}'. Permitted types are: {', '.join(valid_event_types)}."
            }, status=400)

        if publish_now and not is_super_admin(request.user):
            return JsonResponse({'detail': 'Only Super Administrators can publish directly upon creation.'}, status=403)

        try:
            with transaction.atomic():
                ev = PanchayatEvent.objects.create(
                    event_type=event_type,
                    status=STATUS_DRAFT,
                    start_datetime=parsed_start,
                    end_datetime=parsed_end,
                    venue_mr=venue,
                    created_by=request.user,
                )
                # Primary statutory Marathi translation (mandated by ADR-0001)
                EventTranslation.objects.create(
                    event=ev,
                    language_code='mr',
                    title=title,
                    description=description,
                    agenda=agenda,
                )
                # If created from en/hi interface, also create explicit translation for that language
                if lang in ('en', 'hi'):
                    EventTranslation.objects.create(
                        event=ev,
                        language_code=lang,
                        title=title,
                        description=description,
                        agenda=agenda,
                    )

                if publish_now:
                    gov_services.approve_and_publish_event(
                        event_id=ev.id,
                        approver=request.user,
                        notes='Direct publication by Super Administrator upon creation',
                        allow_self_approval=True,
                    )
                    ev.refresh_from_db()

            return JsonResponse({
                'success': True,
                'event_id': str(ev.id),
                'status': ev.status,
                'is_published': ev.is_published,
                'message': 'Meeting/event created and published.' if publish_now else 'Draft meeting/event created successfully.',
            }, status=201)

        except ValidationError as exc:
            msg = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            logger.warning("Event creation validation error: %s", msg)
            return JsonResponse({'detail': msg}, status=400)
        except IntegrityError as exc:
            logger.warning("Event creation integrity error: %s", exc)
            return JsonResponse({'detail': 'Database constraint violation. Please verify date ranges and meeting details.'}, status=400)
        except Exception as exc:
            logger.error("Event creation failure: %s", exc, exc_info=True)
            return JsonResponse({'detail': f"Failed to create meeting: {str(exc)}"}, status=500)


@ensure_csrf_cookie
@require_http_methods(['GET', 'PUT', 'POST'])
@require_cms_auth
def cms_event_detail_view(request, event_id):
    """
    GET: Retrieves event details and translations.
    PUT: Updates draft event details.
    POST: Adds a translation for another language.
    """
    try:
        ev = PanchayatEvent.objects.get(id=event_id)
    except (PanchayatEvent.DoesNotExist, ValidationError):
        return JsonResponse({'detail': 'Event not found.'}, status=404)

    if request.method == 'GET':
        trans_list = []
        for t in ev.translations.all():
            trans_list.append({
                'id': t.id,
                'language_code': t.language_code,
                'title': t.title,
                'description': t.description,
                'agenda': t.agenda,
            })
        return JsonResponse({
            'id': str(ev.id),
            'event_type': ev.event_type,
            'status': ev.status,
            'start_datetime': ev.start_datetime.isoformat(),
            'end_datetime': ev.end_datetime.isoformat(),
            'venue_mr': ev.venue_mr,
            'is_published': ev.is_published,
            'cancellation_reason': ev.cancellation_reason,
            'translations': trans_list,
        })

    elif request.method == 'PUT':
        if ev.status not in (STATUS_DRAFT, STATUS_REJECTED if 'STATUS_REJECTED' in globals() else 'rejected'):
            return JsonResponse({'detail': f"Cannot modify event in '{ev.status}' status directly."}, status=400)

        data, err = _parse_json(request)
        if err:
            return err

        try:
            if 'venue_mr' in data:
                ev.venue_mr = (data['venue_mr'] or '').strip()

            if 'start_datetime' in data or 'end_datetime' in data:
                start_raw = data.get('start_datetime') or ev.start_datetime.isoformat()
                end_raw = data.get('end_datetime') or ev.end_datetime.isoformat()

                parsed_start = parse_datetime(str(start_raw))
                if parsed_start is None:
                    return JsonResponse({'detail': 'Invalid start_datetime format. Expected valid ISO datetime.'}, status=400)
                if timezone.is_naive(parsed_start):
                    parsed_start = timezone.make_aware(parsed_start, timezone.get_current_timezone())

                parsed_end = parse_datetime(str(end_raw))
                if parsed_end is None:
                    return JsonResponse({'detail': 'Invalid end_datetime format. Expected valid ISO datetime.'}, status=400)
                if timezone.is_naive(parsed_end):
                    parsed_end = timezone.make_aware(parsed_end, timezone.get_current_timezone())

                if parsed_end < parsed_start:
                    return JsonResponse({'detail': 'End datetime must be greater than or equal to start datetime.'}, status=400)

                ev.start_datetime = parsed_start
                ev.end_datetime = parsed_end

            if 'event_type' in data:
                et = (data['event_type'] or '').strip()
                EVENT_TYPE_ALIAS_MAP = {
                    'monthly_meeting': 'ward_meeting',
                    'special_meeting': 'gram_sabha',
                    'standing_committee': 'ward_meeting',
                }
                et = EVENT_TYPE_ALIAS_MAP.get(et, et)
                valid_types = [c[0] for c in EVENT_TYPE_CHOICES]
                if et in valid_types:
                    ev.event_type = et
                else:
                    return JsonResponse({'detail': f"Invalid event_type '{et}'. Permitted types are: {', '.join(valid_types)}."}, status=400)

            ev.save()

            lang = (data.get('language_code') or 'mr').strip().lower()
            trans = ev.translations.filter(language_code=lang).first() or ev.translations.first()
            if trans:
                if 'title' in data and data['title'].strip():
                    trans.title = data['title'].strip()
                if 'description' in data:
                    trans.description = (data['description'] or '').strip()
                if 'agenda' in data:
                    trans.agenda = (data['agenda'] or '').strip()
                trans.save()

            return JsonResponse({'success': True, 'message': 'Event updated.'})

        except ValidationError as exc:
            msg = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            return JsonResponse({'detail': msg}, status=400)
        except IntegrityError as exc:
            return JsonResponse({'detail': 'Database constraint violation. Please verify date ranges and meeting details.'}, status=400)
        except Exception as exc:
            logger.error("Event update failure: %s", exc, exc_info=True)
            return JsonResponse({'detail': f"Failed to update meeting: {str(exc)}"}, status=500)

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        lang = (data.get('language_code') or 'mr').strip().lower()
        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'detail': 'Title is required for translation.'}, status=400)

        trans, created = EventTranslation.objects.get_or_create(
            event=ev,
            language_code=lang,
            defaults={
                'title': title,
                'description': (data.get('description') or '').strip(),
                'agenda': (data.get('agenda') or '').strip(),
            },
        )
        if not created:
            trans.title = title
            trans.description = (data.get('description') or '').strip()
            trans.agenda = (data.get('agenda') or '').strip()
            trans.save()

        return JsonResponse({'success': True, 'message': 'Translation saved.'})


# ==============================================================================
# 8. Domain Content Management: Schemes
# ==============================================================================

@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_schemes_collection_view(request):
    """
    GET: Lists all Welfare Schemes with translations and revisions.
    POST: Creates a new Scheme and initial draft revision.
    """
    if request.method == 'GET':
        schemes = WelfareScheme.objects.prefetch_related('translations__revisions__created_by').order_by('display_order', '-created_at')
        results = []
        for s in schemes:
            trans_list = []
            for t in s.translations.all():
                revs = []
                for r in t.revisions.all().order_by('-revision_number'):
                    revs.append({
                        'id': str(r.id),
                        'revision_number': r.revision_number,
                        'title': r.scheme_name,
                        'scheme_name': r.scheme_name,
                        'short_summary': r.short_summary,
                        'benefits': r.benefits,
                        'eligibility_criteria': r.eligibility_criteria,
                        'required_documents': r.required_documents,
                        'application_process': r.application_process,
                        'editorial_status': r.editorial_status,
                        'content_hash': r.content_hash,
                        'author_name': r.created_by.full_name or r.created_by.email if r.created_by else 'System',
                        'created_at': r.created_at.isoformat(),
                    })
                trans_list.append({
                    'id': str(t.id),
                    'language_code': t.language_code,
                    'status': t.status,
                    'revisions': revs,
                })
            results.append({
                'id': str(s.id),
                'slug': s.slug,
                'scheme_level': s.scheme_level,
                'scheme_level_display': s.get_scheme_level_display(),
                'target_beneficiary': s.target_beneficiary,
                'target_beneficiary_display': s.get_target_beneficiary_display(),
                'official_portal_url': s.official_portal_url,
                'department': s.department or '',
                'contact_details': s.contact_details or '',
                'display_order': s.display_order,
                'created_at': s.created_at.isoformat(),
                'updated_at': s.updated_at.isoformat() if hasattr(s, 'updated_at') and s.updated_at else s.created_at.isoformat(),
                'translations': trans_list,
            })
        return JsonResponse({'count': len(results), 'results': results})

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        slug = (data.get('slug') or '').strip().lower()
        title = (data.get('title') or data.get('scheme_name') or '').strip()
        scheme_level = data.get('scheme_level') or 'state'
        beneficiary = data.get('target_beneficiary') or 'farmers'
        short_desc = (data.get('short_summary') or data.get('short_description') or '').strip()
        benefits = (data.get('benefits') or data.get('benefits_summary') or '').strip()
        eligibility = (data.get('eligibility_criteria') or '').strip()
        req_docs = (data.get('required_documents') or 'आधार कार्ड, ७/१२ उतारा, बँक पासबुक').strip()
        application_process = (data.get('application_process') or '').strip()
        department = (data.get('department') or '').strip()
        contact_details = (data.get('contact_details') or '').strip()
        lang = (data.get('language_code') or 'mr').strip().lower()
        publish_now = bool(data.get('publish_now', False))

        if not slug or not title:
            return JsonResponse({'detail': 'slug and title are required.'}, status=400)

        if WelfareScheme.objects.filter(slug=slug).exists():
            return JsonResponse({'detail': f"A scheme with slug '{slug}' already exists. Please choose a unique slug."}, status=400)

        if publish_now and not is_super_admin(request.user):
            return JsonResponse({'detail': 'Only Super Administrators can publish directly upon creation.'}, status=403)

        try:
            with transaction.atomic():
                scheme = WelfareScheme.objects.create(
                    slug=slug,
                    scheme_level=scheme_level,
                    target_beneficiary=beneficiary,
                    official_portal_url=data.get('official_portal_url', '').strip(),
                    department=department,
                    contact_details=contact_details,
                    created_by=request.user,
                )
                trans = SchemeTranslation.objects.create(
                    scheme=scheme,
                    language_code=lang,
                    localized_slug=f"{slug}-{lang}",
                    status=STATUS_DRAFT,
                )
                rev = SchemeRevision.objects.create(
                    translation=trans,
                    revision_number=1,
                    scheme_name=title,
                    short_summary=short_desc,
                    benefits=benefits,
                    eligibility_criteria=eligibility,
                    required_documents=req_docs,
                    application_process=application_process,
                    editorial_status=EDITORIAL_DRAFT,
                    created_by=request.user,
                )
                if publish_now:
                    gov_services.approve_scheme_revision(
                        revision_id=rev.id,
                        approver=request.user,
                        notes='Direct publication by Super Administrator upon creation',
                        allow_self_approval=True,
                    )
                    gov_services.publish_scheme_translation(
                        translation_id=trans.id,
                        revision_id=rev.id,
                        actor=request.user,
                        justification='Direct publication by Super Administrator upon creation',
                    )
                    trans.refresh_from_db()
                    rev.refresh_from_db()
        except ValidationError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)
        except IntegrityError as exc:
            return JsonResponse({'detail': f"Database integrity error: {str(exc)}"}, status=400)

        return JsonResponse({
            'success': True,
            'scheme_id': str(scheme.id),
            'translation_id': str(trans.id),
            'revision_id': str(rev.id),
            'status': trans.status,
            'is_published': trans.status == 'published',
            'editorial_status': rev.editorial_status,
            'message': 'Scheme created and published successfully.' if publish_now else 'Draft scheme registered successfully.',
        }, status=201)


@ensure_csrf_cookie
@require_http_methods(['GET', 'POST', 'PUT'])
@require_cms_auth
def cms_scheme_detail_revisions_view(request, scheme_id):
    """
    GET: Retrieves scheme details, translations, and revisions.
    POST: Branches new draft revision or adds translation.
    """
    try:
        scheme = WelfareScheme.objects.get(id=scheme_id)
    except (WelfareScheme.DoesNotExist, ValidationError):
        return JsonResponse({'detail': 'Scheme not found.'}, status=404)

    if request.method == 'GET':
        trans_list = []
        for t in scheme.translations.prefetch_related('revisions__created_by').all():
            revs = []
            for r in t.revisions.all().order_by('-revision_number'):
                revs.append({
                    'id': str(r.id),
                    'revision_number': r.revision_number,
                    'title': r.scheme_name,
                    'scheme_name': r.scheme_name,
                    'short_summary': r.short_summary,
                    'benefits': r.benefits,
                    'eligibility_criteria': r.eligibility_criteria,
                    'application_process': r.application_process,
                    'editorial_status': r.editorial_status,
                    'content_hash': r.content_hash,
                    'author_name': r.created_by.full_name or r.created_by.email if r.created_by else 'System',
                    'created_at': r.created_at.isoformat(),
                })
            trans_list.append({
                'id': str(t.id),
                'language_code': t.language_code,
                'status': t.status,
                'revisions': revs,
            })
        return JsonResponse({
            'id': str(scheme.id),
            'slug': scheme.slug,
            'scheme_level': scheme.scheme_level,
            'scheme_level_display': scheme.get_scheme_level_display(),
            'target_beneficiary': scheme.target_beneficiary,
            'target_beneficiary_display': scheme.get_target_beneficiary_display(),
            'official_portal_url': scheme.official_portal_url,
            'department': scheme.department or '',
            'contact_details': scheme.contact_details or '',
            'created_at': scheme.created_at.isoformat(),
            'updated_at': scheme.updated_at.isoformat() if hasattr(scheme, 'updated_at') and scheme.updated_at else scheme.created_at.isoformat(),
            'translations': trans_list,
        })

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        lang = (data.get('language_code') or 'mr').strip().lower()
        title = (data.get('title') or data.get('scheme_name') or '').strip()
        if not title:
            return JsonResponse({'detail': 'Title is required.'}, status=400)

        with transaction.atomic():
            if 'department' in data:
                scheme.department = (data['department'] or '').strip()
                scheme.save(update_fields=['department'])
            if 'contact_details' in data:
                scheme.contact_details = (data['contact_details'] or '').strip()
                scheme.save(update_fields=['contact_details'])

            trans, created = SchemeTranslation.objects.get_or_create(
                scheme=scheme,
                language_code=lang,
                defaults={'status': STATUS_DRAFT, 'localized_slug': f"{scheme.slug}-{lang}"},
            )
            latest = trans.revisions.order_by('-revision_number').first()
            next_num = (latest.revision_number + 1) if latest else 1

            rev = SchemeRevision.objects.create(
                translation=trans,
                revision_number=next_num,
                scheme_name=title,
                short_summary=(data.get('short_summary') or data.get('short_description') or (latest.short_summary if latest else '')),
                benefits=(data.get('benefits') or data.get('benefits_summary') or (latest.benefits if latest else '')),
                eligibility_criteria=(data.get('eligibility_criteria') or (latest.eligibility_criteria if latest else '')),
                required_documents=(data.get('required_documents') or (latest.required_documents if latest else 'आधार कार्ड, ७/१२ उतारा, बँक पासबुक')),
                application_process=(data.get('application_process') or (latest.application_process if latest else '')),
                editorial_status=EDITORIAL_DRAFT,
                created_by=request.user,
            )

        return JsonResponse({
            'success': True,
            'translation_id': str(trans.id),
            'revision_id': str(rev.id),
            'revision_number': rev.revision_number,
            'message': 'New scheme revision branched.',
        }, status=201)

    elif request.method == 'PUT':
        data, err = _parse_json(request)
        if err:
            return err

        with transaction.atomic():
            if 'scheme_level' in data:
                scheme.scheme_level = data['scheme_level']
            if 'target_beneficiary' in data:
                scheme.target_beneficiary = data['target_beneficiary']
            if 'official_portal_url' in data:
                scheme.official_portal_url = data['official_portal_url'].strip()
            if 'department' in data:
                scheme.department = (data['department'] or '').strip()
            if 'contact_details' in data:
                scheme.contact_details = (data['contact_details'] or '').strip()
            scheme.save()

            lang = (data.get('language_code') or 'mr').strip().lower()
            trans = scheme.translations.filter(language_code=lang).first() or scheme.translations.first()
            if trans:
                rev = trans.revisions.filter(editorial_status=EDITORIAL_DRAFT).order_by('-revision_number').first()
                if rev:
                    if 'title' in data and data['title'].strip():
                        rev.scheme_name = data['title'].strip()
                    if 'scheme_name' in data and data['scheme_name'].strip():
                        rev.scheme_name = data['scheme_name'].strip()
                    if 'short_summary' in data:
                        rev.short_summary = data['short_summary'].strip()
                    if 'benefits' in data:
                        rev.benefits = data['benefits'].strip()
                    if 'eligibility_criteria' in data:
                        rev.eligibility_criteria = data['eligibility_criteria'].strip()
                    if 'application_process' in data:
                        rev.application_process = data['application_process'].strip()
                    if 'required_documents' in data:
                        rev.required_documents = data['required_documents'].strip()
                    rev.save()

        return JsonResponse({'success': True, 'message': 'Scheme draft updated.'})


# ==============================================================================
# 9. Domain Content Management: Gallery
# ==============================================================================

@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_gallery_collection_view(request):
    """
    GET: Lists all photo gallery albums with status and item counts.
    POST: Creates a new album and initial translation.
    """
    if request.method == 'GET':
        albums = GalleryAlbum.objects.prefetch_related('translations', 'items').order_by('-created_at')
        results = []
        for alb in albums:
            trans_list = []
            for t in alb.translations.all():
                trans_list.append({
                    'id': str(t.id),
                    'language_code': t.language_code,
                    'title': t.title,
                    'description': t.description,
                })
            results.append({
                'id': str(alb.id),
                'slug': alb.slug,
                'category': alb.category,
                'event_date': alb.event_date.isoformat() if alb.event_date else None,
                'status': alb.status,
                'is_published': alb.is_published,
                'primary_language': alb.primary_language,
                'title': alb.get_title(),
                'description': alb.get_description(),
                'items_count': alb.items.count(),
                'created_at': alb.created_at.isoformat(),
                'translations': trans_list,
            })
        return JsonResponse({'count': len(results), 'results': results})

    elif request.method == 'POST':
        data, err = _parse_json(request)
        if err:
            return err

        slug = (data.get('slug') or '').strip().lower()
        category = (data.get('category') or 'infrastructure').strip().lower()
        event_date_raw = data.get('event_date')
        primary_lang = (data.get('primary_language') or data.get('language_code') or 'mr').strip().lower()
        if primary_lang not in ('mr', 'hi', 'en'):
            primary_lang = 'mr'

        # Single title & description entered once in the selected primary language
        title = (
            data.get('title')
            or (data.get('title_mr') if primary_lang == 'mr' else (data.get('title_hi') if primary_lang == 'hi' else data.get('title_en')))
            or data.get('title_mr')
            or data.get('title_hi')
            or data.get('title_en')
            or ''
        ).strip()
        description = (
            data.get('description')
            or (data.get('description_mr') if primary_lang == 'mr' else (data.get('description_hi') if primary_lang == 'hi' else data.get('description_en')))
            or data.get('description_mr')
            or data.get('description_hi')
            or data.get('description_en')
            or ''
        ).strip()

        if not slug:
            return JsonResponse({'detail': 'अल्बम स्लग आवश्यक आहे (Album slug is required).'}, status=400)

        if not title:
            return JsonResponse({'detail': 'अल्बम शीर्षक आवश्यक आहे (Album title is required).'}, status=400)

        # 1. Slug format validation (ASCII alphanumeric, hyphens, underscores)
        import re
        if not re.match(r'^[a-z0-9_-]+$', slug):
            return JsonResponse({
                'detail': 'स्लग मध्ये फक्त इंग्रजी अक्षरे, आकडे, डॅश आणि अंडरस्कोर वापरता येतील (Slug may only contain lowercase letters, numbers, hyphens, and underscores).'
            }, status=400)

        # 2. Duplicate slug check to avoid unhandled database unique constraint IntegrityError (HTTP 500)
        if GalleryAlbum.objects.filter(slug=slug).exists():
            return JsonResponse({
                'detail': f"या स्लगचे अल्बम आधीच अस्तित्वात आहे (An album with slug '{slug}' already exists)."
            }, status=400)

        # 3. Category alias normalization and validation against ALBUM_CATEGORY_CHOICES
        GALLERY_CATEGORY_ALIASES = {
            'culture': 'cultural',
            'water_supply': 'environment',
            'general': 'infrastructure',
        }
        category = GALLERY_CATEGORY_ALIASES.get(category, category)
        valid_categories = [c[0] for c in ALBUM_CATEGORY_CHOICES]
        if category not in valid_categories:
            return JsonResponse({
                'detail': f"अवैध वर्गवारी '{category}'. वैध वर्गवारी: {', '.join(valid_categories)}."
            }, status=400)

        # 4. Safe event_date parsing
        event_date = None
        if event_date_raw:
            if isinstance(event_date_raw, str) and event_date_raw.strip():
                try:
                    from datetime import datetime
                    event_date = datetime.strptime(event_date_raw.strip()[:10], '%Y-%m-%d').date()
                except ValueError:
                    return JsonResponse({'detail': 'अवैध दिनांक स्वरूप. दिनांक YYYY-MM-DD स्वरूपात असावा (Invalid event_date format).'}, status=400)

        # 5. Language validation
        valid_langs = [c[0] for c in LANGUAGE_CHOICES]
        if primary_lang not in valid_langs:
            primary_lang = LANGUAGE_MARATHI

        publish_now = bool(data.get('publish_now', False))
        if publish_now and not is_super_admin(request.user):
            return JsonResponse({'detail': 'Only Super Administrators can publish directly upon creation.'}, status=403)

        try:
            with transaction.atomic():
                alb = GalleryAlbum.objects.create(
                    slug=slug,
                    category=category,
                    event_date=event_date,
                    primary_language=primary_lang,
                    status=STATUS_DRAFT,
                    created_by=request.user,
                )
                # Primary language translation (mandatory)
                AlbumTranslation.objects.create(
                    album=alb,
                    language_code=primary_lang,
                    title=title,
                    description=description,
                )

                if publish_now:
                    alb, rec, pe = gov_services.approve_and_publish_gallery_album(
                        album_id=alb.id,
                        approver=request.user,
                        notes='Direct publication by Super Administrator upon creation',
                        allow_self_approval=True,
                    )

            return JsonResponse({
                'success': True,
                'album_id': str(alb.id),
                'status': alb.status,
                'is_published': alb.is_published,
                'message': 'Gallery album created and published directly.' if publish_now else 'Gallery album draft created.',
            }, status=201)
        except (ValidationError, IntegrityError, ValueError) as exc:
            msg = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            logger.warning("Gallery album creation failed: %s", msg)
            return JsonResponse({'detail': f"अल्बम निर्मिती अयशस्वी: {msg}"}, status=400)
        except Exception as exc:
            logger.error("Unexpected error in gallery album creation: %s", exc, exc_info=True)
            return JsonResponse({'detail': f"अल्बम निर्मिती अयशस्वी (Creation failed): {str(exc)}"}, status=500)


@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
@require_cms_auth
def cms_gallery_detail_items_view(request, album_id):
    """
    GET: Retrieves album details, translations, and item photographs.
    POST: Uploads an image item, links an external image with SSRF checks, or reorders items.
    """
    try:
        alb = GalleryAlbum.objects.get(id=album_id)
    except (GalleryAlbum.DoesNotExist, ValidationError):
        return JsonResponse({'detail': 'Album not found.'}, status=404)

    if request.method == 'GET':
        items = []
        for it in alb.items.all().order_by('display_order', 'uploaded_at'):
            preview_url = it.external_url if (it.source_type == 'link' and it.external_url) else f"/api/cms/gallery/image/{it.id}/"
            items.append({
                'id': str(it.id),
                'source_type': it.source_type,
                'external_url': it.external_url,
                'original_filename': it.original_filename,
                'file_size_bytes': it.file_size_bytes,
                'mime_type': it.mime_type,
                'checksum_sha256': it.checksum_sha256,
                'caption_mr': it.caption_mr,
                'caption_hi': it.caption_hi,
                'caption_en': it.caption_en,
                'caption': it.caption,
                'alt_text': it.alt_text,
                'caption_mr': it.caption_mr,
                'caption_hi': it.caption_hi,
                'caption_en': it.caption_en,
                'alt_text_mr': it.alt_text_mr,
                'alt_text_hi': it.alt_text_hi,
                'alt_text_en': it.alt_text_en,
                'is_cover_image': it.is_cover_image,
                'display_order': it.display_order,
                'preview_url': preview_url,
            })
        trans_list = []
        for t in alb.translations.all():
            trans_list.append({
                'id': str(t.id),
                'language_code': t.language_code,
                'title': t.title,
                'description': t.description,
            })
        return JsonResponse({
            'id': str(alb.id),
            'slug': alb.slug,
            'category': alb.category,
            'primary_language': alb.primary_language,
            'title': alb.get_title(),
            'description': alb.get_description(),
            'status': alb.status,
            'is_published': alb.is_published,
            'items': items,
            'translations': trans_list,
        })

    elif request.method == 'POST':
        # Check for JSON actions: reorder, set_cover, delete_item, add_link
        content_type = request.content_type or ''
        data = {}
        if 'application/json' in content_type:
            data, _ = _parse_json(request)
            if not data:
                data = {}

        action = (data.get('action') or request.POST.get('action') or '').strip().lower()

        # Action: Reorder items persistently
        if action == 'reorder':
            item_ids = data.get('order') or data.get('item_ids')
            if not isinstance(item_ids, list):
                return JsonResponse({'detail': 'order must be a list of item UUIDs.'}, status=400)
            try:
                with transaction.atomic():
                    for idx, it_id in enumerate(item_ids):
                        alb.items.filter(id=it_id).update(display_order=idx + 1)
                return JsonResponse({'success': True, 'message': 'Gallery items reordered successfully.'})
            except (ValidationError, ValueError, IntegrityError) as exc:
                return JsonResponse({'detail': str(exc)}, status=400)

        # Action: Set Cover Image
        if action == 'set_cover':
            item_id = data.get('item_id') or request.POST.get('item_id')
            if not item_id:
                return JsonResponse({'detail': 'item_id is required.'}, status=400)
            try:
                with transaction.atomic():
                    alb.items.update(is_cover_image=False)
                    alb.items.filter(id=item_id).update(is_cover_image=True)
                return JsonResponse({'success': True, 'message': 'Album cover image updated.'})
            except (ValidationError, ValueError, IntegrityError) as exc:
                return JsonResponse({'detail': str(exc)}, status=400)

        # Action: Delete Item
        if action == 'delete_item':
            item_id = data.get('item_id') or request.POST.get('item_id')
            if not item_id:
                return JsonResponse({'detail': 'item_id is required.'}, status=400)
            try:
                item = alb.items.filter(id=item_id).first()
                if item:
                    if item.source_type == 'upload':
                        from apps.gallery.storage import delete_private_gallery_file
                        delete_private_gallery_file(item.storage_path)
                    item.delete()
                return JsonResponse({'success': True, 'message': 'Item deleted from album.'})
            except (ValidationError, ValueError, IntegrityError) as exc:
                return JsonResponse({'detail': str(exc)}, status=400)

        # Action: Update Album Metadata and Title/Description
        if action in ('update_album', 'update_translations', 'edit_album'):
            try:
                with transaction.atomic():
                    # Primary language update
                    if 'primary_language' in data:
                        new_plang = (data['primary_language'] or '').strip().lower()
                        if new_plang in ('mr', 'hi', 'en'):
                            alb.primary_language = new_plang

                    # Category update
                    if 'category' in data:
                        new_cat = (data['category'] or '').strip().lower()
                        GALLERY_CATEGORY_ALIASES = {'culture': 'cultural', 'water_supply': 'environment', 'general': 'infrastructure'}
                        new_cat = GALLERY_CATEGORY_ALIASES.get(new_cat, new_cat)
                        valid_cats = [c[0] for c in ALBUM_CATEGORY_CHOICES]
                        if new_cat in valid_cats:
                            alb.category = new_cat

                    # Event date update
                    if 'event_date' in data:
                        ev_raw = data['event_date']
                        if ev_raw and str(ev_raw).strip():
                            from datetime import datetime
                            alb.event_date = datetime.strptime(str(ev_raw).strip()[:10], '%Y-%m-%d').date()
                        else:
                            alb.event_date = None

                    alb.save()

                    # Exactly ONE title & description entered in the selected primary language
                    title = (
                        data.get('title')
                        or data.get('title_mr')
                        or data.get('title_hi')
                        or data.get('title_en')
                    )
                    description = (
                        data.get('description')
                        if 'description' in data
                        else (
                            data.get('description_mr')
                            or data.get('description_hi')
                            or data.get('description_en')
                        )
                    )

                    if title is not None:
                        title_str = str(title).strip()
                        if not title_str:
                            return JsonResponse({'detail': 'अल्बम शीर्षक रिकामे असू शकत नाही (Album title cannot be empty).'}, status=400)

                        t_prim, _ = AlbumTranslation.objects.get_or_create(
                            album=alb,
                            language_code=alb.primary_language
                        )
                        t_prim.title = title_str
                        if description is not None:
                            t_prim.description = str(description).strip()
                        t_prim.save()

                return JsonResponse({'success': True, 'message': 'Album details updated successfully.'})
            except (ValidationError, ValueError, IntegrityError) as exc:
                return JsonResponse({'detail': str(exc)}, status=400)

        source_type = (data.get('source_type') or request.POST.get('source_type') or 'upload').strip().lower()

        # Branch A: External Link Source
        if source_type == 'link' or data.get('external_url') or request.POST.get('external_url'):
            raw_url = (data.get('external_url') or request.POST.get('external_url') or data.get('image_url') or request.POST.get('image_url') or '').strip()
            if not raw_url:
                return JsonResponse({'detail': 'External image URL is required.'}, status=400)

            converted_url, err = convert_and_validate_image_url(raw_url)
            if err:
                return JsonResponse({'detail': err}, status=400)

            caption = (
                data.get('caption')
                or data.get('caption_mr')
                or data.get('caption_en')
                or data.get('caption_hi')
                or request.POST.get('caption')
                or request.POST.get('caption_mr')
                or ''
            ).strip()
            alt_text = (
                data.get('alt_text')
                or data.get('alt_text_mr')
                or data.get('alt_text_en')
                or data.get('alt_text_hi')
                or request.POST.get('alt_text')
                or request.POST.get('alt_text_mr')
                or caption
                or 'छायाचित्र'
            ).strip()
            if len(alt_text) < 3:
                alt_text = 'छायाचित्र'

            next_order = alb.items.count() + 1
            import hashlib
            checksum = hashlib.sha256(converted_url.encode('utf-8')).hexdigest()

            try:
                item = GalleryItem.objects.create(
                    album=alb,
                    source_type='link',
                    external_url=converted_url,
                    storage_path=f"link:{generate_uuid7()}",
                    original_filename=caption[:50] or 'external-image.jpg',
                    file_size_bytes=1024,
                    mime_type='image/jpeg',
                    checksum_sha256=checksum,
                    caption_mr=caption,
                    caption_hi=caption,
                    caption_en=caption,
                    alt_text_mr=alt_text,
                    alt_text_hi=alt_text,
                    alt_text_en=alt_text,
                    display_order=next_order,
                    uploaded_by=request.user,
                )

                return JsonResponse({
                    'success': True,
                    'item_id': str(item.id),
                    'source_type': 'link',
                    'preview_url': converted_url,
                    'message': 'Image link successfully added to album.',
                }, status=201)
            except (ValidationError, IntegrityError, ValueError) as exc:
                msg = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                return JsonResponse({'detail': f"छायाचित्र लिंक जोडणे अयशस्वी: {msg}"}, status=400)

        # Branch B: File Upload Source
        uploaded_image = request.FILES.get('image_file') or request.FILES.get('file')
        if not uploaded_image:
            return JsonResponse({'detail': 'Image file or external link is required.'}, status=400)

        caption = (
            request.POST.get('caption')
            or request.POST.get('caption_mr')
            or request.POST.get('caption_en')
            or request.POST.get('caption_hi')
            or ''
        ).strip()
        alt_text = (
            request.POST.get('alt_text')
            or request.POST.get('alt_text_mr')
            or request.POST.get('alt_text_en')
            or request.POST.get('alt_text_hi')
            or caption
            or 'छायाचित्र'
        ).strip()
        if len(alt_text) < 3:
            alt_text = 'छायाचित्र'

        try:
            filename, orig_name, file_size, mime_type, checksum = save_gallery_image(
                uploaded_image, uploaded_image.name
            )
        except ValidationError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)

        next_order = alb.items.count() + 1
        try:
            item = GalleryItem.objects.create(
                album=alb,
                source_type='upload',
                storage_path=filename,
                original_filename=orig_name,
                file_size_bytes=file_size,
                mime_type=mime_type,
                checksum_sha256=checksum,
                caption_mr=caption,
                caption_hi=caption,
                caption_en=caption,
                alt_text_mr=alt_text,
                alt_text_hi=alt_text,
                alt_text_en=alt_text,
                display_order=next_order,
                uploaded_by=request.user,
            )

            return JsonResponse({
                'success': True,
                'item_id': str(item.id),
                'source_type': 'upload',
                'checksum_sha256': checksum,
                'message': 'Photograph uploaded to album.',
            }, status=201)
        except (ValidationError, IntegrityError, ValueError) as exc:
            msg = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            return JsonResponse({'detail': f"छायाचित्र अपलोड अयशस्वी: {msg}"}, status=400)


@require_GET
@require_cms_auth
def cms_gallery_image_serve_view(request, item_id):
    """
    Allows authenticated, MFA-verified administrators to view private/draft gallery images.
    """
    try:
        item = GalleryItem.objects.get(id=item_id)
    except (GalleryItem.DoesNotExist, ValidationError):
        raise Http404("Gallery item not found.")

    if item.source_type == 'link' and item.external_url:
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(item.external_url)

    try:
        resolved = resolve_private_gallery_path(item.storage_path)
    except Exception:
        raise Http404("Invalid storage path.")

    if not resolved.exists() or not resolved.is_file():
        raise Http404("Image file missing on disk.")

    if not verify_gallery_image_integrity(item.storage_path, item.checksum_sha256):
        return HttpResponse("Image integrity check failed.", status=500)

    return FileResponse(open(resolved, 'rb'), content_type=item.mime_type)


@require_http_methods(['GET', 'PUT'])
@require_cms_auth
def cms_panchayat_profile_view(request):
    """
    CMS endpoint to inspect and update statutory Panchayat Profile and office-holder records.
    - GET: Available to Super Admin and Operator to view current profile and office-holder records.
    - PUT: Strictly restricted to Super Admin (Gramsevak). Allows updating Sarpanch name,
      Gramsevak name, contact details, office addresses, and official metadata.
    """
    from apps.site_config.models import PanchayatProfile
    profile = PanchayatProfile.objects.filter(id=1).first()
    if not profile:
        profile = PanchayatProfile.objects.create(
            id=1,
            census_code='549493',
            lgd_code='549493',
            district_name_mr='छत्रपती संभाजीनगर',
            district_name_en='Chhatrapati Sambhajinagar',
            taluka_name_mr='पैठण',
            taluka_name_en='Paithan',
            panchayat_name_mr='ग्रामपंचायत कार्यालय, नारायणगाव',
            panchayat_name_en='Gram Panchayat Office, Narayangaon',
            office_address_mr='मु. पो. नारायणगाव, ता. पैठण, जि. छत्रपती संभाजीनगर, महाराष्ट्र — ४३११४८',
            office_address_en='At Post Narayangaon, Taluka Paithan, Dist Chhatrapati Sambhajinagar, Maharashtra 431148',
            contact_email='grampanchayat.narayangaon@gov.in',
            contact_phone='02431-223022',
            sarpanch_name='सरपंच (लोकप्रतिनिधी)',
            gram_sevak_name='ग्रामसेवक / ग्रामविकास अधिकारी',
        )

    if request.method == 'GET':
        return JsonResponse({
            'profile': {
                'id': profile.id,
                'census_code': profile.census_code,
                'lgd_code': profile.lgd_code,
                'district_name_mr': profile.district_name_mr,
                'district_name_en': profile.district_name_en,
                'taluka_name_mr': profile.taluka_name_mr,
                'taluka_name_en': profile.taluka_name_en,
                'panchayat_name_mr': profile.panchayat_name_mr,
                'panchayat_name_en': profile.panchayat_name_en,
                'office_address_mr': profile.office_address_mr,
                'office_address_en': profile.office_address_en,
                'contact_email': profile.contact_email,
                'contact_phone': profile.contact_phone,
                'sarpanch_name': profile.sarpanch_name,
                'gram_sevak_name': profile.gram_sevak_name,
                'official_seal_asset_path': profile.official_seal_asset_path,
                'show_archived_notices_publicly': profile.show_archived_notices_publicly,
                'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
                'updated_by': profile.updated_by.email if profile.updated_by else None,
            }
        })

    # PUT: Update profile (Super Admin only)
    if not is_super_admin(request.user):
        return JsonResponse({'detail': 'Only the Super Administrator (Gram Sevak) can update Panchayat profile and office-holder records.'}, status=403)

    data, err = _parse_json(request)
    if err:
        return err

    # Editable fields
    if 'sarpanch_name' in data:
        name = str(data['sarpanch_name']).strip()
        if not name:
            return JsonResponse({'detail': 'Sarpanch name cannot be empty.'}, status=400)
        profile.sarpanch_name = name

    if 'gram_sevak_name' in data:
        name = str(data['gram_sevak_name']).strip()
        if not name:
            return JsonResponse({'detail': 'Gram Sevak name cannot be empty.'}, status=400)
        profile.gram_sevak_name = name

    if 'contact_phone' in data:
        profile.contact_phone = str(data['contact_phone']).strip()

    if 'contact_email' in data:
        profile.contact_email = str(data['contact_email']).strip().lower()

    if 'office_address_mr' in data:
        profile.office_address_mr = str(data['office_address_mr']).strip()

    if 'office_address_en' in data:
        profile.office_address_en = str(data['office_address_en']).strip()

    if 'panchayat_name_mr' in data:
        profile.panchayat_name_mr = str(data['panchayat_name_mr']).strip()

    if 'panchayat_name_en' in data:
        profile.panchayat_name_en = str(data['panchayat_name_en']).strip()

    if 'show_archived_notices_publicly' in data:
        profile.show_archived_notices_publicly = bool(data['show_archived_notices_publicly'])

    profile.updated_by = request.user
    profile.save()

    logger.info("Panchayat profile updated by Super Admin %s: Sarpanch='%s', GramSevak='%s'",
                request.user.email, profile.sarpanch_name, profile.gram_sevak_name)

    return JsonResponse({
        'detail': 'Panchayat profile and office-holder details updated successfully.',
        'profile': {
            'id': profile.id,
            'sarpanch_name': profile.sarpanch_name,
            'gram_sevak_name': profile.gram_sevak_name,
            'contact_phone': profile.contact_phone,
            'contact_email': profile.contact_email,
            'office_address_mr': profile.office_address_mr,
            'office_address_en': profile.office_address_en,
            'panchayat_name_mr': profile.panchayat_name_mr,
            'panchayat_name_en': profile.panchayat_name_en,
            'show_archived_notices_publicly': profile.show_archived_notices_publicly,
            'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
            'updated_by': profile.updated_by.email if profile.updated_by else None,
        }
    })

