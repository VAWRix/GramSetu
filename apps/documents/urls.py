"""
URL configuration for apps.documents.
"""

from django.urls import path
from apps.documents import views

app_name = 'documents'

urlpatterns = [
    # Citizen document download
    path('<uuid:translation_id>/download/', views.citizen_document_download, name='citizen_download'),
    
    # Administrative & audit version download
    path('version/<uuid:version_id>/download/', views.version_document_download, name='version_download'),

    # Public Documents JSON API
    path('', views.document_list_api_view, name='document_list_api'),
    path('<uuid:document_id>/', views.document_detail_api_view, name='document_detail_api'),
]
