"""
Site Configuration models for GramSetu platform.

Implements PanchayatProfile (singleton), SiteNavigation, NavigationTranslation,
EmergencyBanner, and EmergencyBannerTranslation in accordance with approved architectural
specifications in docs/data-model.md.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class PanchayatProfile(models.Model):
    """
    Singleton record representing the official statutory identity and contact details
    of the local Gram Panchayat. Enforced as single-row via check constraint (id = 1).
    """
    id = models.SmallIntegerField(primary_key=True, default=1, editable=False)
    census_code = models.CharField(max_length=20, unique=True, help_text="Official Census 2011 Village Code.")
    lgd_code = models.CharField(max_length=20, unique=True, help_text="Local Government Directory (LGD) Code.")
    district_name_mr = models.CharField(max_length=100)
    district_name_en = models.CharField(max_length=100)
    taluka_name_mr = models.CharField(max_length=100)
    taluka_name_en = models.CharField(max_length=100)
    panchayat_name_mr = models.CharField(max_length=200)
    panchayat_name_en = models.CharField(max_length=200)
    office_address_mr = models.TextField()
    office_address_en = models.TextField()
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20)
    sarpanch_name = models.CharField(max_length=150)
    gram_sevak_name = models.CharField(max_length=150)
    official_seal_asset_path = models.CharField(max_length=500, blank=True)
    show_archived_notices_publicly = models.BooleanField(
        default=True,
        help_text="Controls whether expired notices are displayed in public historical archives.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='updated_profiles',
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'site_config_panchayat_profile'
        verbose_name = 'Panchayat Profile / ग्रामपंचायत माहिती'
        verbose_name_plural = 'Panchayat Profile / ग्रामपंचायत माहिती'
        constraints = [
            models.CheckConstraint(
                check=Q(id=1),
                name='chk_single_profile',
            ),
        ]

    def __str__(self):
        return f"{self.panchayat_name_mr} ({self.census_code})"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)


class SiteNavigation(models.Model):
    """
    Logical navigation container for header and footer menus.
    """
    LOCATION_HEADER = 'header'
    LOCATION_FOOTER = 'footer'

    LOCATION_CHOICES = [
        (LOCATION_HEADER, 'Header Menu'),
        (LOCATION_FOOTER, 'Footer Menu'),
    ]

    menu_location = models.CharField(max_length=20, choices=LOCATION_CHOICES)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'site_config_navigation'
        verbose_name = 'Navigation Item / मेनू घटक'
        verbose_name_plural = 'Navigation Items / मेनू घटक'
        ordering = ['menu_location', 'display_order']
        constraints = [
            models.CheckConstraint(
                check=Q(menu_location__in=['header', 'footer']),
                name='chk_valid_menu_location',
            ),
        ]

    def __str__(self):
        return f"Navigation #{self.id} [{self.get_menu_location_display()}] (order={self.display_order})"


class NavigationTranslation(models.Model):
    """
    Multilingual label and target URL for a navigation menu item.
    """
    navigation = models.ForeignKey(
        SiteNavigation,
        on_delete=models.CASCADE,
        related_name='translations',
    )
    language_code = models.CharField(
        max_length=5,
        choices=[('mr', 'Marathi'), ('hi', 'Hindi'), ('en', 'English')],
    )
    label = models.CharField(max_length=100)
    url_path = models.CharField(max_length=255)

    class Meta:
        db_table = 'site_config_navigation_translation'
        verbose_name = 'Navigation Translation / मेनू भाषांतर'
        verbose_name_plural = 'Navigation Translations / मेनू भाषांतरे'
        constraints = [
            models.UniqueConstraint(
                fields=['navigation', 'language_code'],
                name='uq_nav_lang',
            ),
            models.CheckConstraint(
                check=Q(language_code__in=['mr', 'hi', 'en']),
                name='chk_valid_nav_lang',
            ),
        ]

    def __str__(self):
        return f"{self.label} [{self.language_code}] -> {self.url_path}"


class EmergencyBanner(models.Model):
    """
    High-visibility emergency banner broadcast across public pages.
    Enforces that only one emergency banner can be active site-wide at any time.
    """
    SEVERITY_INFO = 'info'
    SEVERITY_WARNING = 'warning'
    SEVERITY_DANGER = 'danger'

    SEVERITY_CHOICES = [
        (SEVERITY_INFO, 'Informational'),
        (SEVERITY_WARNING, 'Warning'),
        (SEVERITY_DANGER, 'Critical Emergency'),
    ]

    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_banners',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'site_config_emergency_banner'
        verbose_name = 'Emergency Banner / आणीबाणी सूचना फलक'
        verbose_name_plural = 'Emergency Banners / आणीबाणी सूचना फलक'
        constraints = [
            models.UniqueConstraint(
                fields=['is_active'],
                condition=Q(is_active=True),
                name='uq_active_emergency_banner',
            ),
            models.CheckConstraint(
                check=Q(severity__in=['info', 'warning', 'danger']),
                name='chk_valid_banner_severity',
            ),
        ]

    def __str__(self):
        return f"Banner #{self.id} [{self.get_severity_display()}] (active={self.is_active})"


class EmergencyBannerTranslation(models.Model):
    """
    Multilingual copy for an emergency banner.
    """
    banner = models.ForeignKey(
        EmergencyBanner,
        on_delete=models.CASCADE,
        related_name='translations',
    )
    language_code = models.CharField(
        max_length=5,
        choices=[('mr', 'Marathi'), ('hi', 'Hindi'), ('en', 'English')],
    )
    message = models.CharField(max_length=500)
    action_url = models.URLField(blank=True)
    action_label = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'site_config_emergency_banner_translation'
        verbose_name = 'Emergency Banner Translation / आणीबाणी फलक भाषांतर'
        verbose_name_plural = 'Emergency Banner Translations / आणीबाणी फलक भाषांतरे'
        constraints = [
            models.UniqueConstraint(
                fields=['banner', 'language_code'],
                name='uq_banner_lang',
            ),
            models.CheckConstraint(
                check=Q(language_code__in=['mr', 'hi', 'en']),
                name='chk_valid_banner_lang',
            ),
        ]

    def __str__(self):
        return f"[{self.language_code}] {self.message[:50]}..."
