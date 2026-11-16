"""
URL configuration for apps.site_config public API.
"""

from django.urls import path
from apps.site_config.views import site_config_api_view

app_name = 'site_config'

urlpatterns = [
    path('', site_config_api_view, name='site_config_api'),
]
