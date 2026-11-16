"""
GramSetu Root URL Configuration
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Infrastructure & operational probes
    path('', include('apps.core.urls')),
    
    # Administrative portal
    path('admin/', admin.site.urls),

    # Protected documents and downloads domain
    path('documents/', include('apps.documents.urls')),

    # Panchayat events and meetings domain
    path('events/', include('apps.events.urls')),

    # Government welfare schemes domain
    path('schemes/', include('apps.schemes.urls')),

    # Approved media gallery domain
    path('gallery/', include('apps.gallery.urls')),

    # Unified public search domain
    path('search/', include('apps.search.urls')),

    # Dedicated Public Read-Only JSON API for Frontend Integration
    path('api/', include('apps.core.api_urls')),
]

# Standardized error handlers
handler400 = 'apps.core.views.error_400'
handler403 = 'apps.core.views.error_403'
handler404 = 'apps.core.views.error_404'
handler500 = 'apps.core.views.error_500'
