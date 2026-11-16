"""
Public citizen-facing views and secure image delivery for Approved Media Gallery (apps.gallery).

Enforces the canonical public disclosure gate:
- Only approved, published gallery albums and photographs are visible to anonymous citizens.
- Draft, pending, withdrawn, and unapproved albums/photos strictly return 404 to anonymous users.
- Explicit language selection (?lang=mr|hi|en) with zero silent language fallback.
- Application-mediated binary image delivery (outside web root) with SHA-256 integrity verification.
"""

import logging
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse, FileResponse, HttpResponseServerError
from django.utils import timezone
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
    LANGUAGE_MARATHI,
    LANGUAGE_CHOICES,
    ALBUM_CATEGORY_CHOICES,
    STATUS_PUBLISHED,
)
from apps.gallery.storage import resolve_private_gallery_path
from apps.identity.permissions import is_super_admin, is_operator

logger = logging.getLogger('gramsetu.gallery')


def gallery_list_view(request):
    """
    Public listing of approved, published gallery albums.
    Supports:
    - ?lang=mr|hi|en (Default: mr)
    - ?category=infrastructure|gram_sabha|welfare|cultural|environment
    - ?allow_archived=0|1
    """
    lang = request.GET.get('lang', LANGUAGE_MARATHI)
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    category = request.GET.get('category', '').strip()
    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')

    # All published albums are eligible for public citizen viewing
    qs = GalleryAlbum.objects.public_eligible(allow_archived=allow_archived)

    if category and category in [c[0] for c in ALBUM_CATEGORY_CHOICES]:
        qs = qs.by_category(category)

    albums_data = []
    for album in qs.order_by('-event_date', '-created_at'):
        # Match requested language or gracefully fall back to the single primary translation
        trans = album.translations.filter(language_code=lang).first() or album.get_primary_translation() or album.translations.first()
        if not trans:
            continue
        is_fallback = (trans.language_code != lang)

        cover = album.cover_image
        cover_data = None
        if cover:
            img_url = cover.external_url if (cover.source_type == 'link' and cover.external_url) else f"/gallery/image/{cover.id}/"
            cover_data = {
                'id': str(cover.id),
                'source_type': cover.source_type,
                'image_url': img_url,
                'caption': cover.caption,
                'alt_text': cover.alt_text,
                'width_px': cover.width_px,
                'height_px': cover.height_px,
            }

        albums_data.append({
            'id': str(album.id),
            'slug': album.slug,
            'category': album.category,
            'category_display': album.get_category_display(),
            'event_date': album.event_date.isoformat() if album.event_date else None,
            'primary_language': album.primary_language,
            'title': trans.title,
            'description': trans.description,
            'photo_count': album.items.count(),
            'item_count': album.items.count(),
            'cover_image': cover_data,
            'language_code': trans.language_code,
            'is_fallback': is_fallback,
        })

    return JsonResponse({
        'language': lang,
        'category_filter': category or 'all',
        'count': len(albums_data),
        'results': albums_data,
    })


def gallery_detail_view(request, identifier):
    """
    Public detail view for a specific GalleryAlbum.
    Identifier can be either album UUID or slug.
    Enforces disclosure gate: unapproved/withdrawn albums return 404 to anonymous users.
    Gracefully falls back to primary Marathi record if translation is missing.
    """
    album = None
    try:
        album = GalleryAlbum.objects.get(id=identifier)
    except (GalleryAlbum.DoesNotExist, ValueError, ValidationError):
        try:
            album = GalleryAlbum.objects.get(slug=identifier)
        except GalleryAlbum.DoesNotExist:
            raise Http404("Gallery album not found.")

    allow_archived = request.GET.get('allow_archived', '0').lower() in ('1', 'true', 'yes')
    if not album.is_publicly_visible(allow_archived=allow_archived):
        if request.user.is_anonymous or not (is_super_admin(request.user) or is_operator(request.user)):
            raise Http404("Gallery album not found.")

    lang = request.GET.get('lang', LANGUAGE_MARATHI)
    valid_langs = [c[0] for c in LANGUAGE_CHOICES]
    if lang not in valid_langs:
        lang = LANGUAGE_MARATHI

    # Match requested language or gracefully fall back to the single primary translation
    trans = album.translations.filter(language_code=lang).first() or album.get_primary_translation() or album.translations.first()
    if not trans:
        raise Http404(f"No content available for album '{album.slug}'.")
    is_fallback = (trans.language_code != lang)

    photos_data = []
    for item in album.items.order_by('display_order', 'uploaded_at'):
        img_url = item.external_url if (item.source_type == 'link' and item.external_url) else f"/gallery/image/{item.id}/"
        photos_data.append({
            'id': str(item.id),
            'source_type': item.source_type,
            'image_url': img_url,
            'original_filename': item.original_filename,
            'mime_type': item.mime_type,
            'file_size_bytes': item.file_size_bytes,
            'width_px': item.width_px,
            'height_px': item.height_px,
            'is_cover_image': item.is_cover_image,
            'display_order': item.display_order,
            'caption': item.caption,
            'alt_text': item.alt_text,
        })

    return JsonResponse({
        'id': str(album.id),
        'slug': album.slug,
        'category': album.category,
        'category_display': album.get_category_display(),
        'event_date': album.event_date.isoformat() if album.event_date else None,
        'primary_language': album.primary_language,
        'language': trans.language_code,
        'status': album.status,
        'title': trans.title,
        'description': trans.description,
        'photo_count': len(photos_data),
        'photos': photos_data,
        'is_fallback': is_fallback,
    })


def gallery_image_serve_view(request, item_id):
    """
    Application-mediated secure image delivery for an approved GalleryItem.
    Enforces authorization check, verifies physical existence, checks SHA-256 integrity,
    and streams bytes via FileResponse.
    """
    try:
        item = GalleryItem.objects.select_related('album').get(id=item_id)
    except (GalleryItem.DoesNotExist, ValueError, ValidationError):
        raise Http404("Photograph not found.")

    # Authorization gate
    is_visible = item.album.is_publicly_visible(allow_archived=False)
    if not is_visible:
        if request.user.is_anonymous or not (is_super_admin(request.user) or is_operator(request.user)):
            raise Http404("Photograph not found.")

    if item.source_type == 'link' and item.external_url:
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(item.external_url)

    # Resolve internal storage path
    try:
        resolved_path = resolve_private_gallery_path(item.storage_path)
    except Exception as e:
        logger.error(f"Failed to resolve path for item {item.id}: {e}")
        raise Http404("Photograph not found.")

    if not resolved_path.exists() or not resolved_path.is_file():
        logger.critical(f"STORAGE DRIFT: Physical file missing on disk for GalleryItem {item.id} (path: {item.storage_path}).")
        raise Http404("Photograph file is not accessible.")

    # Cryptographic integrity check
    if not item.verify_integrity():
        logger.critical(f"SECURITY INTEGRITY FAILURE: SHA-256 mismatch for GalleryItem {item.id}.")
        return HttpResponseServerError("Photograph integrity verification failed.")

    # Stream the file
    response = FileResponse(open(resolved_path, 'rb'), content_type=item.mime_type)
    response['Content-Length'] = item.file_size_bytes
    if is_visible:
        response['Cache-Control'] = 'public, max-age=86400'
    else:
        response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'

    return response
