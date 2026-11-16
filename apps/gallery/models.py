"""
Approved Media Gallery domain models for GramSetu platform.

Implements GalleryAlbum (logical anchor), AlbumTranslation (multilingual explicit entity),
and GalleryItem (individual approved photograph with accessibility alt text) in accordance with
approved architectural specifications in docs/data-model.md Section 4.9 and ADRs 0001, 0002, 0003, and 0006.

Covers approved photographs of public infrastructure, development works, Gram Sabha proceedings,
welfare distributions, and cultural functions with strict accessibility and storage security.
"""

import hashlib
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from apps.core.utils import generate_uuid7
from apps.gallery.storage import (
    verify_gallery_image_integrity,
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGE_SIZE_BYTES,
)

# Language constants (Marathi statutory primary)
LANGUAGE_MARATHI = 'mr'
LANGUAGE_HINDI = 'hi'
LANGUAGE_ENGLISH = 'en'

LANGUAGE_CHOICES = [
    (LANGUAGE_MARATHI, 'Marathi / मराठी'),
    (LANGUAGE_HINDI, 'Hindi / हिंदी'),
    (LANGUAGE_ENGLISH, 'English / इंग्रजी'),
]

# Gallery Album Category Constants (Section 4.9)
CATEGORY_INFRASTRUCTURE = 'infrastructure'
CATEGORY_GRAM_SABHA = 'gram_sabha'
CATEGORY_WELFARE = 'welfare'
CATEGORY_CULTURAL = 'cultural'
CATEGORY_ENVIRONMENT = 'environment'

ALBUM_CATEGORY_CHOICES = [
    (CATEGORY_INFRASTRUCTURE, 'Public Infrastructure / पायाभूत सुविधा व विकासकामे'),
    (CATEGORY_GRAM_SABHA, 'Gram Sabha Proceedings / ग्रामसभा व बैठका'),
    (CATEGORY_WELFARE, 'Welfare & Benefits / योजना वाटप व समाजकल्याण'),
    (CATEGORY_CULTURAL, 'Cultural & National Events / सांस्कृतिक व राष्ट्रीय उत्सव'),
    (CATEGORY_ENVIRONMENT, 'Environment & Water / पर्यावरण व जलसंधारण'),
]

# Album Publication & Lifecycle Status
STATUS_DRAFT = 'draft'
STATUS_PENDING_APPROVAL = 'pending_approval'
STATUS_APPROVED = 'approved'
STATUS_PUBLISHED = 'published'
STATUS_WITHDRAWN = 'withdrawn'
STATUS_ARCHIVED = 'archived'

STATUS_CHOICES = [
    (STATUS_DRAFT, 'Draft / मसुदा'),
    (STATUS_PENDING_APPROVAL, 'Pending Review / मंजुरी प्रलंबित'),
    (STATUS_APPROVED, 'Approved / मंजूर'),
    (STATUS_PUBLISHED, 'Published / प्रकाशित'),
    (STATUS_WITHDRAWN, 'Withdrawn / मागे घेतले'),
    (STATUS_ARCHIVED, 'Archived / संग्रहित'),
]


class GalleryAlbumQuerySet(models.QuerySet):
    def public_eligible(self, allow_archived: bool = False):
        """
        Returns gallery albums eligible for public citizen viewing:
        - is_published is True
        - status is 'published' (or 'archived' if allow_archived)
        """
        allowed_statuses = [STATUS_PUBLISHED]
        if allow_archived:
            allowed_statuses.append(STATUS_ARCHIVED)

        return self.filter(
            is_published=True,
            status__in=allowed_statuses,
        )

    def for_language(self, language_code: str = LANGUAGE_MARATHI):
        """
        Filters albums having an explicit translation in the requested language.
        Strict translation entity: no silent fallback.
        """
        return self.filter(translations__language_code=language_code).distinct()

    def by_category(self, category: str):
        return self.filter(category=category)


class GalleryAlbumManager(models.Manager.from_queryset(GalleryAlbumQuerySet)):
    pass


class GalleryAlbum(models.Model):
    """
    Canonical logical anchor for an approved photograph album or event collection.
    Tracks event date, categorization, publication state, and statutory provenance.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    slug = models.SlugField(
        max_length=150,
        unique=True,
        allow_unicode=False,
        help_text="Language-neutral ASCII identifier (e.g. 'water-conservation-2026')",
    )
    category = models.CharField(
        max_length=50,
        choices=ALBUM_CATEGORY_CHOICES,
        default=CATEGORY_INFRASTRUCTURE,
        db_index=True,
        help_text="Thematic classification of photograph collection",
    )
    event_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date on which photographs were captured / कार्यक्रमाचा दिनांक",
    )
    is_published = models.BooleanField(
        default=False,
        help_text="True if approved and publicly accessible on citizen portal",
    )
    primary_language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default=LANGUAGE_MARATHI,
        db_index=True,
        help_text="Primary content language (mr, hi, en) / मुख्य भाषा",
    )
    status = models.CharField(
        max_length=20,
        default=STATUS_DRAFT,
        choices=STATUS_CHOICES,
        help_text="Lifecycle and publication status",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_gallery_albums',
        help_text="Staff member who created the album container",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = GalleryAlbumManager()

    class Meta:
        db_table = 'gallery_album'
        verbose_name = 'Gallery Album / चित्रदालन संग्रह'
        verbose_name_plural = 'Gallery Albums / चित्रदालन संग्रह'
        ordering = ['-event_date', '-created_at']
        indexes = [
            models.Index(fields=['-event_date', '-created_at'], name='idx_album_date'),
            models.Index(fields=['category', 'status', 'is_published'], name='idx_album_cat_status'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(category__in=[c[0] for c in ALBUM_CATEGORY_CHOICES]),
                name='chk_valid_album_category',
            ),
            models.CheckConstraint(
                condition=Q(status__in=[c[0] for c in STATUS_CHOICES]),
                name='chk_valid_album_status',
            ),
            models.CheckConstraint(
                condition=Q(primary_language__in=[c[0] for c in LANGUAGE_CHOICES]),
                name='chk_valid_album_primary_lang',
            ),
        ]

    def __str__(self):
        title = self.get_title() or self.slug
        date_str = f" ({self.event_date.strftime('%d-%m-%Y')})" if self.event_date else ""
        return f"{title}{date_str} [{self.get_category_display()}]"

    def clean(self):
        super().clean()
        if self.is_published and self.status == STATUS_DRAFT:
            raise ValidationError("Draft albums cannot be marked as published.")

    def get_primary_translation(self):
        """
        Returns the translation matching the album's primary language,
        or falls back to any available translation.
        """
        return self.translations.filter(language_code=self.primary_language).first() or self.translations.first()

    def get_translation(self, language_code: str = None):
        """
        Returns localized translation for language_code if available,
        otherwise falls back to the primary language translation.
        """
        if language_code:
            t = self.translations.filter(language_code=language_code).first()
            if t:
                return t
        return self.get_primary_translation()

    def get_title(self, language_code: str = None) -> str:
        """
        Returns localized album title, falling back to primary translation.
        """
        t = self.get_translation(language_code)
        return t.title if t else ""

    def get_description(self, language_code: str = None) -> str:
        """
        Returns localized album description, falling back to primary translation.
        """
        t = self.get_translation(language_code)
        return t.description if t else ""

    def is_publicly_visible(self, allow_archived: bool = False) -> bool:
        """
        Evaluates whether this album is currently eligible for public citizen viewing.
        """
        if not self.is_published:
            return False
        if self.status == STATUS_PUBLISHED:
            return True
        if self.status == STATUS_ARCHIVED and allow_archived:
            return True
        return False

    @property
    def cover_image(self):
        """
        Returns designated cover image or first photograph in display order.
        """
        cover = self.items.filter(is_cover_image=True).first()
        if not cover:
            cover = self.items.order_by('display_order', 'uploaded_at').first()
        return cover

    def calculate_hash(self) -> str:
        """
        Computes deterministic SHA-256 digest of album metadata, its translations,
        and its member image checksums for tamper-evident binding in ApprovalRecord.
        """
        trans_data = []
        if self.pk:
            for t in self.translations.all().order_by('language_code'):
                trans_data.append(f"{t.language_code}:{t.title.strip()}:{t.description.strip()}")

        items_data = []
        if self.pk:
            for item in self.items.all().order_by('display_order', 'id'):
                alt_txt = (item.alt_text_mr or item.alt_text_en or item.alt_text_hi or '').strip()
                items_data.append(f"{item.id}:{item.checksum_sha256}:{alt_txt}")

        trans_str = "|".join(trans_data)
        items_str = "|".join(items_data)
        date_str = self.event_date.isoformat() if self.event_date else ""
        payload = (
            f"slug:{self.slug}|cat:{self.category}|primary_lang:{self.primary_language}|date:{date_str}|"
            f"trans:{trans_str}|items:{items_str}"
        ).encode('utf-8')
        return hashlib.sha256(payload).hexdigest()


class AlbumTranslation(models.Model):
    """
    Multilingual explicit translation entity for a GalleryAlbum.
    Enforces the Explicit Translation Entity pattern (ADR 0001).
    """
    id = models.BigAutoField(primary_key=True)
    album = models.ForeignKey(
        GalleryAlbum,
        on_delete=models.CASCADE,
        related_name='translations',
    )
    language_code = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
    )
    title = models.CharField(
        max_length=255,
        help_text="Localized album title / अल्बमचे शीर्षक",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the event or development initiative",
    )

    class Meta:
        db_table = 'gallery_album_translation'
        verbose_name = 'Album Translation / अल्बम भाषांतर'
        verbose_name_plural = 'Album Translations / अल्बम भाषांतरे'
        ordering = ['album', 'language_code']
        constraints = [
            models.UniqueConstraint(
                fields=['album', 'language_code'],
                name='uq_album_lang',
            ),
            models.CheckConstraint(
                condition=Q(language_code__in=[c[0] for c in LANGUAGE_CHOICES]),
                name='chk_valid_album_lang',
            ),
        ]

    def __str__(self):
        return f"{self.album.slug} [{self.language_code}] - {self.title}"


class GalleryItem(models.Model):
    """
    Individual approved photograph within a GalleryAlbum.
    Stores binary in protected disk storage and tracks mandatory accessibility alt text.
    """
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    album = models.ForeignKey(
        GalleryAlbum,
        on_delete=models.CASCADE,
        related_name='items',
    )
    storage_path = models.CharField(
        max_length=500,
        unique=True,
        help_text="Unguessable internal storage filename on private disk",
    )
    original_filename = models.CharField(
        max_length=255,
        help_text="Original uploaded filename (sanitized)",
    )
    file_size_bytes = models.IntegerField(
        help_text="Binary size in bytes (max 15 MB)",
    )
    mime_type = models.CharField(
        max_length=100,
        help_text="Verified image MIME type (image/jpeg, image/png, image/webp)",
    )
    width_px = models.IntegerField(
        null=True,
        blank=True,
        help_text="Image pixel width",
    )
    height_px = models.IntegerField(
        null=True,
        blank=True,
        help_text="Image pixel height",
    )
    checksum_sha256 = models.CharField(
        max_length=64,
        help_text="Cryptographic SHA-256 digest of image binary",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Sequential display order within the album",
    )
    is_cover_image = models.BooleanField(
        default=False,
        help_text="If True, displayed as the representative thumbnail for the album",
    )
    caption_mr = models.CharField(
        max_length=255,
        blank=True,
        help_text="Marathi photograph caption / छायाचित्राचे शीर्षक",
    )
    caption_hi = models.CharField(
        max_length=255,
        blank=True,
        help_text="Hindi photograph caption",
    )
    caption_en = models.CharField(
        max_length=255,
        blank=True,
        help_text="English photograph caption",
    )
    alt_text_mr = models.CharField(
        max_length=255,
        help_text="Mandatory Marathi accessibility description / वर्णनात्मक मजकूर (screen readers)",
    )
    alt_text_hi = models.CharField(
        max_length=255,
        blank=True,
        help_text="Hindi accessibility description",
    )
    alt_text_en = models.CharField(
        max_length=255,
        blank=True,
        help_text="English accessibility description",
    )
    source_type = models.CharField(
        max_length=10,
        choices=[('upload', 'Direct Upload'), ('link', 'External Link')],
        default='upload',
        help_text="Source of the photograph: file upload or validated external URL",
    )
    external_url = models.URLField(
        max_length=1000,
        blank=True,
        null=True,
        help_text="Direct or converted image URL for external link items",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='uploaded_gallery_items',
        help_text="Staff member who uploaded the photograph",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='approved_gallery_items',
        help_text="Super Administrator who formally approved this photograph",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gallery_item'
        verbose_name = 'Gallery Photo / छायाचित्र'
        verbose_name_plural = 'Gallery Photos / छायाचित्रे'
        ordering = ['display_order', 'uploaded_at']
        indexes = [
            models.Index(fields=['album', 'display_order'], name='idx_gallery_album_order'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(file_size_bytes__gt=0) & Q(file_size_bytes__lte=MAX_IMAGE_SIZE_BYTES),
                name='chk_gallery_file_size',
            ),
            models.CheckConstraint(
                condition=Q(mime_type__in=sorted(ALLOWED_IMAGE_MIME_TYPES)),
                name='chk_valid_gallery_mime',
            ),
        ]

    def __str__(self):
        return f"Photo #{str(self.id)[:8]} ({self.original_filename})"

    def clean(self):
        super().clean()
        alt_text = (self.alt_text_mr or self.alt_text_en or self.alt_text_hi or '').strip()
        if not alt_text or len(alt_text) < 3:
            raise ValidationError("Accessibility alt text (alt_text_mr) must be at least 3 characters.")
        if not self.alt_text_mr:
            self.alt_text_mr = alt_text

    def verify_integrity(self) -> bool:
        """
        Verifies disk image integrity against expected SHA-256 checksum.
        """
        if self.source_type == 'link':
            return bool(self.external_url)
        return verify_gallery_image_integrity(self.storage_path, self.checksum_sha256)

    @property
    def caption(self) -> str:
        """Single caption entered for this photograph."""
        return self.caption_mr or self.caption_hi or self.caption_en or ""

    @property
    def alt_text(self) -> str:
        """Single accessible alt text entered for this photograph."""
        return self.alt_text_mr or self.alt_text_hi or self.alt_text_en or ""

    def get_caption(self, language_code: str = None) -> str:
        """Consistently returns the single saved caption regardless of language."""
        return self.caption

    def get_alt_text(self, language_code: str = None) -> str:
        """Consistently returns the single accessible alt text regardless of language."""
        return self.alt_text
