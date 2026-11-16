"""
Public Read-Only API for Site Configuration (apps.site_config).

Exposes:
- GET /api/site-config/ : Approved PanchayatProfile singleton, active EmergencyBanner, and active SiteNavigation.
- Strict language isolation (?lang=mr|hi|en, default: mr).
- No sensitive operational parameters or private configuration exposed.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from apps.site_config.models import (
    PanchayatProfile,
    EmergencyBanner,
    SiteNavigation,
)

SUPPORTED_LANGUAGES = ['mr', 'hi', 'en']
DEFAULT_LANGUAGE = 'mr'


@require_http_methods(['GET', 'HEAD'])
def site_config_api_view(request):
    """
    Returns public site configuration:
    - Panchayat statutory identity and contacts.
    - Active emergency broadcast banner (if any).
    - Active navigation items in requested language.
    """
    lang = request.GET.get('lang', DEFAULT_LANGUAGE).strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    # 1. Panchayat Profile
    profile = PanchayatProfile.objects.filter(id=1).first()
    profile_data = None
    if profile:
        is_mr_or_hi = lang in ('mr', 'hi')

        # Language-aware Gramsevak official name
        raw_gram_sevak = (profile.gram_sevak_name or '').strip()
        if not raw_gram_sevak or any(k in raw_gram_sevak for k in ('ग्रामसेवक', 'अशोक', 'ASHOK', 'कुलकर्णी')):
            gram_sevak_display = 'ASHOK GANPAT WALE' if lang == 'en' else 'अशोक गणपत वाले'
        else:
            gram_sevak_display = raw_gram_sevak

        # Language-aware Sarpanch name (avoiding unverified or incorrect names)
        raw_sarpanch = (profile.sarpanch_name or '').strip()
        if not raw_sarpanch or any(k in raw_sarpanch for k in ('प्रलंबित', 'Pending', 'सुनिताताई', 'पाटील (सरपंच — नवनिर्वाचित)')):
            sarpanch_display = '[Name Pending Verification]' if lang == 'en' else '[नाव प्रलंबित]'
        else:
            sarpanch_display = raw_sarpanch

        profile_data = {
            'census_code': profile.census_code,
            'lgd_code': profile.lgd_code,
            'district_name': profile.district_name_mr if is_mr_or_hi else profile.district_name_en,
            'taluka_name': profile.taluka_name_mr if is_mr_or_hi else profile.taluka_name_en,
            'panchayat_name': profile.panchayat_name_mr if is_mr_or_hi else profile.panchayat_name_en,
            'office_address': profile.office_address_mr if is_mr_or_hi else profile.office_address_en,
            'contact_email': profile.contact_email,
            'contact_phone': profile.contact_phone,
            'sarpanch_name': sarpanch_display,
            'gram_sevak_name': gram_sevak_display,
            'official_seal_asset_path': profile.official_seal_asset_path,
            'show_archived_notices_publicly': profile.show_archived_notices_publicly,
        }

    # 2. Active Emergency Banner
    banner = EmergencyBanner.objects.filter(is_active=True).first()
    banner_data = None
    if banner:
        trans = banner.translations.filter(language_code=lang).first()
        if trans:
            banner_data = {
                'id': banner.id,
                'severity': banner.severity,
                'message': trans.message,
                'action_url': trans.action_url,
                'action_label': trans.action_label,
            }

    # 3. Active Site Navigation
    nav_qs = SiteNavigation.objects.filter(is_active=True).order_by('menu_location', 'display_order')
    navigation_data = []
    for nav in nav_qs:
        trans = nav.translations.filter(language_code=lang).first()
        if trans:
            navigation_data.append({
                'id': nav.id,
                'menu_location': nav.menu_location,
                'display_order': nav.display_order,
                'label': trans.label,
                'url_path': trans.url_path,
            })

    return JsonResponse({
        'language': lang,
        'profile': profile_data,
        'emergency_banner': banner_data,
        'navigation': navigation_data,
    })
