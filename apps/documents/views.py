"""
Protected document delivery views for GramSetu platform.

Implements the 5-Point Abstract Document Delivery Security Contract (ADR 0004):
1. Mandatory application mediation (no static direct web access).
2. Unguessable storage identifiers (no identifier-as-authorization).
3. Strict disclosure gate (anonymous users get 404 for unapproved/confidential items).
4. Isolated private storage outside web root.
5. Pluggable streaming delivery with integrity checks.
"""

import logging
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation, ValidationError
from django.http import FileResponse, Http404, HttpResponseForbidden, HttpResponseServerError, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from apps.documents.models import (
    Document,
    DocumentTranslation,
    DocumentVersion,
    LANGUAGE_MARATHI,
    LANGUAGE_CHOICES,
    CATEGORY_CHOICES,
)
from apps.documents.storage import sanitize_filename
from apps.identity.permissions import is_super_admin, is_operator

logger = logging.getLogger('gramsetu.documents')


@require_GET
def citizen_document_download(request, translation_id):
    """
    Public citizen download endpoint for an active approved DocumentTranslation.
    
    Security Contract Enforcement:
    - If translation is publicly disclosed: verify file on disk, check SHA-256 integrity, stream FileResponse.
    - If file missing from disk: log critical error, return 404 (no internal paths leaked).
    - If integrity checksum fails: halt download, log critical error, return 500.
    - If translation is NOT disclosed:
        * Anonymous users receive 404 Not Found (avoids confirming existence of restricted documents).
        * Authenticated staff (Super Admin / Operator) can preview.
        * Authenticated non-staff users receive 403 Forbidden.
    """
    try:
        translation = (
            DocumentTranslation.objects
            .select_related('document', 'current_version', 'current_publication_event')
            .get(id=translation_id)
        )
    except DocumentTranslation.DoesNotExist:
        raise Http404("Document translation not found.")

    is_public = translation.is_publicly_disclosed()

    if not is_public:
        # Strict Disclosure Gate (ADR 0004 Section 4)
        if request.user.is_anonymous:
            # Never return 403 to anonymous users; return 404 to prevent IDOR / file enumeration
            raise Http404("Document translation not found.")

        # Authenticated user inspection
        if not (is_super_admin(request.user) or is_operator(request.user)):
            return HttpResponseForbidden("You do not have permission to view or download this document.")

        # Staff preview of unapproved / draft version
        version = translation.current_version or translation.versions.order_by('-version_number').first()
        if not version:
            raise Http404("No document version uploaded for this translation yet.")
    else:
        version = translation.current_version
        if not version:
            logger.critical(
                "DocumentTranslation %s is marked disclosed but has no current_version set.",
                translation.id,
            )
            raise Http404("Document not available.")

    # Resolve physical storage path
    try:
        file_path = version.get_file_path()
    except SuspiciousOperation as e:
        logger.critical("Path traversal attempt blocked for DocumentVersion %s: %s", version.id, str(e))
        raise Http404("Invalid document storage path.")

    # Storage drift check
    if not file_path.exists() or not file_path.is_file():
        logger.critical(
            "STORAGE DRIFT: Physical file missing on disk for DocumentVersion %s (path: %s).",
            version.id,
            version.storage_path,
        )
        raise Http404("Document file is temporarily unavailable.")

    # Integrity verification
    if not version.verify_integrity():
        logger.critical(
            "SECURITY INTEGRITY FAILURE: SHA-256 checksum mismatch for DocumentVersion %s (path: %s). "
            "Halting download immediately.",
            version.id,
            version.storage_path,
        )
        return HttpResponseServerError("Document integrity verification failed. Download halted.")

    # Deliver file via application-mediated FileResponse
    safe_filename = sanitize_filename(version.original_filename)
    response = FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename=safe_filename,
        content_type=version.mime_type or 'application/octet-stream',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@require_GET
def version_document_download(request, version_id):
    """
    Administrative and statutory audit endpoint for downloading a specific DocumentVersion.
    Restricted to authenticated staff (Super Admin and Operators).
    Anonymous users always receive 404 Not Found.
    """
    if request.user.is_anonymous:
        raise Http404("Document version not found.")

    if not (is_super_admin(request.user) or is_operator(request.user)):
        return HttpResponseForbidden("You do not have administrative permission to access document versions.")

    try:
        version = (
            DocumentVersion.objects
            .select_related('translation', 'translation__document')
            .get(id=version_id)
        )
    except DocumentVersion.DoesNotExist:
        raise Http404("Document version not found.")

    try:
        file_path = version.get_file_path()
    except SuspiciousOperation as e:
        logger.critical("Path traversal attempt blocked for DocumentVersion %s: %s", version.id, str(e))
        raise Http404("Invalid document storage path.")

    if not file_path.exists() or not file_path.is_file():
        logger.critical(
            "STORAGE DRIFT: Physical file missing for DocumentVersion %s (path: %s).",
            version.id,
            version.storage_path,
        )
        raise Http404("Document file missing from storage.")

    if not version.verify_integrity():
        logger.critical(
            "SECURITY INTEGRITY FAILURE: SHA-256 checksum mismatch for DocumentVersion %s (path: %s).",
            version.id,
            version.storage_path,
        )
        return HttpResponseServerError("Document integrity verification failed.")

    safe_filename = sanitize_filename(version.original_filename)
    response = FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename=safe_filename,
        content_type=version.mime_type or 'application/octet-stream',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@require_GET
def document_list_api_view(request):
    """
    Public listing of approved, publicly disclosed documents.
    Supports ?lang=mr|hi|en (Default: mr) and ?category=...
    Excludes confidential documents, draft versions, and withdrawn documents.
    Gracefully falls back to primary Marathi record if translation is missing.
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI).strip().lower()
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    category = request.GET.get('category', '').strip().lower()
    valid_categories = [c[0] for c in CATEGORY_CHOICES]
    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    # Category alias mapping for resilience across frontend versions
    CATEGORY_ALIASES = {
        'gram_sabha_resolution': 'resolution',
        'meeting_minutes': 'resolution',
        'audit_finance': 'budget',
        'development_works': 'statutory_report',
        'policy': 'citizen_charter',
        'general': 'statutory_report',
    }
    if category in CATEGORY_ALIASES:
        category = CATEGORY_ALIASES[category]

    if allow_fallback:
        # Query disclosed documents in either requested lang or fallback to mr
        disclosed_trans = DocumentTranslation.objects.disclosed()
        doc_ids_lang = set(disclosed_trans.filter(language_code=lang).values_list('document_id', flat=True))
        doc_ids_mr = set(disclosed_trans.filter(language_code=LANGUAGE_MARATHI).values_list('document_id', flat=True))
        all_eligible = doc_ids_lang | doc_ids_mr
        qs = Document.objects.filter(id__in=all_eligible)
    else:
        qs = Document.objects.disclosed(language_code=lang)

    if category and category in valid_categories:
        qs = qs.filter(category=category)

    qs = qs.order_by('-issue_date', '-created_at')

    results = []
    for doc in qs:
        trans = doc.translations.filter(language_code=lang).first()
        is_fallback = False
        if not trans or not trans.is_publicly_disclosed():
            if allow_fallback:
                trans = doc.translations.filter(language_code=LANGUAGE_MARATHI).first()
                is_fallback = True

        if not trans or not trans.is_publicly_disclosed():
            continue

        ver = trans.current_version
        if not ver:
            continue

        results.append({
            'id': str(doc.id),
            'translation_id': str(trans.id),
            'category': doc.category,
            'category_display': doc.get_category_display(),
            'reference_number': doc.reference_number,
            'issuing_department': doc.issuing_department,
            'issue_date': doc.issue_date.isoformat() if doc.issue_date else None,
            'title': trans.title,
            'description': trans.description,
            'slug': trans.slug,
            'language_code': trans.language_code,
            'is_fallback': is_fallback and (lang != LANGUAGE_MARATHI),
            'version_number': ver.version_number,
            'file_size_bytes': ver.file_size_bytes,
            'mime_type': ver.mime_type,
            'original_filename': ver.original_filename,
            'download_url': f"/documents/{trans.id}/download/",
        })

    return JsonResponse({
        'language': lang,
        'category': category,
        'count': len(results),
        'results': results,
    })


@require_GET
def document_detail_api_view(request, document_id):
    """
    Public detail view for a specific disclosed Document.
    Returns 404 for unapproved, confidential, or missing translations.
    Gracefully falls back to primary Marathi record if translation is missing.
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI).strip().lower()
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    try:
        doc = Document.objects.get(id=document_id)
    except (Document.DoesNotExist, ValidationError, ValueError):
        raise Http404("Document not found.")

    if doc.is_confidential:
        raise Http404("Document not found.")

    allow_fallback = request.GET.get('fallback', '0').lower() in ('1', 'true', 'yes')

    trans = doc.translations.filter(language_code=lang).first()
    is_fallback = False
    if not trans or not trans.is_publicly_disclosed():
        if allow_fallback:
            trans = doc.translations.filter(language_code=LANGUAGE_MARATHI).first()
            is_fallback = True

    if not trans or not trans.is_publicly_disclosed():
        raise Http404("Document translation not disclosed or available in the requested language.")

    ver = trans.current_version
    if not ver:
        raise Http404("No approved version available.")

    return JsonResponse({
        'id': str(doc.id),
        'translation_id': str(trans.id),
        'category': doc.category,
        'category_display': doc.get_category_display(),
        'reference_number': doc.reference_number,
        'issuing_department': doc.issuing_department,
        'issue_date': doc.issue_date.isoformat() if doc.issue_date else None,
        'title': trans.title,
        'description': trans.description,
        'slug': trans.slug,
        'language_code': trans.language_code,
        'is_fallback': is_fallback and (lang != LANGUAGE_MARATHI),
        'version_number': ver.version_number,
        'file_size_bytes': ver.file_size_bytes,
        'mime_type': ver.mime_type,
        'original_filename': ver.original_filename,
        'download_url': f"/documents/{trans.id}/download/",
    })

