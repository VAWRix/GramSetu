"""
Public Read-Only API for Notices and Announcements (apps.notices).

Exposes:
- GET /api/notices/ : Paginated listing of approved, published notices.
- GET /api/notices/<uuid:notice_id>/ : Detail of an approved published notice.
- Supports ?lang=mr|hi|en (Default: mr), ?type=..., ?urgency=..., ?allow_archived=0|1.
- Strictly adheres to canonical public disclosure gate (ADR 0003).
"""

import json
import re
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, EmptyPage
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from apps.notices.models import (
    Notice,
    NoticeTranslation,
    LANGUAGE_MARATHI,
    LANGUAGE_CHOICES,
    NOTICE_TYPE_CHOICES,
    URGENCY_CHOICES,
)

VALID_LANGUAGES = [c[0] for c in LANGUAGE_CHOICES]
VALID_TYPES = [c[0] for c in NOTICE_TYPE_CHOICES]
VALID_URGENCIES = [c[0] for c in URGENCY_CHOICES]

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


def derive_notice_preview(summary: str, body_markdown: str, max_length: int = 180) -> str:
    """
    Returns a clean, plain-text summary or excerpt for public notice listings.
    Prefers dedicated summary if non-empty. Otherwise extracts safe 1-2 sentences
    from body_markdown, stripping markdown/HTML formatting to prevent raw markup
    or XSS injection.
    """
    if summary and summary.strip():
        text = summary.strip()
        if len(text) > max_length:
            truncated = text[:max_length].rsplit(' ', 1)[0]
            return (truncated + '...') if len(truncated) < len(text) else text
        return text

    if not body_markdown or not body_markdown.strip():
        return ''

    # Strip HTML tags
    cleaned = re.sub(r'<[^>]+>', ' ', body_markdown)
    # Strip Markdown images and links: ![alt](url) -> alt, [text](url) -> text
    cleaned = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', cleaned)
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', cleaned)
    # Strip Markdown headings, blockquotes, bold/italic symbols, code blocks
    cleaned = re.sub(r'#{1,6}\s*', '', cleaned)
    cleaned = re.sub(r'[`*_~>#]', '', cleaned)
    # Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if not cleaned:
        return ''

    if len(cleaned) <= max_length:
        return cleaned

    truncated = cleaned[:max_length].rsplit(' ', 1)[0]
    return (truncated + '...') if len(truncated) < len(cleaned) else cleaned


@require_http_methods(['GET', 'HEAD'])
def notice_list_api_view(request):
    """
    Public listing of approved, published notices.
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI).strip().lower()
    if lang not in VALID_LANGUAGES:
        lang = LANGUAGE_MARATHI

    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    notice_type = request.GET.get('type', '').strip().lower()
    urgency = request.GET.get('urgency', '').strip().lower()

    # Aliases for frontend flexibility and backward compatibility
    TYPE_ALIASES = {
        'public_notice': 'general',
        'administrative': 'statutory',
    }
    if notice_type in TYPE_ALIASES:
        notice_type = TYPE_ALIASES[notice_type]

    URGENCY_ALIASES = {
        'emergency': 'urgent',
    }
    if urgency in URGENCY_ALIASES:
        urgency = URGENCY_ALIASES[urgency]

    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    if allow_fallback:
        # Query published notices having approved translation in the requested language, or fallback to Marathi
        published_trans = NoticeTranslation.objects.published(allow_archived=allow_archived)
        notice_ids_lang = set(published_trans.filter(language_code=lang).values_list('notice_id', flat=True))
        notice_ids_mr = set(published_trans.filter(language_code=LANGUAGE_MARATHI).values_list('notice_id', flat=True))
        all_eligible = notice_ids_lang | notice_ids_mr
        qs = Notice.objects.filter(id__in=all_eligible)
    else:
        qs = Notice.objects.published(language_code=lang, allow_archived=allow_archived)

    if notice_type and notice_type in VALID_TYPES:
        qs = qs.filter(notice_type=notice_type)

    if urgency and urgency in VALID_URGENCIES:
        qs = qs.filter(urgency=urgency)

    qs = qs.order_by('-effective_from', '-created_at')

    try:
        page_num = int(request.GET.get('page', 1))
        if page_num < 1:
            page_num = 1
    except (ValueError, TypeError):
        page_num = 1

    try:
        page_size = int(request.GET.get('page_size', DEFAULT_PAGE_SIZE))
        if page_size < 1:
            page_size = DEFAULT_PAGE_SIZE
        elif page_size > MAX_PAGE_SIZE:
            page_size = MAX_PAGE_SIZE
    except (ValueError, TypeError):
        page_size = DEFAULT_PAGE_SIZE

    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page_num)
    except EmptyPage:
        page_obj = []

    results = []
    for notice in page_obj:
        trans = notice.translations.filter(language_code=lang).first()
        is_fallback = False
        if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
            if allow_fallback:
                trans = notice.translations.filter(language_code=LANGUAGE_MARATHI).first()
                is_fallback = True

        if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
            continue

        rev = trans.current_approved_revision
        if not rev:
            continue

        now = timezone.now()
        has_deadline = notice.deadline is not None
        is_deadline_passed = bool(has_deadline and notice.deadline <= now)
        preview = derive_notice_preview(rev.summary, rev.body_markdown)
        results.append({
            'id': str(notice.id),
            'notice_type': notice.notice_type,
            'notice_type_display': notice.get_notice_type_display(),
            'urgency': notice.urgency,
            'urgency_display': notice.get_urgency_display(),
            'reference_number': notice.reference_number,
            'issue_date': notice.issue_date.isoformat() if notice.issue_date else None,
            'effective_from': notice.effective_from.isoformat() if notice.effective_from else None,
            'expires_at': notice.expires_at.isoformat() if notice.expires_at else None,
            'deadline': notice.deadline.isoformat() if notice.deadline else None,
            'has_deadline': has_deadline,
            'is_deadline_passed': is_deadline_passed,
            'is_urgent_published': notice.is_urgent_published,
            'title': rev.title,
            'summary': preview or rev.summary or '',
            'description': preview,
            'language_code': trans.language_code,
            'is_fallback': is_fallback and (lang != LANGUAGE_MARATHI),
            'created_at': notice.created_at.isoformat(),
        })

    return JsonResponse({
        'language': lang,
        'count': paginator.count,
        'page': page_num,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'results': results,
    })


@require_http_methods(['GET', 'HEAD'])
def notice_detail_api_view(request, notice_id):
    """
    Public detail view for a specific Notice.
    Strictly returns 404 if notice or requested translation is not eligible for disclosure.
    Gracefully falls back to primary Marathi record if translation is missing.
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI).strip().lower()
    if lang not in VALID_LANGUAGES:
        lang = LANGUAGE_MARATHI

    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    try:
        notice = Notice.objects.get(id=notice_id)
    except (Notice.DoesNotExist, ValidationError, ValueError):
        raise Http404("Notice not found.")

    trans = notice.translations.filter(language_code=lang).first()
    is_fallback = False
    if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
        if allow_fallback:
            trans = notice.translations.filter(language_code=LANGUAGE_MARATHI).first()
            is_fallback = True

    if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
        raise Http404("Notice translation not available or not disclosed in the requested language.")

    rev = trans.current_approved_revision
    if not rev:
        raise Http404("No approved revision available for this notice.")

    # Sanitize attachments (do not leak internal storage paths)
    attachments = []
    if rev.attachments_metadata and isinstance(rev.attachments_metadata, list):
        for a in rev.attachments_metadata:
            if isinstance(a, dict):
                attachments.append({
                    'title': a.get('title', ''),
                    'filename': a.get('original_filename') or a.get('filename', ''),
                    'file_size': a.get('file_size_bytes') or a.get('file_size', 0),
                    'mime_type': a.get('mime_type', ''),
                })

    preview = derive_notice_preview(rev.summary, rev.body_markdown)
    now = timezone.now()
    has_deadline = notice.deadline is not None
    is_deadline_passed = bool(has_deadline and notice.deadline <= now)
    return JsonResponse({
        'id': str(notice.id),
        'notice_type': notice.notice_type,
        'notice_type_display': notice.get_notice_type_display(),
        'urgency': notice.urgency,
        'urgency_display': notice.get_urgency_display(),
        'reference_number': notice.reference_number,
        'issue_date': notice.issue_date.isoformat() if notice.issue_date else None,
        'effective_from': notice.effective_from.isoformat() if notice.effective_from else None,
        'expires_at': notice.expires_at.isoformat() if notice.expires_at else None,
        'deadline': notice.deadline.isoformat() if notice.deadline else None,
        'has_deadline': has_deadline,
        'is_deadline_passed': is_deadline_passed,
        'is_urgent_published': notice.is_urgent_published,
        'title': rev.title,
        'summary': rev.summary or preview,
        'description': preview,
        'body_markdown': rev.body_markdown,
        'language_code': trans.language_code,
        'is_fallback': is_fallback and (lang != LANGUAGE_MARATHI),
        'attachments': attachments,
        'created_at': notice.created_at.isoformat(),
    })
