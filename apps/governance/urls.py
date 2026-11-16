"""
Administrative CMS API URL router for GramSetu platform.

Mounts under /api/cms/ in apps/core/api_urls.py:
- /api/cms/dashboard/
- /api/cms/pending/
- /api/cms/action/
- /api/cms/audit/
- /api/cms/pages/
- /api/cms/pages/<uuid:page_id>/
- /api/cms/pages/revisions/<uuid:revision_id>/
- /api/cms/notices/
- /api/cms/notices/<uuid:notice_id>/
- /api/cms/documents/
- /api/cms/documents/<uuid:document_id>/versions/
- /api/cms/documents/versions/<uuid:version_id>/download/
- /api/cms/events/
- /api/cms/events/<uuid:event_id>/
- /api/cms/schemes/
- /api/cms/schemes/<uuid:scheme_id>/
- /api/cms/gallery/
- /api/cms/gallery/<uuid:album_id>/
- /api/cms/gallery/image/<uuid:item_id>/
"""

from django.urls import path
from apps.governance import views

app_name = 'cms'

urlpatterns = [
    # Dashboard & Review Queue
    path('dashboard/', views.cms_dashboard_view, name='dashboard'),
    path('pending/', views.cms_pending_submissions_view, name='pending_submissions'),
    path('action/', views.cms_governance_action_view, name='governance_action'),
    path('audit/', views.cms_audit_logs_view, name='audit_logs'),

    # Content Pages
    path('pages/', views.cms_pages_collection_view, name='pages_collection'),
    path('pages/research/', views.cms_page_research_view, name='page_research'),
    path('pages/<uuid:page_id>/', views.cms_page_detail_revisions_view, name='page_detail_revisions'),
    path('pages/revisions/<uuid:revision_id>/', views.cms_page_revision_update_view, name='page_revision_update'),

    # Notices & Announcements
    path('notices/', views.cms_notices_collection_view, name='notices_collection'),
    path('notices/<uuid:notice_id>/', views.cms_notice_detail_revisions_view, name='notice_detail_revisions'),

    # Disclosed Documents
    path('documents/', views.cms_documents_collection_view, name='documents_collection'),
    path('documents/<uuid:document_id>/versions/', views.cms_document_version_upload_view, name='document_version_upload'),
    path('documents/versions/<uuid:version_id>/download/', views.cms_document_version_download_view, name='document_version_download'),

    # Meetings & Events
    path('events/', views.cms_events_collection_view, name='events_collection'),
    path('events/<uuid:event_id>/', views.cms_event_detail_view, name='event_detail'),

    # Welfare Schemes
    path('schemes/', views.cms_schemes_collection_view, name='schemes_collection'),
    path('schemes/<uuid:scheme_id>/', views.cms_scheme_detail_revisions_view, name='scheme_detail_revisions'),

    # Photo Gallery
    path('gallery/', views.cms_gallery_collection_view, name='gallery_collection'),
    path('gallery/<uuid:album_id>/', views.cms_gallery_detail_items_view, name='gallery_detail_items'),
    path('gallery/image/<uuid:item_id>/', views.cms_gallery_image_serve_view, name='gallery_image_serve'),
    path('gallery/image/<uuid:item_id>', views.cms_gallery_image_serve_view),

    # Panchayat Profile & Office-Holder Management
    path('profile/', views.cms_panchayat_profile_view, name='panchayat_profile'),
]
