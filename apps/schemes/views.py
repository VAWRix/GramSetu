"""
Public citizen-facing views for Government Welfare Schemes (apps.schemes).

Enforces the canonical public disclosure gate (ADR 0003):
- Only active, approved, and published scheme translations are visible to anonymous citizens.
- Draft, submitted, unapproved, withdrawn, and archived schemes strictly return 404 to anonymous users.
- Explicit language selection (?lang=mr|hi|en) with zero silent language fallback.
- Strictly informational: no citizen applications, tracking, or document submissions.
"""

from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from apps.schemes.models import (
    WelfareScheme,
    SchemeTranslation,
    LANGUAGE_MARATHI,
    LANGUAGE_CHOICES,
    SCHEME_LEVEL_CHOICES,
    BENEFICIARY_CHOICES,
)
from apps.identity.permissions import is_super_admin, is_operator


def scheme_list_view(request):
    """
    Public listing of approved, published government welfare schemes.
    Supports:
    - ?lang=mr|hi|en (Default: mr)
    - ?level=central|state|district
    - ?beneficiary=farmers|women|youth|senior_citizens|general
    - ?allow_archived=0|1
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI)
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    level = request.GET.get('level', '').strip()
    beneficiary = request.GET.get('beneficiary', '').strip()
    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    if allow_fallback:
        published_trans = SchemeTranslation.objects.published(allow_archived=allow_archived)
        scheme_ids_lang = set(published_trans.filter(language_code=lang).values_list('scheme_id', flat=True))
        scheme_ids_mr = set(published_trans.filter(language_code=LANGUAGE_MARATHI).values_list('scheme_id', flat=True))
        all_eligible = scheme_ids_lang | scheme_ids_mr
        qs = WelfareScheme.objects.filter(id__in=all_eligible)
    else:
        qs = WelfareScheme.objects.published(language_code=lang, allow_archived=allow_archived)

    if level and level in [c[0] for c in SCHEME_LEVEL_CHOICES]:
        qs = qs.by_level(level)

    if beneficiary and beneficiary in [c[0] for c in BENEFICIARY_CHOICES]:
        qs = qs.by_beneficiary(beneficiary)

    schemes_data = []
    for scheme in qs.order_by('display_order', '-created_at'):
        trans = scheme.get_translation(lang)
        is_fallback = False
        if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
            if allow_fallback:
                trans = scheme.get_translation(LANGUAGE_MARATHI)
                is_fallback = True

        if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
            continue

        schemes_data.append({
            'id': str(scheme.id),
            'slug': scheme.slug,
            'scheme_level': scheme.scheme_level,
            'scheme_level_display': scheme.get_scheme_level_display(),
            'target_beneficiary': scheme.target_beneficiary,
            'target_beneficiary_display': scheme.get_target_beneficiary_display(),
            'scheme_name': trans.scheme_name,
            'short_summary': trans.short_summary,
            'official_portal_url': scheme.official_portal_url,
            'department': scheme.department,
            'contact_details': scheme.contact_details,
            'display_order': scheme.display_order,
            'language_code': trans.language_code,
            'is_fallback': is_fallback and (lang != LANGUAGE_MARATHI),
            'updated_at': scheme.updated_at.isoformat() if scheme.updated_at else None,
        })

    return JsonResponse({
        'language': lang,
        'level_filter': level or 'all',
        'beneficiary_filter': beneficiary or 'all',
        'count': len(schemes_data),
        'results': schemes_data,
    })


def scheme_detail_view(request, identifier):
    """
    Public detail view for a specific WelfareScheme.
    Identifier can be either scheme UUID or slug.
    Enforces disclosure gate: unapproved/withdrawn schemes return 404 to anonymous users.
    Gracefully falls back to primary Marathi record if translation is missing.
    """
    # Attempt lookup by UUID or slug
    scheme = None
    try:
        scheme = WelfareScheme.objects.get(id=identifier)
    except (WelfareScheme.DoesNotExist, ValueError, ValidationError):
        try:
            scheme = WelfareScheme.objects.get(slug=identifier)
        except WelfareScheme.DoesNotExist:
            raise Http404("Welfare scheme not found.")

    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')
    lang = request.GET.get('lang', LANGUAGE_MARATHI)
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    trans = scheme.get_translation(lang)
    is_fallback = False
    if not trans or not trans.is_publicly_visible(allow_archived=allow_archived):
        if allow_fallback:
            trans = scheme.get_translation(LANGUAGE_MARATHI)
            is_fallback = True

    # Check public visibility
    is_visible = trans is not None and trans.is_publicly_visible(allow_archived=allow_archived)
    if not is_visible:
        if request.user.is_anonymous or not (is_super_admin(request.user) or is_operator(request.user)):
            raise Http404("Welfare scheme not found.")

    if not trans:
        raise Http404(f"No translation available for language '{lang}'.")

    # Fetch disclosed supporting documents
    docs_data = []
    for doc in scheme.supporting_documents.all():
        doc_trans = doc.translations.filter(language_code=lang).first()
        if not doc_trans:
            doc_trans = doc.translations.filter(language_code=LANGUAGE_MARATHI).first()
        if doc_trans and doc_trans.status == 'disclosed' and doc_trans.current_version_id:
            docs_data.append({
                'id': str(doc.id),
                'title': doc_trans.title,
                'category': doc.category,
                'category_display': doc.get_category_display(),
                'reference_number': doc.reference_number,
                'download_url': f"/documents/{doc.id}/download/",
            })

    return JsonResponse({
        'id': str(scheme.id),
        'slug': scheme.slug,
        'scheme_level': scheme.scheme_level,
        'scheme_level_display': scheme.get_scheme_level_display(),
        'target_beneficiary': scheme.target_beneficiary,
        'target_beneficiary_display': scheme.get_target_beneficiary_display(),
        'official_portal_url': scheme.official_portal_url,
        'department': scheme.department,
        'contact_details': scheme.contact_details,
        'language': lang,
        'status': trans.status,
        'scheme_name': trans.scheme_name,
        'short_summary': trans.short_summary,
        'eligibility_criteria': trans.eligibility_criteria,
        'benefits': trans.benefits,
        'required_documents': trans.required_documents,
        'application_process': trans.application_process,
        'supporting_documents': docs_data,
        'updated_at': scheme.updated_at.isoformat() if scheme.updated_at else None,
        'created_at': scheme.created_at.isoformat() if scheme.created_at else None,
        'portal_notice': "This is an official informational portal. Citizen applications must be submitted via designated government offices or official portals.",
    })
