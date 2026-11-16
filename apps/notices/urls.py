"""
URL configuration for apps.notices public API.
"""

from django.urls import path
from apps.notices.views import notice_list_api_view, notice_detail_api_view

app_name = 'notices'

urlpatterns = [
    path('', notice_list_api_view, name='notice_list_api'),
    path('<uuid:notice_id>/', notice_detail_api_view, name='notice_detail_api'),
]
