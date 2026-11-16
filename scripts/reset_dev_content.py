#!/usr/bin/env python3
"""
GramSetu Development Content Data Reset Script

Safely cleans out development/testing content records across:
- Notices & Announcements (Notice, NoticeTranslation, NoticeRevision)
- Disclosed Documents (Document, DocumentTranslation, DocumentVersion)
- Panchayat Events & Meetings (PanchayatEvent, EventTranslation)
- Welfare Schemes (WelfareScheme, SchemeTranslation, SchemeRevision)
- Photo Gallery (GalleryAlbum, AlbumTranslation, GalleryItem)
- Non-system Pages (Page, PageTranslation, PageRevision)
- Debug/Test temporary user accounts (preserves statutory Super Admin and Operator)

Strictly Preserves:
- Super Admin: 'local.admin@gramsetu.gov.in'
- Operator: 'local.operator@gramsetu.gov.in'
- Authentication passwords, MFA devices, TOTP keys, role assignments
- Database schema, table structures, and migration history
- System configurations
"""

import os
import sys
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.db import transaction
from apps.identity.models import User, RoleAssignment
from apps.notices.models import Notice, NoticeTranslation, NoticeRevision
from apps.documents.models import Document, DocumentTranslation, DocumentVersion
from apps.events.models import PanchayatEvent, EventTranslation
from apps.schemes.models import WelfareScheme, SchemeTranslation, SchemeRevision
from apps.gallery.models import GalleryAlbum, AlbumTranslation, GalleryItem
from apps.content.models import Page, PageTranslation, PageRevision
from apps.governance.models import ApprovalRecord, RejectionRecord, PublicationEvent
from apps.search.models import SearchDocumentIndex
from apps.search.services import rebuild_search_index

PRESERVED_EMAILS = {
    'local.admin@gramsetu.gov.in',
    'local.operator@gramsetu.gov.in',
}

def execute_reset(dry_run=False):
    print(f">>> [GramSetu Content Reset] Starting {'DRY RUN' if dry_run else 'EXECUTION'}...")

    # 1. Verify preserved accounts exist
    for email in PRESERVED_EMAILS:
        user = User.objects.filter(email=email).first()
        if not user:
            sys.exit(f"ABORT: Required preserved account '{email}' does not exist in database!")
        print(f"PASS: Verified preserved user '{email}' (Active: {user.is_active}, Role: {getattr(getattr(user, 'role_assignment', None), 'role', None)})")

    with transaction.atomic():
        # Counts before
        notice_count = Notice.objects.count()
        doc_count = Document.objects.count()
        event_count = PanchayatEvent.objects.count()
        scheme_count = WelfareScheme.objects.count()
        gallery_count = GalleryAlbum.objects.count()
        page_count = Page.objects.filter(is_system_page=False).count()

        # Delete Content Records
        print("\n--- Resetting Content Domains ---")
        
        # Gallery
        GalleryAlbum.objects.update(status='draft', is_published=False)
        items_deleted, _ = GalleryItem.objects.all().delete()
        alb_trans_deleted, _ = AlbumTranslation.objects.all().delete()
        albums_deleted, _ = GalleryAlbum.objects.all().delete()
        print(f"Gallery: {albums_deleted} albums, {alb_trans_deleted} translations, {items_deleted} photos removed.")

        # Schemes
        SchemeRevision.objects.update(editorial_status='draft')
        SchemeTranslation.objects.update(status='draft', current_approved_revision=None)
        sch_rev_deleted, _ = SchemeRevision.objects.all().delete()
        sch_trans_deleted, _ = SchemeTranslation.objects.all().delete()
        schemes_deleted, _ = WelfareScheme.objects.all().delete()
        print(f"Schemes: {schemes_deleted} schemes, {sch_trans_deleted} translations, {sch_rev_deleted} revisions removed.")

        # Events
        PanchayatEvent.objects.update(status='draft', is_published=False)
        ev_trans_deleted, _ = EventTranslation.objects.all().delete()
        events_deleted, _ = PanchayatEvent.objects.all().delete()
        print(f"Events: {events_deleted} events, {ev_trans_deleted} translations removed.")

        # Documents
        DocumentVersion.objects.update(disclosure_status='draft')
        DocumentTranslation.objects.update(status='draft', current_version=None, current_publication_event=None)
        doc_ver_deleted, _ = DocumentVersion.objects.all().delete()
        doc_trans_deleted, _ = DocumentTranslation.objects.all().delete()
        docs_deleted, _ = Document.objects.all().delete()
        print(f"Documents: {docs_deleted} documents, {doc_trans_deleted} translations, {doc_ver_deleted} versions removed.")

        # Notices
        NoticeRevision.objects.update(editorial_status='draft')
        NoticeTranslation.objects.update(status='draft', current_approved_revision=None)
        not_rev_deleted, _ = NoticeRevision.objects.all().delete()
        not_trans_deleted, _ = NoticeTranslation.objects.all().delete()
        notices_deleted, _ = Notice.objects.all().delete()
        print(f"Notices: {notices_deleted} notices, {not_trans_deleted} translations, {not_rev_deleted} revisions removed.")

        # Non-system pages
        PageRevision.objects.filter(translation__page__is_system_page=False).update(editorial_status='draft')
        PageTranslation.objects.filter(page__is_system_page=False).update(status='draft', current_approved_revision=None)
        page_rev_deleted, _ = PageRevision.objects.filter(translation__page__is_system_page=False).delete()
        page_trans_deleted, _ = PageTranslation.objects.filter(page__is_system_page=False).delete()
        pages_deleted, _ = Page.objects.filter(is_system_page=False).delete()
        print(f"Pages: {pages_deleted} custom pages removed (system statutory pages preserved).")

        # Search Document Index
        search_entries_deleted, _ = SearchDocumentIndex.objects.all().delete()
        print(f"Search Index: {search_entries_deleted} search projection entries cleared.")

        # Cleanup extra debug users
        extra_users = User.objects.exclude(email__in=PRESERVED_EMAILS)
        extra_count = extra_users.count()
        extra_emails = [u.email for u in extra_users]
        extra_users.delete()
        print(f"Debug Users: Removed {extra_count} temporary users: {extra_emails}")

        # Clean orphaned physical files in private storage (only on non-dry-run)
        private_docs_dir = BASE_DIR / 'private_docs'
        private_gallery_dir = BASE_DIR / 'private_media' / 'gallery'
        cleaned_docs = 0
        cleaned_gallery = 0
        if not dry_run:
            if private_docs_dir.exists():
                for f in private_docs_dir.glob('*.dat'):
                    try:
                        f.unlink()
                        cleaned_docs += 1
                    except Exception as e:
                        print(f"Warning: could not delete {f}: {e}")
            if private_gallery_dir.exists():
                for f in private_gallery_dir.glob('*.dat'):
                    try:
                        f.unlink()
                        cleaned_gallery += 1
                    except Exception as e:
                        print(f"Warning: could not delete {f}: {e}")
        else:
            cleaned_docs = len(list(private_docs_dir.glob('*.dat'))) if private_docs_dir.exists() else 0
            cleaned_gallery = len(list(private_gallery_dir.glob('*.dat'))) if private_gallery_dir.exists() else 0

        print(f"Storage Cleanup: {cleaned_docs} document blobs and {cleaned_gallery} gallery blobs {'would be' if dry_run else ''} cleaned from private storage.")

        if dry_run:
            print("\nDRY RUN: Rolling back transaction (no changes made to database).")
            transaction.set_rollback(True)
        else:
            print("\nSUCCESS: Transaction committed. Development content clean reset complete.")
            rebuilt_count = rebuild_search_index()
            print(f"Search Index Rebuild: {rebuilt_count} remaining eligible entries indexed.")

    # Post-check users (only assert on actual execution)
    remaining_users = list(User.objects.values_list('email', flat=True))
    print(f"\nFinal User Accounts: {remaining_users}")
    if not dry_run:
        assert set(remaining_users) == PRESERVED_EMAILS, f"Mismatch in preserved accounts: {remaining_users}"
        print("PASS: Both Super Admin and Operator accounts are strictly preserved.")
    else:
        print("PASS: Dry run completed cleanly.")

if __name__ == '__main__':
    dry = '--dry-run' in sys.argv
    execute_reset(dry_run=dry)
