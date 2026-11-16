"""
Search indexing and query execution services for Unified Public Search (apps.search).

Provides:
- Input sanitization and safe query normalization.
- Automatic denormalized projection indexing across all 6 approved public domains:
  Pages (apps.content), Notices (apps.notices), Documents (apps.documents),
  Events (apps.events), Schemes (apps.schemes), and Media Gallery (apps.gallery).
- Strict enforcement of public eligibility, statutory disclosure gates, and language isolation.
- Fast PostgreSQL full-text search with fallback substring matching.
- Leakage protection: zero exposure of draft content, private storage paths, or confidential records.
"""

from datetime import datetime, time, date
import logging
import re
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Q, F, Case, When, Value, IntegerField
from django.utils import timezone

from apps.search.models import (
    SearchDocumentIndex,
    TYPE_PAGE,
    TYPE_NOTICE,
    TYPE_DOCUMENT,
    TYPE_EVENT,
    TYPE_SCHEME,
    TYPE_GALLERY,
    TARGET_CONTENT_TYPE_CHOICES,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
    LANGUAGE_CHOICES,
)

logger = logging.getLogger('gramsetu.search')

MAX_QUERY_LENGTH = 200
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50

# Content type display mapping
CONTENT_TYPE_DISPLAY_MAP = {
    TYPE_PAGE: 'Informational Page / माहिती पान',
    TYPE_NOTICE: 'Notice & Announcement / सूचना व जाहिरात',
    TYPE_DOCUMENT: 'Document & Download / दस्तऐवज',
    TYPE_EVENT: 'Event & Meeting / कार्यक्रम व सभा',
    TYPE_SCHEME: 'Government Scheme / शासकीय योजना',
    TYPE_GALLERY: 'Media Gallery / चित्रदालन',
}


def normalize_search_query(raw_query: str) -> str:
    """
    Safely cleans and normalizes user search query input.
    - Strips control characters.
    - Normalizes redundant whitespace.
    - Enforces maximum character length cap to prevent denial-of-service.
    """
    if not raw_query or not isinstance(raw_query, str):
        return ""

    # Remove non-printable control characters (keep Devanagari and printable ASCII)
    cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', raw_query)
    # Collapse consecutive whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Cap length
    if len(cleaned) > MAX_QUERY_LENGTH:
        cleaned = cleaned[:MAX_QUERY_LENGTH].strip()

    return cleaned


def update_search_vector_for_entry(entry_id: int):
    """
    Regenerates the PostgreSQL tsvector on SearchDocumentIndex with weighted fields.
    """
    try:
        SearchDocumentIndex.objects.filter(pk=entry_id).update(
            search_vector=(
                SearchVector('title', weight='A', config='simple')
                + SearchVector('summary', weight='B', config='simple')
                + SearchVector('search_text', weight='C', config='simple')
            )
        )
    except Exception as e:
        logger.warning(f"Could not update search vector for SearchDocumentIndex #{entry_id}: {e}")


# ------------------------------------------------------------------------------
# Domain-Specific Indexing Handlers (Strictly Enforce Canonical Public Invariants)
# ------------------------------------------------------------------------------

def sync_page_translation(translation):
    """
    Synchronizes a PageTranslation into the unified search index.
    Strictly asserts public eligibility via PageTranslation.is_publicly_visible().
    """
    from apps.content.models import PageTranslation
    page = translation.page

    # Verify public visibility under canonical invariants
    is_visible = False
    try:
        is_visible = translation.is_publicly_visible()
    except Exception:
        pass

    if not is_visible:
        SearchDocumentIndex.objects.filter(
            target_content_type=TYPE_PAGE,
            target_id=page.id,
            language_code=translation.language_code,
        ).delete()
        return None

    rev = translation.current_approved_revision
    if not rev:
        return None

    pub_at = (
        translation.current_publication_event.effective_from
        if (translation.current_publication_event and translation.current_publication_event.effective_from)
        else translation.created_at
    )
    url_slug = translation.localized_slug or page.slug

    entry, _ = SearchDocumentIndex.objects.update_or_create(
        target_content_type=TYPE_PAGE,
        target_id=page.id,
        language_code=translation.language_code,
        defaults={
            'title': rev.title.strip(),
            'summary': rev.summary.strip(),
            'search_text': f"{rev.title} {rev.summary} {rev.body_markdown}".strip(),
            'published_at': pub_at,
            'url_path': f"/pages/{url_slug}/",
            'category': 'information',
            'category_display': 'Information / माहिती',
        },
    )
    update_search_vector_for_entry(entry.id)
    return entry


def sync_notice_translation(translation):
    """
    Synchronizes a NoticeTranslation into the unified search index.
    Enforces publication window and unexpired status.
    """
    from apps.notices.models import NoticeTranslation
    notice = translation.notice

    # Verify canonical notice public visibility
    is_visible = False
    try:
        is_visible = translation.is_publicly_visible()
    except Exception:
        pass

    if not is_visible or notice.is_expired():
        SearchDocumentIndex.objects.filter(
            target_content_type=TYPE_NOTICE,
            target_id=notice.id,
            language_code=translation.language_code,
        ).delete()
        return None

    rev = translation.current_approved_revision
    if not rev:
        return None

    pub_at = notice.effective_from or translation.created_at
    ref = f" Ref: {notice.reference_number}" if notice.reference_number else ""
    auth_val = getattr(rev, 'issuing_authority', '')
    auth = f" Authority: {auth_val}" if auth_val else ""

    entry, _ = SearchDocumentIndex.objects.update_or_create(
        target_content_type=TYPE_NOTICE,
        target_id=notice.id,
        language_code=translation.language_code,
        defaults={
            'title': rev.title.strip(),
            'summary': rev.summary.strip(),
            'search_text': f"{rev.title} {rev.summary} {rev.body_markdown}{ref}{auth}".strip(),
            'published_at': pub_at,
            'url_path': f"/notices/{notice.id}/",
            'category': notice.notice_type,
            'category_display': notice.get_notice_type_display(),
        },
    )
    update_search_vector_for_entry(entry.id)
    return entry


def sync_document_translation(translation):
    """
    Synchronizes a DocumentTranslation into the unified search index.
    Enforces confidentiality check (ADR 0004) and approved disclosure status.
    """
    doc = translation.document
    if doc.is_confidential:
        # Confidential records must never appear in public search index
        SearchDocumentIndex.objects.filter(
            target_content_type=TYPE_DOCUMENT,
            target_id=doc.id,
        ).delete()
        return None

    is_disclosed = False
    try:
        is_disclosed = translation.is_publicly_disclosed()
    except Exception:
        pass

    if not is_disclosed:
        SearchDocumentIndex.objects.filter(
            target_content_type=TYPE_DOCUMENT,
            target_id=doc.id,
            language_code=translation.language_code,
        ).delete()
        return None

    ver = translation.current_version
    filename = ver.original_filename if ver else ""
    ref = f" Ref: {doc.reference_number}" if doc.reference_number else ""
    dept = f" Dept: {doc.issuing_department}" if doc.issuing_department else ""

    if doc.issue_date:
        pub_at = timezone.make_aware(datetime.combine(doc.issue_date, time.min))
    else:
        pub_at = translation.created_at

    entry, _ = SearchDocumentIndex.objects.update_or_create(
        target_content_type=TYPE_DOCUMENT,
        target_id=doc.id,
        language_code=translation.language_code,
        defaults={
            'title': translation.title.strip(),
            'summary': translation.description.strip(),
            'search_text': f"{translation.title} {translation.description}{ref}{dept} {filename}".strip(),
            'published_at': pub_at,
            'url_path': f"/documents/{translation.id}/download/",
            'category': doc.category,
            'category_display': doc.get_category_display(),
        },
    )
    update_search_vector_for_entry(entry.id)
    return entry


def sync_event(event):
    """
    Synchronizes all translations of an approved PanchayatEvent into the search index.
    """
    from apps.events.models import STATUS_PUBLISHED, STATUS_COMPLETED

    is_eligible = event.is_published and event.status in (STATUS_PUBLISHED, STATUS_COMPLETED)
    if not is_eligible:
        SearchDocumentIndex.objects.filter(
            target_content_type=TYPE_EVENT,
            target_id=event.id,
        ).delete()
        return []

    entries = []
    pub_at = event.start_datetime or event.created_at

    for translation in event.translations.all():
        venue = translation.venue_override or event.venue_mr or ""
        search_body = f"{translation.title} {translation.description} {translation.agenda} {venue}".strip()

        entry, _ = SearchDocumentIndex.objects.update_or_create(
            target_content_type=TYPE_EVENT,
            target_id=event.id,
            language_code=translation.language_code,
            defaults={
                'title': translation.title.strip(),
                'summary': translation.description.strip(),
                'search_text': search_body,
                'published_at': pub_at,
                'url_path': f"/events/{event.id}/",
                'category': event.event_type,
                'category_display': event.get_event_type_display(),
            },
        )
        update_search_vector_for_entry(entry.id)
        entries.append(entry)

    return entries


def sync_scheme_translation(translation):
    """
    Synchronizes a SchemeTranslation into the unified search index.
    """
    scheme = translation.scheme

    is_visible = False
    try:
        is_visible = scheme.is_active and translation.is_publicly_visible()
    except Exception:
        pass

    if not is_visible:
        SearchDocumentIndex.objects.filter(
            target_content_type=TYPE_SCHEME,
            target_id=scheme.id,
            language_code=translation.language_code,
        ).delete()
        return None

    rev = translation.current_approved_revision
    if not rev:
        return None

    search_body = (
        f"{rev.scheme_name} {rev.short_summary} {rev.eligibility_criteria} "
        f"{rev.required_documents} {rev.application_process}"
    ).strip()

    pub_at = (
        translation.current_publication_event.effective_from
        if (translation.current_publication_event and translation.current_publication_event.effective_from)
        else translation.updated_at
    )

    url_slug = translation.localized_slug or scheme.slug

    entry, _ = SearchDocumentIndex.objects.update_or_create(
        target_content_type=TYPE_SCHEME,
        target_id=scheme.id,
        language_code=translation.language_code,
        defaults={
            'title': rev.scheme_name.strip(),
            'summary': rev.short_summary.strip(),
            'search_text': search_body,
            'published_at': pub_at,
            'url_path': f"/schemes/{url_slug}/",
            'category': scheme.target_beneficiary,
            'category_display': scheme.get_target_beneficiary_display(),
        },
    )
    update_search_vector_for_entry(entry.id)
    return entry


def sync_gallery_album(album):
    """
    Synchronizes all translations of an approved GalleryAlbum into the search index.
    """
    from apps.gallery.models import STATUS_PUBLISHED

    is_eligible = album.is_published and album.status == STATUS_PUBLISHED
    if not is_eligible:
        SearchDocumentIndex.objects.filter(
            target_content_type=TYPE_GALLERY,
            target_id=album.id,
        ).delete()
        return []

    entries = []
    if album.event_date:
        pub_at = timezone.make_aware(datetime.combine(album.event_date, time.min))
    else:
        pub_at = album.created_at

    for translation in album.translations.all():
        lang = translation.language_code
        photo_captions = [
            f"{item.get_caption(lang)} {item.get_alt_text(lang)}"
            for item in album.items.all()
        ]
        search_body = f"{translation.title} {translation.description} " + " ".join(photo_captions)

        entry, _ = SearchDocumentIndex.objects.update_or_create(
            target_content_type=TYPE_GALLERY,
            target_id=album.id,
            language_code=lang,
            defaults={
                'title': translation.title.strip(),
                'summary': translation.description.strip(),
                'search_text': search_body.strip(),
                'published_at': pub_at,
                'url_path': f"/gallery/{album.slug}/",
                'category': album.category,
                'category_display': album.get_category_display(),
            },
        )
        update_search_vector_for_entry(entry.id)
        entries.append(entry)

    return entries


def remove_target_from_index(target_content_type: str, target_id):
    """
    Removes all index entries for a specific target content item.
    """
    SearchDocumentIndex.objects.filter(
        target_content_type=target_content_type,
        target_id=target_id,
    ).delete()


def rebuild_search_index():
    """
    Comprehensively scans all 6 domains and synchronizes all currently eligible records.
    Removes any orphaned or ineligible entries from the index table.
    """
    from apps.content.models import PageTranslation
    from apps.notices.models import NoticeTranslation
    from apps.documents.models import DocumentTranslation
    from apps.events.models import PanchayatEvent
    from apps.schemes.models import SchemeTranslation
    from apps.gallery.models import GalleryAlbum

    indexed_count = 0

    # 1. Informational Pages
    for pt in PageTranslation.objects.all():
        if sync_page_translation(pt):
            indexed_count += 1

    # 2. Notices & Announcements
    for nt in NoticeTranslation.objects.all():
        if sync_notice_translation(nt):
            indexed_count += 1

    # 3. Documents & Downloads
    for dt in DocumentTranslation.objects.all():
        if sync_document_translation(dt):
            indexed_count += 1

    # 4. Events & Meetings
    for ev in PanchayatEvent.objects.all():
        entries = sync_event(ev)
        indexed_count += len(entries)

    # 5. Welfare Schemes
    for st in SchemeTranslation.objects.all():
        if sync_scheme_translation(st):
            indexed_count += 1

    # 6. Media Gallery Albums
    for alb in GalleryAlbum.objects.all():
        entries = sync_gallery_album(alb)
        indexed_count += len(entries)

    logger.info(f"Rebuilt unified search index with {indexed_count} total entries.")
    return indexed_count


# ------------------------------------------------------------------------------
# Unified Public Search Query Execution Engine
# ------------------------------------------------------------------------------

def execute_unified_search(
    query: str = "",
    language: str = LANGUAGE_MARATHI,
    content_type: str = "",
    category: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """
    Executes a high-performance unified search across SearchDocumentIndex.

    Guarantees:
    - Strict language isolation (zero silent language fallback).
    - Dynamic exclusion of any expired notices or confidential records.
    - Parameterized ORM queries preventing SQL injection.
    - Full-text search and partial Devanagari/English substring matching.
    - Safe pagination and clean public metadata.
    """
    # 1. Validate & normalize language
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if language not in valid_langs:
        language = LANGUAGE_MARATHI

    # 2. Normalize search query text
    clean_query = normalize_search_query(query)

    # 3. Page size cap
    try:
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    except (ValueError, TypeError):
        page_size = DEFAULT_PAGE_SIZE

    # 4. Empty-state handling if query and filters are both empty
    has_filters = bool(content_type or category or date_from or date_to)
    if not clean_query and not has_filters:
        return {
            'query': '',
            'language': language,
            'content_type_filter': 'all',
            'category_filter': 'all',
            'date_from': None,
            'date_to': None,
            'total_results': 0,
            'page': 1,
            'page_size': page_size,
            'total_pages': 0,
            'has_next': False,
            'has_previous': False,
            'empty_reason': 'empty_query',
            'results': [],
        }

    # If the index table is completely empty on fresh invocation, auto-rebuild once
    if SearchDocumentIndex.objects.count() == 0:
        rebuild_search_index()

    # 5. Base queryset filtered strictly by requested language (ADR 0001: no silent fallback)
    qs = SearchDocumentIndex.objects.filter(language_code=language)

    # 6. Content type filter
    valid_types = [c[0] for c in TARGET_CONTENT_TYPE_CHOICES]
    if content_type and content_type in valid_types:
        qs = qs.filter(target_content_type=content_type)

    # 7. Category filter
    if category and isinstance(category, str):
        clean_cat = category.strip()
        if clean_cat:
            qs = qs.filter(category=clean_cat)

    # 8. Date range filters (published_at)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d")
            aware_from = timezone.make_aware(datetime.combine(d_from.date(), time.min))
            qs = qs.filter(published_at__gte=aware_from)
        except (ValueError, TypeError):
            pass

    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d")
            aware_to = timezone.make_aware(datetime.combine(d_to.date(), time.max))
            qs = qs.filter(published_at__lte=aware_to)
        except (ValueError, TypeError):
            pass

    # 9. Dynamic Source-of-Truth Live Validation (Defense-in-Depth against stale index entries)
    # Search-index entries cannot independently authorize public disclosure.
    # Canonical domain querysets strictly govern visibility even if signals failed or an index entry became stale.
    from apps.content.models import PageTranslation
    from apps.notices.models import NoticeTranslation
    from apps.documents.models import DocumentTranslation
    from apps.events.models import PanchayatEvent
    from apps.schemes.models import SchemeTranslation
    from apps.gallery.models import GalleryAlbum

    if content_type == TYPE_PAGE:
        qs = qs.filter(target_id__in=PageTranslation.objects.for_language(language).published().values_list('page_id', flat=True))
    elif content_type == TYPE_NOTICE:
        qs = qs.filter(target_id__in=NoticeTranslation.objects.for_language(language).published().values_list('notice_id', flat=True))
    elif content_type == TYPE_DOCUMENT:
        qs = qs.filter(target_id__in=DocumentTranslation.objects.for_language(language).disclosed().values_list('document_id', flat=True))
    elif content_type == TYPE_EVENT:
        qs = qs.filter(target_id__in=PanchayatEvent.objects.public_eligible().for_language(language).values_list('id', flat=True))
    elif content_type == TYPE_SCHEME:
        qs = qs.filter(target_id__in=SchemeTranslation.objects.for_language(language).published().values_list('scheme_id', flat=True))
    elif content_type == TYPE_GALLERY:
        qs = qs.filter(target_id__in=GalleryAlbum.objects.public_eligible().for_language(language).values_list('id', flat=True))
    else:
        valid_q = (
            Q(target_content_type=TYPE_PAGE, target_id__in=PageTranslation.objects.for_language(language).published().values_list('page_id', flat=True))
            | Q(target_content_type=TYPE_NOTICE, target_id__in=NoticeTranslation.objects.for_language(language).published().values_list('notice_id', flat=True))
            | Q(target_content_type=TYPE_DOCUMENT, target_id__in=DocumentTranslation.objects.for_language(language).disclosed().values_list('document_id', flat=True))
            | Q(target_content_type=TYPE_EVENT, target_id__in=PanchayatEvent.objects.public_eligible().for_language(language).values_list('id', flat=True))
            | Q(target_content_type=TYPE_SCHEME, target_id__in=SchemeTranslation.objects.for_language(language).published().values_list('scheme_id', flat=True))
            | Q(target_content_type=TYPE_GALLERY, target_id__in=GalleryAlbum.objects.public_eligible().for_language(language).values_list('id', flat=True))
        )
        qs = qs.filter(valid_q)

    # 10. Query text matching
    if clean_query:
        # Synergistic PostgreSQL full-text search + substring matching for Devanagari & English
        search_q = (
            Q(title__icontains=clean_query)
            | Q(summary__icontains=clean_query)
            | Q(search_text__icontains=clean_query)
        )
        try:
            # Also match PostgreSQL tsvector
            search_q |= Q(search_vector=SearchQuery(clean_query, config='simple'))
        except Exception:
            pass

        qs = qs.filter(search_q)

        # Relevance scoring: exact title match > summary match > text match
        qs = qs.annotate(
            relevance_weight=Case(
                When(title__icontains=clean_query, then=Value(30)),
                When(summary__icontains=clean_query, then=Value(20)),
                When(search_text__icontains=clean_query, then=Value(10)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by('-relevance_weight', '-published_at')
    else:
        qs = qs.order_by('-published_at')

    # 11. Pagination
    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages) if paginator.num_pages > 0 else []

    # 12. Structure public output (strictly approved metadata, zero internal leaks)
    results = []
    items_to_render = page_obj.object_list if hasattr(page_obj, 'object_list') else []
    for item in items_to_render:
        results.append({
            'target_id': str(item.target_id),
            'content_type': item.target_content_type,
            'content_type_display': CONTENT_TYPE_DISPLAY_MAP.get(item.target_content_type, item.target_content_type),
            'title': item.title,
            'summary': item.summary,
            'category': item.category,
            'category_display': item.category_display or item.category,
            'url': item.url_path,
            'published_at': item.published_at.isoformat() if item.published_at else None,
        })

    current_page_num = page_obj.number if hasattr(page_obj, 'number') else 1

    return {
        'query': clean_query,
        'language': language,
        'content_type_filter': content_type or 'all',
        'category_filter': category or 'all',
        'date_from': date_from or None,
        'date_to': date_to or None,
        'total_results': paginator.count,
        'page': current_page_num,
        'page_size': page_size,
        'total_pages': paginator.num_pages,
        'has_next': page_obj.has_next() if hasattr(page_obj, 'has_next') else False,
        'has_previous': page_obj.has_previous() if hasattr(page_obj, 'has_previous') else False,
        'results': results,
    }
