"""
Public Read-Only JSON API URL router for GramSetu platform.

Mounts clean, uniform endpoints under /api/ for all statutory domains:
- /api/site-config/
- /api/content/pages/
- /api/notices/
- /api/documents/
- /api/events/
- /api/schemes/
- /api/gallery/
- /api/search/
"""

from django.urls import path, include
from apps.site_config.views import site_config_api_view
from apps.content.views import page_list_api_view, page_detail_api_view
from apps.notices.views import notice_list_api_view, notice_detail_api_view
from apps.documents.views import document_list_api_view, document_detail_api_view
from apps.events.views import event_list_view, event_detail_view
from apps.schemes.views import scheme_list_view, scheme_detail_view
from apps.gallery.views import gallery_list_view, gallery_detail_view, gallery_image_serve_view
from apps.search.views import search_view

app_name = 'api'

urlpatterns = [
    # Authentication & Multi-Factor Authentication (MFA)
    path('auth/', include('apps.identity.urls')),

    # Administrative CMS & Governance Workflows
    path('cms/', include('apps.governance.urls')),

    # Site Configuration
    path('site-config/', site_config_api_view, name='site_config'),

    # Informational Content Pages
    path('content/pages/', page_list_api_view, name='page_list'),
    path('content/pages/<str:slug>/', page_detail_api_view, name='page_detail'),

    # Notices & Announcements
    path('notices/', notice_list_api_view, name='notice_list'),
    path('notices/<uuid:notice_id>/', notice_detail_api_view, name='notice_detail'),

    # Disclosed Documents
    path('documents/', document_list_api_view, name='document_list'),
    path('documents/<uuid:document_id>/', document_detail_api_view, name='document_detail'),

    # Meetings & Events
    path('events/', event_list_view, name='event_list'),
    path('events/<uuid:event_id>/', event_detail_view, name='event_detail'),

    # Welfare Schemes
    path('schemes/', scheme_list_view, name='scheme_list'),
    path('schemes/<str:identifier>/', scheme_detail_view, name='scheme_detail'),

    # Photo Gallery
    path('gallery/', gallery_list_view, name='gallery_list'),
    path('gallery/image/<uuid:item_id>/', gallery_image_serve_view, name='gallery_image_serve'),
    path('gallery/image/<uuid:item_id>', gallery_image_serve_view),
    path('gallery/<str:identifier>/', gallery_detail_view, name='gallery_detail'),
    path('gallery/<str:identifier>', gallery_detail_view),

    # Unified Public Search
    path('search/', search_view, name='search'),
]
