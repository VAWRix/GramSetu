"""
URL routes for Approved Media Gallery (apps.gallery).
"""

from django.urls import path
from apps.gallery.views import (
    gallery_list_view,
    gallery_detail_view,
    gallery_image_serve_view,
)

app_name = 'gallery'

urlpatterns = [
    path('', gallery_list_view, name='album_list'),
    path('image/<uuid:item_id>/', gallery_image_serve_view, name='image_serve'),
    path('image/<uuid:item_id>', gallery_image_serve_view),
    path('<str:identifier>/', gallery_detail_view, name='album_detail'),
    path('<str:identifier>', gallery_detail_view),
]
