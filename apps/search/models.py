"""
Unified Public Search Index models for GramSetu platform.

Implements SearchDocumentIndex as a denormalized projection table optimized for fast,
secure public search across all disclosed domain records without cross-table outer joins,
in accordance with approved architectural specifications in docs/data-model.md Section 4.10.
"""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models import Q
from django.utils import timezone

# Target content type choices
TYPE_PAGE = 'page'
TYPE_NOTICE = 'notice'
TYPE_DOCUMENT = 'document'
TYPE_EVENT = 'event'
TYPE_SCHEME = 'scheme'
TYPE_GALLERY = 'gallery'

TARGET_CONTENT_TYPE_CHOICES = [
    (TYPE_PAGE, 'Informational Page / माहिती पान'),
    (TYPE_NOTICE, 'Notice & Announcement / सूचना व जाहिरात'),
    (TYPE_DOCUMENT, 'Document & Download / दस्तऐवज'),
    (TYPE_EVENT, 'Event & Meeting / कार्यक्रम व सभा'),
    (TYPE_SCHEME, 'Government Scheme / शासकीय योजना'),
    (TYPE_GALLERY, 'Media Gallery / चित्रदालन'),
]

# Language constants (Marathi statutory primary)
LANGUAGE_MARATHI = 'mr'
LANGUAGE_HINDI = 'hi'
LANGUAGE_ENGLISH = 'en'

LANGUAGE_CHOICES = [
    (LANGUAGE_MARATHI, 'Marathi / मराठी'),
    (LANGUAGE_HINDI, 'Hindi / हिंदी'),
    (LANGUAGE_ENGLISH, 'English / इंग्रजी'),
]


class SearchDocumentIndex(models.Model):
    """
    Denormalized search projection table optimized for fast public citizen search
    across all approved and disclosed domain records.

    Enforces:
    - Zero exposure of private storage paths, draft content, or confidential records.
    - Strict language isolation (zero silent language fallback).
    - PostgreSQL full-text search vector with GIN index.
    """
    id = models.BigAutoField(primary_key=True)
    target_content_type = models.CharField(
        max_length=50,
        choices=TARGET_CONTENT_TYPE_CHOICES,
        db_index=True,
        help_text="Domain content type of the target entity",
    )
    target_id = models.UUIDField(
        db_index=True,
        help_text="Primary UUID identifier of the root domain entity",
    )
    language_code = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        db_index=True,
        help_text="Explicit translation language code (mr, hi, en)",
    )
    title = models.CharField(
        max_length=300,
        help_text="Approved localized title",
    )
    summary = models.TextField(
        blank=True,
        help_text="Brief public summary or description",
    )
    search_text = models.TextField(
        help_text="Consolidated searchable plain text body",
    )
    search_vector = SearchVectorField(
        null=True,
        blank=True,
        help_text="PostgreSQL tsvector generated for fast full-text matching",
    )
    published_at = models.DateTimeField(
        db_index=True,
        help_text="Effective publication timestamp for ordering and date range filters",
    )
    url_path = models.CharField(
        max_length=500,
        help_text="Canonical public URL path for navigating to the item",
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Domain-specific category code for structured faceted filtering",
    )
    category_display = models.CharField(
        max_length=150,
        blank=True,
        help_text="Localized human-readable category name",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when search index entry was last refreshed",
    )

    class Meta:
        db_table = 'search_document_index'
        verbose_name = 'Search Index Record / शोध नोंद'
        verbose_name_plural = 'Search Index Records / शोध नोंदी'
        ordering = ['-published_at']
        indexes = [
            GinIndex(fields=['search_vector'], name='idx_search_vector'),
            models.Index(fields=['language_code', '-published_at'], name='idx_search_lang_pub'),
            models.Index(fields=['target_content_type', 'language_code'], name='idx_search_type_lang'),
            models.Index(fields=['category', 'language_code'], name='idx_search_cat_lang'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['target_content_type', 'target_id', 'language_code'],
                name='uq_search_target_lang',
            ),
            models.CheckConstraint(
                condition=Q(language_code__in=[c[0] for c in LANGUAGE_CHOICES]),
                name='chk_valid_search_lang',
            ),
            models.CheckConstraint(
                condition=Q(target_content_type__in=[c[0] for c in TARGET_CONTENT_TYPE_CHOICES]),
                name='chk_valid_search_type',
            ),
        ]

    def __str__(self):
        return f"[{self.target_content_type}:{self.language_code}] {self.title[:50]}"
