"""
URL routes for Government Welfare Schemes (apps.schemes).
"""

from django.urls import path
from apps.schemes.views import (
    scheme_list_view,
    scheme_detail_view,
)

app_name = 'schemes'

urlpatterns = [
    path('', scheme_list_view, name='scheme_list'),
    path('<str:identifier>/', scheme_detail_view, name='scheme_detail'),
]
