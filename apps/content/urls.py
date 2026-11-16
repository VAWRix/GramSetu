"""
URL configuration for apps.content public API.
"""

from django.urls import path
from apps.content.views import page_list_api_view, page_detail_api_view

app_name = 'content'

urlpatterns = [
    path('', page_list_api_view, name='page_list_api'),
    path('<str:slug>/', page_detail_api_view, name='page_detail_api'),
]
