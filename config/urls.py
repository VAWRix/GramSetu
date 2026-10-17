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
]

# Standardized error handlers
handler400 = 'apps.core.views.error_400'
handler403 = 'apps.core.views.error_403'
handler404 = 'apps.core.views.error_404'
handler500 = 'apps.core.views.error_500'
