"""
Real-time search index synchronization signals for apps.search.

Automatically updates SearchDocumentIndex entries whenever domain models,
translations, or publication events change.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.search.models import (
    TYPE_PAGE,
    TYPE_NOTICE,
    TYPE_DOCUMENT,
    TYPE_EVENT,
    TYPE_SCHEME,
    TYPE_GALLERY,
)
from apps.search.services import (
    sync_page_translation,
    sync_notice_translation,
    sync_document_translation,
    sync_event,
    sync_scheme_translation,
    sync_gallery_album,
    remove_target_from_index,
)


def connect_search_signals():
    """
    Connects post_save and post_delete receivers to all domain models.
    """
    try:
        from apps.content.models import Page, PageTranslation
        from apps.notices.models import Notice, NoticeTranslation
        from apps.documents.models import Document, DocumentTranslation
        from apps.events.models import PanchayatEvent, EventTranslation
        from apps.schemes.models import WelfareScheme, SchemeTranslation
        from apps.gallery.models import GalleryAlbum, AlbumTranslation
        from apps.governance.models import PublicationEvent

        # 1. Pages
        @receiver(post_save, sender=PageTranslation, weak=False)
        def on_page_translation_save(sender, instance, **kwargs):
            sync_page_translation(instance)

        @receiver(post_delete, sender=Page, weak=False)
        def on_page_delete(sender, instance, **kwargs):
            remove_target_from_index(TYPE_PAGE, instance.id)

        # 2. Notices
        @receiver(post_save, sender=NoticeTranslation, weak=False)
        def on_notice_translation_save(sender, instance, **kwargs):
            sync_notice_translation(instance)

        @receiver(post_delete, sender=Notice, weak=False)
        def on_notice_delete(sender, instance, **kwargs):
            remove_target_from_index(TYPE_NOTICE, instance.id)

        # 3. Documents
        @receiver(post_save, sender=DocumentTranslation, weak=False)
        def on_document_translation_save(sender, instance, **kwargs):
            sync_document_translation(instance)

        @receiver(post_delete, sender=Document, weak=False)
        def on_document_delete(sender, instance, **kwargs):
            remove_target_from_index(TYPE_DOCUMENT, instance.id)

        # 4. Events
        @receiver(post_save, sender=PanchayatEvent, weak=False)
        def on_event_save(sender, instance, **kwargs):
            sync_event(instance)

        @receiver(post_save, sender=EventTranslation, weak=False)
        def on_event_translation_save(sender, instance, **kwargs):
            sync_event(instance.event)

        @receiver(post_delete, sender=PanchayatEvent, weak=False)
        def on_event_delete(sender, instance, **kwargs):
            remove_target_from_index(TYPE_EVENT, instance.id)

        # 5. Schemes
        @receiver(post_save, sender=SchemeTranslation, weak=False)
        def on_scheme_translation_save(sender, instance, **kwargs):
            sync_scheme_translation(instance)

        @receiver(post_delete, sender=WelfareScheme, weak=False)
        def on_scheme_delete(sender, instance, **kwargs):
            remove_target_from_index(TYPE_SCHEME, instance.id)

        # 6. Media Gallery
        @receiver(post_save, sender=GalleryAlbum, weak=False)
        def on_gallery_album_save(sender, instance, **kwargs):
            sync_gallery_album(instance)

        @receiver(post_save, sender=AlbumTranslation, weak=False)
        def on_album_translation_save(sender, instance, **kwargs):
            sync_gallery_album(instance.album)

        @receiver(post_delete, sender=GalleryAlbum, weak=False)
        def on_gallery_album_delete(sender, instance, **kwargs):
            remove_target_from_index(TYPE_GALLERY, instance.id)

        # 7. Governance Publication Events (publish, withdraw, archive)
        @receiver(post_save, sender=PublicationEvent, weak=False)
        def on_publication_event_save(sender, instance, **kwargs):
            target_type = instance.target_content_type
            if target_type == 'pagetranslation':
                try:
                    pt = PageTranslation.objects.get(id=instance.target_id)
                    sync_page_translation(pt)
                except PageTranslation.DoesNotExist:
                    pass
            elif target_type == 'noticetranslation':
                try:
                    nt = NoticeTranslation.objects.get(id=instance.target_id)
                    sync_notice_translation(nt)
                except NoticeTranslation.DoesNotExist:
                    pass
            elif target_type == 'documenttranslation':
                try:
                    dt = DocumentTranslation.objects.get(id=instance.target_id)
                    sync_document_translation(dt)
                except DocumentTranslation.DoesNotExist:
                    pass
            elif target_type == 'panchayatevent':
                try:
                    ev = PanchayatEvent.objects.get(id=instance.target_id)
                    sync_event(ev)
                except PanchayatEvent.DoesNotExist:
                    pass
            elif target_type == 'schemetranslation':
                try:
                    st = SchemeTranslation.objects.get(id=instance.target_id)
                    sync_scheme_translation(st)
                except SchemeTranslation.DoesNotExist:
                    pass
            elif target_type == 'galleryalbum':
                try:
                    alb = GalleryAlbum.objects.get(id=instance.target_id)
                    sync_gallery_album(alb)
                except GalleryAlbum.DoesNotExist:
                    pass

    except (ImportError, RuntimeError):
        pass
