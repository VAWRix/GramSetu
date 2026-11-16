"""
Comprehensive domain, storage, governance, view, and admin tests for apps.gallery.

Verifies:
- GalleryAlbum model constraints, UUIDv7 PK, ASCII slug, category choices, status choices, and deterministic SHA-256 hash.
- AlbumTranslation explicit multilingual entities (mr statutory primary, hi, en) and strict zero-silent-fallback.
- GalleryItem photograph metadata, 15 MB cap, permitted MIME types, magic byte validation, mandatory Marathi alt-text.
- Private decoupled storage utilities, path traversal defense, and physical SHA-256 integrity verification.
- Separation of duties in publication approval (authors cannot approve their own gallery albums).
- Governance publishing workflows: submit, approve & publish, reject, withdraw, and archive.
- Public views and disclosure gate (draft, pending, withdrawn albums/photos return 404 to anonymous citizens).
- Application-mediated binary image streaming (outside web root) with SHA-256 integrity verification and tampering halt.
- Django Admin interface permissions, intermediate action forms, and anti-self-approval enforcement.
"""

import hashlib
import io
import os
from pathlib import Path
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError, SuspiciousOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.identity.models import (
    User,
    RoleAssignment,
    ROLE_SUPER_ADMIN,
    ROLE_OPERATOR,
)
from apps.governance.models import (
    ApprovalRecord,
    RejectionRecord,
    PublicationEvent,
    EVENT_INITIAL_PUBLISH,
    EVENT_UPDATE_PUBLISH,
    EVENT_WITHDRAWAL,
    EVENT_ARCHIVAL,
)
from apps.governance.services import (
    submit_gallery_album_for_approval,
    approve_and_publish_gallery_album,
    reject_gallery_album,
    withdraw_gallery_album,
    archive_gallery_album,
)
from apps.gallery.models import (
    GalleryAlbum,
    AlbumTranslation,
    GalleryItem,
    CATEGORY_INFRASTRUCTURE,
    CATEGORY_GRAM_SABHA,
    CATEGORY_WELFARE,
    CATEGORY_CULTURAL,
    CATEGORY_ENVIRONMENT,
    LANGUAGE_MARATHI,
    LANGUAGE_HINDI,
    LANGUAGE_ENGLISH,
    STATUS_DRAFT,
    STATUS_PENDING_APPROVAL,
    STATUS_APPROVED,
    STATUS_PUBLISHED,
    STATUS_WITHDRAWN,
    STATUS_ARCHIVED,
)
from apps.gallery.storage import (
    save_gallery_image,
    sanitize_filename,
    resolve_private_gallery_path,
    verify_gallery_image_integrity,
    get_private_gallery_dir,
    detect_image_mime,
    validate_image_file,
    MAX_IMAGE_SIZE_BYTES,
)
from apps.gallery.admin import (
    GalleryAlbumAdmin,
    GalleryItemAdmin,
    GalleryItemCreationForm,
    GalleryItemChangeForm,
)


class GalleryBaseTestCase(TestCase):
    """
    Base test fixture establishing users and image file creation helpers.
    """

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email='admin@gramsetu.in',
            full_name='Super Administrator',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.super_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )

        self.operator = User.objects.create_user(
            email='operator@gramsetu.in',
            full_name='Gram Panchayat Operator',
            password='OperatorPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.operator,
            role=ROLE_OPERATOR,
            assigned_by=self.super_admin,
        )

        self.second_admin = User.objects.create_user(
            email='second_admin@gramsetu.in',
            full_name='Second Administrator',
            password='AdminPassword123!',
            is_staff=True,
        )
        RoleAssignment.objects.create(
            user=self.second_admin,
            role=ROLE_SUPER_ADMIN,
            assigned_by=self.super_admin,
        )

        self.citizen = User.objects.create_user(
            email='citizen@gramsetu.in',
            full_name='Ordinary Citizen',
            password='CitizenPassword123!',
            is_staff=False,
        )

        self.created_files = []

    def create_dummy_jpeg(self, filename="photo.jpg", content=None):
        """
        Creates a valid JPEG binary file in private gallery storage.
        """
        if content is None:
            # Valid JPEG magic bytes header (\xff\xd8\xff) followed by dummy payload
            content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00' + (b'\xab' * 128)

        uploaded = SimpleUploadedFile(filename, content, content_type="image/jpeg")
        storage_filename, clean_name, file_size, mime, checksum = save_gallery_image(uploaded, filename)
        file_path = get_private_gallery_dir() / storage_filename
        self.created_files.append(file_path)
        return storage_filename, clean_name, file_size, mime, checksum

    def tearDown(self):
        # Clean up all created image files from disk
        for fp in self.created_files:
            try:
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass


class GalleryModelAndStorageTests(GalleryBaseTestCase):
    """
    Tests model validation, check constraints, hash computation, and storage security.
    """

    def test_album_creation_and_defaults(self):
        album = GalleryAlbum.objects.create(
            slug='water-project-2026',
            category=CATEGORY_INFRASTRUCTURE,
            created_by=self.operator,
        )
        self.assertIsNotNone(album.id)
        self.assertEqual(album.status, STATUS_DRAFT)
        self.assertFalse(album.is_published)
        self.assertFalse(album.is_publicly_visible())

    def test_album_invalid_category_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GalleryAlbum.objects.create(
                    slug='invalid-category-album',
                    category='unsupported_cat',
                    created_by=self.operator,
                )

    def test_album_clean_draft_cannot_be_published(self):
        album = GalleryAlbum(
            slug='draft-published-conflict',
            category=CATEGORY_INFRASTRUCTURE,
            created_by=self.operator,
            status=STATUS_DRAFT,
            is_published=True,
        )
        with self.assertRaises(ValidationError) as ctx:
            album.clean()
        self.assertIn("Draft albums cannot be marked as published", str(ctx.exception))

    def test_album_translation_uniqueness_and_constraint(self):
        album = GalleryAlbum.objects.create(
            slug='panchayat-hall-2026',
            category=CATEGORY_INFRASTRUCTURE,
            created_by=self.operator,
        )
        AlbumTranslation.objects.create(
            album=album,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामपंचायत नवीन सभागृह',
            description='नवीन प्रशासकीय इमारतीचे छायाचित्र दालन.',
        )

        # Duplicate language for same album should violate unique constraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AlbumTranslation.objects.create(
                    album=album,
                    language_code=LANGUAGE_MARATHI,
                    title='दुसरे शीर्षक',
                )

        # Invalid language code should violate check constraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AlbumTranslation.objects.create(
                    album=album,
                    language_code='fr',
                    title='Titre en français',
                )

    def test_gallery_item_mandatory_alt_text_mr(self):
        album = GalleryAlbum.objects.create(
            slug='hall-photos',
            category=CATEGORY_INFRASTRUCTURE,
            created_by=self.operator,
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()

        # Item with empty alt_text_mr should fail clean()
        item = GalleryItem(
            album=album,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='',  # Missing
            uploaded_by=self.operator,
        )
        with self.assertRaises(ValidationError) as ctx:
            item.clean()
        self.assertIn("alt_text_mr", str(ctx.exception))

    def test_storage_magic_byte_validation(self):
        # Valid JPEG magic bytes (\xff\xd8\xff)
        jpeg_header = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        self.assertEqual(detect_image_mime(jpeg_header), 'image/jpeg')

        # Valid PNG magic bytes (\x89PNG\r\n\x1a\n)
        png_header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
        self.assertEqual(detect_image_mime(png_header), 'image/png')

        # Valid WebP magic bytes (RIFF....WEBP)
        webp_header = b'RIFF\x24\x00\x00\x00WEBPVP8 '
        self.assertEqual(detect_image_mime(webp_header), 'image/webp')

        # Invalid text or executable
        fake_header = b'MZ\x90\x00\x03\x00\x00\x00'
        self.assertIsNone(detect_image_mime(fake_header))

        fake_file = SimpleUploadedFile("fake.jpg", b"This is not a real JPEG image file at all.")
        with self.assertRaises(ValidationError) as ctx:
            validate_image_file(fake_file, "fake.jpg")
        self.assertIn("File header verification failed", str(ctx.exception))

    def test_storage_file_size_cap_validation(self):
        oversized = SimpleUploadedFile("huge.jpg", b"X" * (MAX_IMAGE_SIZE_BYTES + 1024))
        with self.assertRaises(ValidationError) as ctx:
            validate_image_file(oversized, "huge.jpg")
        self.assertIn("exceeds maximum limit of 15 MB", str(ctx.exception))

    def test_storage_path_traversal_defense(self):
        with self.assertRaises(SuspiciousOperation):
            resolve_private_gallery_path("")

        # Should strip directory tokens safely or raise SuspiciousOperation if attempting escape
        resolved = resolve_private_gallery_path("../../etc/passwd")
        # In our implementation, os.path.basename is extracted if traversal characters present
        self.assertTrue(str(resolved).startswith(str(get_private_gallery_dir())))
        self.assertEqual(resolved.name, "passwd")

    def test_album_calculate_hash_deterministic(self):
        album = GalleryAlbum.objects.create(
            slug='solar-pumps-2026',
            category=CATEGORY_WELFARE,
            created_by=self.operator,
        )
        AlbumTranslation.objects.create(
            album=album,
            language_code=LANGUAGE_MARATHI,
            title='सौर कृषी पंप वाटप',
            description='शेतकऱ्यांना सौर पंपांचे वाटप करण्यात आले.',
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        item = GalleryItem.objects.create(
            album=album,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='शेतकऱ्यांना सौर पंप वाटप करताना सरपंच',
            uploaded_by=self.operator,
        )

        h1 = album.calculate_hash()
        h2 = album.calculate_hash()
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

        # Modifying item description or order changes hash
        item.alt_text_mr = 'नवीन वर्णनात्मक मजकूर'
        item.save()
        h3 = album.calculate_hash()
        self.assertNotEqual(h1, h3)


class GalleryGovernanceTests(GalleryBaseTestCase):
    """
    Tests governance workflow services: submission, approval, rejection, withdrawal, archival.
    """

    def setUp(self):
        super().setUp()
        self.album = GalleryAlbum.objects.create(
            slug='water-conservation-2026',
            category=CATEGORY_ENVIRONMENT,
            created_by=self.operator,
        )
        self.trans_mr = AlbumTranslation.objects.create(
            album=self.album,
            language_code=LANGUAGE_MARATHI,
            title='जलसंधारण मोहीम २०२६',
            description='गावातील नाला खोलीकरण व बंधारे बांधकाम छायाचित्रे.',
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        self.item = GalleryItem.objects.create(
            album=self.album,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='बंधाऱ्याचे बांधकाम पूर्ण झालेले छायाचित्र',
            uploaded_by=self.operator,
        )

    def test_submit_for_approval_success(self):
        submitted = submit_gallery_album_for_approval(self.album.id, self.operator)
        self.assertEqual(submitted.status, STATUS_PENDING_APPROVAL)

    def test_submit_for_approval_english_primary_success(self):
        album_en = GalleryAlbum.objects.create(
            slug='english-only-album',
            category=CATEGORY_CULTURAL,
            primary_language=LANGUAGE_ENGLISH,
            created_by=self.operator,
        )
        AlbumTranslation.objects.create(
            album=album_en,
            language_code=LANGUAGE_ENGLISH,
            title='English Title Only',
            description='English Description Only',
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        GalleryItem.objects.create(
            album=album_en,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='English photo description for screen reader',
            uploaded_by=self.operator,
        )

        submitted = submit_gallery_album_for_approval(album_en.id, self.operator)
        self.assertEqual(submitted.status, STATUS_PENDING_APPROVAL)

    def test_submit_for_approval_requires_primary_translation(self):
        album_no_title = GalleryAlbum.objects.create(
            slug='no-title-album',
            category=CATEGORY_CULTURAL,
            primary_language=LANGUAGE_MARATHI,
            created_by=self.operator,
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        GalleryItem.objects.create(
            album=album_no_title,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='Sample photo description',
            uploaded_by=self.operator,
        )

        with self.assertRaises(ValidationError) as ctx:
            submit_gallery_album_for_approval(album_no_title.id, self.operator)
        self.assertIn("primary title", str(ctx.exception).lower())

    def test_submit_for_approval_requires_photographs(self):
        empty_album = GalleryAlbum.objects.create(
            slug='empty-photo-album',
            category=CATEGORY_CULTURAL,
            created_by=self.operator,
        )
        AlbumTranslation.objects.create(
            album=empty_album,
            language_code=LANGUAGE_MARATHI,
            title='रिकामे दालन',
        )
        with self.assertRaises(ValidationError) as ctx:
            submit_gallery_album_for_approval(empty_album.id, self.operator)
        self.assertIn("at least one photograph", str(ctx.exception))

    def test_approve_and_publish_success(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)

        # Super admin approves (different user than operator creator)
        album, approval, pub_event = approve_and_publish_gallery_album(
            self.album.id,
            self.super_admin,
            notes="Formal statutory approval by BDO/SuperAdmin",
        )

        self.assertEqual(album.status, STATUS_PUBLISHED)
        self.assertTrue(album.is_published)
        self.assertTrue(album.is_publicly_visible())

        # Check ApprovalRecord created
        self.assertIsInstance(approval, ApprovalRecord)
        self.assertEqual(approval.target_id, self.album.id)
        self.assertEqual(approval.approved_by, self.super_admin)
        self.assertFalse(approval.is_self_approval)

        # Check PublicationEvent created
        self.assertIsInstance(pub_event, PublicationEvent)
        self.assertEqual(pub_event.target_id, self.album.id)
        self.assertEqual(pub_event.event_type, EVENT_INITIAL_PUBLISH)

        # Check member photograph is stamped with approval
        self.item.refresh_from_db()
        self.assertEqual(self.item.approved_by, self.super_admin)
        self.assertIsNotNone(self.item.approved_at)

    def test_approve_and_publish_anti_self_approval(self):
        # Album created by super_admin
        admin_album = GalleryAlbum.objects.create(
            slug='admin-created-album',
            category=CATEGORY_GRAM_SABHA,
            created_by=self.super_admin,
        )
        AlbumTranslation.objects.create(
            album=admin_album,
            language_code=LANGUAGE_MARATHI,
            title='ग्रामसभा २०२६ छायाचित्रे',
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        GalleryItem.objects.create(
            album=admin_album,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='ग्रामसभा सभासद उपस्थिती',
            uploaded_by=self.super_admin,
        )

        submit_gallery_album_for_approval(admin_album.id, self.super_admin)

        # Super admin attempting to approve their own created album must fail
        with self.assertRaises(ValidationError) as ctx:
            approve_and_publish_gallery_album(admin_album.id, self.super_admin)
        self.assertIn("Separation of duties violation", str(ctx.exception))

        # A second administrator CAN approve it
        album, approval, _ = approve_and_publish_gallery_album(admin_album.id, self.second_admin)
        self.assertEqual(album.status, STATUS_PUBLISHED)
        self.assertFalse(approval.is_self_approval)

    def test_approve_and_publish_integrity_failure_blocks_approval(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)

        # Tamper with file on disk (corrupt bytes)
        disk_path = get_private_gallery_dir() / self.item.storage_path
        with open(disk_path, 'wb') as f:
            f.write(b'\xff\xd8\xff\xe0_tampered_payload_that_invalidates_sha256')

        with self.assertRaises(ValidationError) as ctx:
            approve_and_publish_gallery_album(self.album.id, self.super_admin)
        self.assertIn("Integrity verification failed", str(ctx.exception))

    def test_reject_gallery_album(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)

        # Reject with short rationale fails (< 10 chars)
        with self.assertRaises(ValidationError) as ctx:
            reject_gallery_album(self.album.id, self.super_admin, "Too bad")
        self.assertIn("at least 10 non-whitespace characters", str(ctx.exception))

        # Valid rejection
        album, rejection = reject_gallery_album(
            self.album.id,
            self.super_admin,
            "Photograph quality does not meet resolution standards. Please re-upload.",
        )
        self.assertEqual(album.status, STATUS_DRAFT)
        self.assertIsInstance(rejection, RejectionRecord)
        self.assertEqual(rejection.rejected_by, self.super_admin)

    def test_withdraw_gallery_album(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        # Short justification fails
        with self.assertRaises(ValidationError) as ctx:
            withdraw_gallery_album(self.album.id, self.super_admin, "Withdraw")
        self.assertIn("at least 10 non-whitespace characters", str(ctx.exception))

        # Valid withdrawal immediately severs citizen visibility
        album, pub_event = withdraw_gallery_album(
            self.album.id,
            self.super_admin,
            "Statutory withdrawal due to pending inquiry into contractor work.",
        )
        self.assertEqual(album.status, STATUS_WITHDRAWN)
        self.assertFalse(album.is_published)
        self.assertFalse(album.is_publicly_visible())
        self.assertEqual(pub_event.event_type, EVENT_WITHDRAWAL)

    def test_archive_gallery_album(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        album, pub_event = archive_gallery_album(
            self.album.id,
            self.super_admin,
            justification="Annual statutory record archival",
        )
        self.assertEqual(album.status, STATUS_ARCHIVED)
        self.assertEqual(pub_event.event_type, EVENT_ARCHIVAL)


class GalleryPublicViewsTests(GalleryBaseTestCase):
    """
    Tests citizen-facing views, disclosure gate, and secure binary streaming.
    """

    def setUp(self):
        super().setUp()
        self.album = GalleryAlbum.objects.create(
            slug='school-renovation-2026',
            category=CATEGORY_INFRASTRUCTURE,
            created_by=self.operator,
        )
        self.trans_mr = AlbumTranslation.objects.create(
            album=self.album,
            language_code=LANGUAGE_MARATHI,
            title='जिल्हा परिषद शाळा दुरुस्ती',
            description='शाळा इमारतीचे नूतनीकरण छायाचित्रे.',
        )
        self.trans_en = AlbumTranslation.objects.create(
            album=self.album,
            language_code=LANGUAGE_ENGLISH,
            title='Zilla Parishad School Renovation',
            description='Photographs of school building renovation works.',
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        self.item = GalleryItem.objects.create(
            album=self.album,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            caption_mr='शाळेची नवीन रंगरंगोटी',
            caption_en='New painting of school building',
            alt_text_mr='दुरुस्ती पूर्ण झालेल्या शाळेची नवीन इमारत',
            alt_text_en='Renovated school building with new paint',
            is_cover_image=True,
            uploaded_by=self.operator,
        )

    def test_public_listing_only_shows_published(self):
        # 1. While in draft, listing returns 0 results
        resp = self.client.get(reverse('gallery:album_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 0)

        # 2. Publish album
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        # 3. Now listing returns the album
        resp = self.client.get(reverse('gallery:album_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['slug'], 'school-renovation-2026')
        self.assertEqual(data['results'][0]['title'], 'जिल्हा परिषद शाळा दुरुस्ती')
        self.assertIsNotNone(data['results'][0]['cover_image'])

    def test_public_listing_category_filtering(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        # Match category
        resp = self.client.get(reverse('gallery:album_list') + f'?category={CATEGORY_INFRASTRUCTURE}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)

        # Different category
        resp = self.client.get(reverse('gallery:album_list') + f'?category={CATEGORY_CULTURAL}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 0)

    def test_public_listing_language_matching_and_fallback(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        # Marathi query: matches explicit Marathi translation
        resp_mr = self.client.get(reverse('gallery:album_list') + '?lang=mr')
        self.assertEqual(resp_mr.json()['count'], 1)
        self.assertEqual(resp_mr.json()['results'][0]['title'], 'जिल्हा परिषद शाळा दुरुस्ती')
        self.assertFalse(resp_mr.json()['results'][0]['is_fallback'])

        # English query: matches explicit English translation
        resp_en = self.client.get(reverse('gallery:album_list') + '?lang=en')
        self.assertEqual(resp_en.json()['count'], 1)
        self.assertEqual(resp_en.json()['results'][0]['title'], 'Zilla Parishad School Renovation')
        self.assertFalse(resp_en.json()['results'][0]['is_fallback'])

        # Hindi query: falls back to primary Marathi title rather than blank or empty
        resp_hi = self.client.get(reverse('gallery:album_list') + '?lang=hi')
        self.assertEqual(resp_hi.json()['count'], 1)
        self.assertEqual(resp_hi.json()['results'][0]['title'], 'जिल्हा परिषद शाळा दुरुस्ती')
        self.assertTrue(resp_hi.json()['results'][0]['is_fallback'])

    def test_public_detail_view_anonymous_404_for_unapproved(self):
        # Anonymous citizen gets 404 for draft album
        resp = self.client.get(reverse('gallery:album_detail', args=[self.album.slug]))
        self.assertEqual(resp.status_code, 404)

        # Also 404 by UUID identifier
        resp_uuid = self.client.get(reverse('gallery:album_detail', args=[self.album.id]))
        self.assertEqual(resp_uuid.status_code, 404)

        # Staff can preview draft
        self.client.force_login(self.operator)
        resp_staff = self.client.get(reverse('gallery:album_detail', args=[self.album.slug]))
        self.assertEqual(resp_staff.status_code, 200)

    def test_public_detail_view_published_success(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        resp = self.client.get(reverse('gallery:album_detail', args=[self.album.slug]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['slug'], 'school-renovation-2026')
        self.assertEqual(data['photo_count'], 1)
        photo = data['photos'][0]
        self.assertEqual(photo['caption'], 'शाळेची नवीन रंगरंगोटी')
        self.assertEqual(photo['alt_text'], 'दुरुस्ती पूर्ण झालेल्या शाळेची नवीन इमारत')

    def test_public_detail_view_fallback_to_primary_language(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        # Hindi translation does not exist -> gracefully falls back to primary Marathi content with 200 OK
        resp = self.client.get(reverse('gallery:album_detail', args=[self.album.slug]) + '?lang=hi')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['title'], 'जिल्हा परिषद शाळा दुरुस्ती')
        self.assertTrue(data['is_fallback'])

    def test_image_serve_view_success(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        url = reverse('gallery:image_serve', args=[self.item.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/jpeg')
        self.assertIn('public', resp['Cache-Control'])
        content = b"".join(resp.streaming_content)
        self.assertEqual(hashlib.sha256(content).hexdigest(), self.item.checksum_sha256)

    def test_image_serve_view_without_trailing_slash(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        url = f"/gallery/image/{self.item.id}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/jpeg')

    def test_unsupported_google_drive_folder_link_rejected(self):
        from apps.gallery.storage import convert_and_validate_image_url
        folder_url = 'https://drive.google.com/drive/folders/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs'
        converted, err = convert_and_validate_image_url(folder_url)
        self.assertIsNotNone(err)
        self.assertIn("folder", err.lower())

        docs_url = 'https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs/edit'
        converted, err = convert_and_validate_image_url(docs_url)
        self.assertIsNotNone(err)
        self.assertIn("docs", err.lower())

    def test_image_serve_view_anonymous_404_when_album_unapproved(self):
        # Album is in draft
        url = reverse('gallery:image_serve', args=[self.item.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

        # Staff can view/preview image
        self.client.force_login(self.operator)
        resp_staff = self.client.get(url)
        self.assertEqual(resp_staff.status_code, 200)

    def test_image_serve_view_corrupted_hash_returns_500(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        # Corrupt file on disk
        disk_path = get_private_gallery_dir() / self.item.storage_path
        with open(disk_path, 'wb') as f:
            f.write(b'\xff\xd8\xffcorrupted_image_payload')

        url = reverse('gallery:image_serve', args=[self.item.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 500)
        self.assertIn(b"integrity verification failed", resp.content)

    def test_image_serve_view_missing_file_returns_404(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        # Delete physical file on disk (simulating storage drift)
        disk_path = get_private_gallery_dir() / self.item.storage_path
        if disk_path.exists():
            disk_path.unlink()

        url = reverse('gallery:image_serve', args=[self.item.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class GalleryAdminTests(GalleryBaseTestCase):
    """
    Tests Django Admin permissions, inline photo creation, and anti-self-approval enforcement.
    """

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.album_admin = GalleryAlbumAdmin(GalleryAlbum, self.site)
        self.item_admin = GalleryItemAdmin(GalleryItem, self.site)

        self.album = GalleryAlbum.objects.create(
            slug='health-subcenter-2026',
            category=CATEGORY_INFRASTRUCTURE,
            created_by=self.operator,
        )
        self.trans_mr = AlbumTranslation.objects.create(
            album=self.album,
            language_code=LANGUAGE_MARATHI,
            title='आरोग्य उपकेंद्र बांधकाम',
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        self.item = GalleryItem.objects.create(
            album=self.album,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='आरोग्य उपकेंद्र नवीन इमारत',
            uploaded_by=self.operator,
        )

    def test_admin_submit_action(self):
        self.client.force_login(self.operator)
        post_data = {
            'action': 'submit_for_approval_action',
            '_selected_action': [str(self.album.id)],
        }
        resp = self.client.post(reverse('admin:gallery_galleryalbum_changelist'), post_data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.album.refresh_from_db()
        self.assertEqual(self.album.status, STATUS_PENDING_APPROVAL)

    def test_admin_approve_action_blocks_self_approval(self):
        # Album created by super_admin
        admin_album = GalleryAlbum.objects.create(
            slug='admin-self-approval-test',
            category=CATEGORY_WELFARE,
            created_by=self.super_admin,
        )
        AlbumTranslation.objects.create(
            album=admin_album,
            language_code=LANGUAGE_MARATHI,
            title='प्रशासक अल्बम',
        )
        storage_fn, clean_fn, size, mime, checksum = self.create_dummy_jpeg()
        GalleryItem.objects.create(
            album=admin_album,
            storage_path=storage_fn,
            original_filename=clean_fn,
            file_size_bytes=size,
            mime_type=mime,
            checksum_sha256=checksum,
            alt_text_mr='छायाचित्र तपशील',
            uploaded_by=self.super_admin,
        )

        submit_gallery_album_for_approval(admin_album.id, self.super_admin)

        # Attempt self-approval via admin action
        self.client.force_login(self.super_admin)
        post_data = {
            'action': 'approve_and_publish_action',
            '_selected_action': [str(admin_album.id)],
        }
        resp = self.client.post(reverse('admin:gallery_galleryalbum_changelist'), post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Album must NOT be published
        admin_album.refresh_from_db()
        self.assertNotEqual(admin_album.status, STATUS_PUBLISHED)
        self.assertFalse(admin_album.is_published)

        # Error message delivered to admin
        messages = list(get_messages(resp.wsgi_request))
        self.assertTrue(any("Separation of duties violation" in str(m) for m in messages))

    def test_admin_approve_action_second_admin_success(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)

        self.client.force_login(self.super_admin)
        post_data = {
            'action': 'approve_and_publish_action',
            '_selected_action': [str(self.album.id)],
        }
        resp = self.client.post(reverse('admin:gallery_galleryalbum_changelist'), post_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        self.album.refresh_from_db()
        self.assertEqual(self.album.status, STATUS_PUBLISHED)
        self.assertTrue(self.album.is_published)

    def test_admin_reject_action_intermediate_and_execution(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        self.client.force_login(self.super_admin)

        # 1. First trigger renders intermediate confirmation form
        post_data = {
            'action': 'reject_album_action',
            '_selected_action': [str(self.album.id)],
        }
        resp = self.client.post(reverse('admin:gallery_galleryalbum_changelist'), post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "rejection_reason")

        # 2. Submitting intermediate form with rationale
        post_data_confirm = {
            'action': 'reject_album_action',
            '_selected_action': [str(self.album.id)],
            'post': 'yes',
            'rejection_reason': 'Photograph lacks clarity and does not show official GP board.',
        }
        resp_confirm = self.client.post(reverse('admin:gallery_galleryalbum_changelist'), post_data_confirm, follow=True)
        self.assertEqual(resp_confirm.status_code, 200)

        self.album.refresh_from_db()
        self.assertEqual(self.album.status, STATUS_DRAFT)

    def test_admin_withdraw_action_intermediate_and_execution(self):
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)

        self.client.force_login(self.super_admin)

        # 1. Trigger intermediate confirmation form
        post_data = {
            'action': 'withdraw_album_action',
            '_selected_action': [str(self.album.id)],
        }
        resp = self.client.post(reverse('admin:gallery_galleryalbum_changelist'), post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "justification")

        # 2. Confirm withdrawal
        post_data_confirm = {
            'action': 'withdraw_album_action',
            '_selected_action': [str(self.album.id)],
            'post': 'yes',
            'justification': 'Administrative withdrawal per Gram Sabha resolution #14.',
        }
        resp_confirm = self.client.post(reverse('admin:gallery_galleryalbum_changelist'), post_data_confirm, follow=True)
        self.assertEqual(resp_confirm.status_code, 200)

        self.album.refresh_from_db()
        self.assertEqual(self.album.status, STATUS_WITHDRAWN)
        self.assertFalse(self.album.is_published)

    def test_admin_delete_permission_blocks_deleting_published(self):
        rf = RequestFactory()
        req = rf.get('/admin/')
        req.user = self.super_admin

        # Draft can be deleted
        self.assertTrue(self.album_admin.has_delete_permission(req, self.album))

        # Published album CANNOT be deleted
        submit_gallery_album_for_approval(self.album.id, self.operator)
        approve_and_publish_gallery_album(self.album.id, self.super_admin)
        self.album.refresh_from_db()
        self.assertFalse(self.album_admin.has_delete_permission(req, self.album))

        # Photo in published album cannot be deleted
        self.assertFalse(self.item_admin.has_delete_permission(req, self.item))

    def test_admin_gallery_item_creation_form(self):
        jpeg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF' + (b'\xcd' * 100)
        uploaded = SimpleUploadedFile("new_photo.jpg", jpeg_bytes, content_type="image/jpeg")

        form = GalleryItemCreationForm(
            data={
                'album': self.album.id,
                'display_order': 2,
                'caption_mr': 'नवीन फोटो',
                'alt_text_mr': 'नवीन इमारतीचे स्पष्ट दृश्य',
            },
            files={'image_file': uploaded},
        )
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save(commit=True, user=self.operator)
        self.created_files.append(get_private_gallery_dir() / item.storage_path)

        self.assertIsNotNone(item.id)
        self.assertEqual(item.uploaded_by, self.operator)
        self.assertEqual(item.mime_type, 'image/jpeg')
        self.assertTrue(item.verify_integrity())
