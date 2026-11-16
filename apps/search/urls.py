"""
URL routes for Unified Public Search (apps.search).
"""

from django.urls import path
from apps.search.views import search_view

app_name = 'search'

urlpatterns = [
    path('', search_view, name='public_search'),
]
