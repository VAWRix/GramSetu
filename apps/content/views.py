"""
Public Read-Only API for Informational Content (apps.content).

Exposes:
- GET /api/content/pages/ : List of published, approved pages in requested language.
- GET /api/content/pages/<slug>/ : Detail of an approved published page translation.
- Strictly adheres to canonical public disclosure gate (ADR 0003).
- Strict language isolation (?lang=mr|hi|en, default: mr) with zero silent fallback.
"""

from django.db.models import Q
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from apps.content.models import (
    Page,
    PageTranslation,
    LANGUAGE_MARATHI,
    LANGUAGE_CHOICES,
    STATUS_PUBLISHED,
)

VALID_LANGUAGES = [c[0] for c in LANGUAGE_CHOICES]


@require_http_methods(['GET', 'HEAD'])
def page_list_api_view(request):
    """
    Public listing of approved, published informational pages.
    Supports ?lang=mr|hi|en (Default: mr), ?allow_archived=0|1, and ?fallback=0|1.
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI).strip().lower()
    if lang not in VALID_LANGUAGES:
        lang = LANGUAGE_MARATHI

    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    if allow_fallback:
        published_trans = PageTranslation.objects.published(allow_archived=allow_archived)
        all_eligible_page_ids = set(published_trans.values_list('page_id', flat=True))
        qs = Page.objects.filter(id__in=all_eligible_page_ids).order_by('display_order', 'slug')
    else:
        qs = Page.objects.published(language_code=lang, allow_archived=allow_archived).order_by('display_order', 'slug')

    pages_data = []
    for page in qs:
        trans = page.translations.filter(language_code=lang).first()
        is_fallback = False
        if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
            if allow_fallback:
                trans = (
                    page.translations.filter(language_code=LANGUAGE_MARATHI).first()
                    or page.translations.filter(status=STATUS_PUBLISHED).first()
                )
                is_fallback = True

        if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
            continue

        rev = trans.current_approved_revision
        if not rev:
            continue

        pages_data.append({
            'id': str(page.id),
            'slug': page.slug,
            'localized_slug': trans.localized_slug,
            'language_code': trans.language_code,
            'title': rev.title,
            'summary': rev.summary,
            'body_markdown': rev.body_markdown or '',
            'sections_data': rev.sections_data or [],
            'references_data': rev.references_data or [],
            'is_system_page': page.is_system_page,
            'display_order': page.display_order,
            'updated_at': trans.updated_at.isoformat(),
            'is_fallback': is_fallback and (trans.language_code != lang),
        })

    return JsonResponse({
        'language': lang,
        'count': len(pages_data),
        'results': pages_data,
    })


@require_http_methods(['GET', 'HEAD'])
def page_detail_api_view(request, slug):
    """
    Public detail view for a specific published Page.
    Enforces the disclosure gate: unapproved or missing translations strictly return 404.
    Supports ?fallback=0|1 for graceful Marathi/primary fallback when enabled.
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI).strip().lower()
    if lang not in VALID_LANGUAGES:
        lang = LANGUAGE_MARATHI

    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    # Match by canonical ASCII slug or localized slug
    page = Page.objects.filter(
        Q(slug=slug) | Q(translations__localized_slug=slug)
    ).distinct().first()

    if not page:
        raise Http404("Page not found.")

    trans = page.translations.filter(language_code=lang).first()
    is_fallback = False
    if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
        if allow_fallback:
            trans = (
                page.translations.filter(language_code=LANGUAGE_MARATHI).first()
                or page.translations.filter(status=STATUS_PUBLISHED).first()
            )
            is_fallback = True

    if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
        raise Http404("Page translation not available or not disclosed in the requested language.")

    rev = trans.current_approved_revision
    if not rev:
        raise Http404("No approved revision available for this page.")

    return JsonResponse({
        'id': str(page.id),
        'slug': page.slug,
        'localized_slug': trans.localized_slug,
        'language_code': trans.language_code,
        'title': rev.title,
        'summary': rev.summary,
        'body_markdown': rev.body_markdown or '',
        'sections_data': rev.sections_data or [],
        'references_data': rev.references_data or [],
        'is_system_page': page.is_system_page,
        'display_order': page.display_order,
        'updated_at': trans.updated_at.isoformat(),
        'is_fallback': is_fallback and (trans.language_code != lang),
    })
