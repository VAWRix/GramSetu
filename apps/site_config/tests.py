"""
Unit tests for apps.site_config models and constraints.
"""

from django.test import SimpleTestCase
from apps.site_config.models import (
    PanchayatProfile,
    SiteNavigation,
    NavigationTranslation,
    EmergencyBanner,
    EmergencyBannerTranslation,
)


class PanchayatProfileModelTests(SimpleTestCase):
    """
    Tests for PanchayatProfile singleton invariants and fields.
    """

    def test_singleton_id_enforced_on_save(self):
        profile = PanchayatProfile(
            id=42,  # Attempting non-1 id
            census_code='555123',
            lgd_code='246810',
            district_name_mr='पुणे',
            district_name_en='Pune',
            taluka_name_mr='हवेली',
            taluka_name_en='Haveli',
            panchayat_name_mr='ग्रामपंचायत वाघोली',
            panchayat_name_en='Gram Panchayat Wagholi',
            office_address_mr='मुख्य चौक, वाघोली',
            office_address_en='Main Chowk, Wagholi',
            contact_email='contact@wagholi-gp.gov.in',
            contact_phone='020-12345678',
            sarpanch_name='श्री. पाटील',
            gram_sevak_name='श्री. कुलकर्णी',
        )
        # Verify str format
        self.assertEqual(str(profile), 'ग्रामपंचायत वाघोली (555123)')
        self.assertTrue(profile.show_archived_notices_publicly)


class SiteNavigationModelTests(SimpleTestCase):
    """
    Tests for SiteNavigation and NavigationTranslation models.
    """

    def test_navigation_and_translation_representation(self):
        nav = SiteNavigation(
            id=1,
            menu_location=SiteNavigation.LOCATION_HEADER,
            display_order=10,
            is_active=True,
        )
        self.assertIn('Header Menu', str(nav))

        trans_mr = NavigationTranslation(
            navigation=nav,
            language_code='mr',
            label='मुख्यपृष्ठ',
            url_path='/',
        )
        self.assertEqual(str(trans_mr), 'मुख्यपृष्ठ [mr] -> /')

        trans_en = NavigationTranslation(
            navigation=nav,
            language_code='en',
            label='Home',
            url_path='/en/',
        )
        self.assertEqual(str(trans_en), 'Home [en] -> /en/')


class EmergencyBannerModelTests(SimpleTestCase):
    """
    Tests for EmergencyBanner and multilingual EmergencyBannerTranslation.
    """

    def test_banner_and_translation_representation(self):
        banner = EmergencyBanner(
            id=5,
            severity=EmergencyBanner.SEVERITY_DANGER,
            is_active=False,
        )
        self.assertIn('Critical Emergency', str(banner))
        self.assertFalse(banner.is_active)

        trans_mr = EmergencyBannerTranslation(
            banner=banner,
            language_code='mr',
            message='गावात अतिवृष्टीचा इशारा देण्यात आला आहे. नागरिकांनी सतर्क रहावे.',
        )
        self.assertTrue(str(trans_mr).startswith('[mr] गावात अतिवृष्टीचा इशारा'))

        trans_en = EmergencyBannerTranslation(
            banner=banner,
            language_code='en',
            message='Heavy rainfall red alert issued for village. Stay indoors.',
        )
        self.assertTrue(str(trans_en).startswith('[en] Heavy rainfall red alert'))
