"""
Public citizen-facing search endpoint for Unified Public Search (apps.search).

Supports:
- GET /search/?q=<query>&lang=mr|hi|en&type=page|notice|document|event|scheme|gallery&category=...&from=YYYY-MM-DD&to=YYYY-MM-DD&page=1
- Strict language isolation (zero silent language fallback).
- Parameterized safe query handling and pagination.
- Only approved public metadata returned; zero data leakage.
"""

from django.http import JsonResponse
from apps.search.services import (
    execute_unified_search,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from apps.search.models import LANGUAGE_MARATHI


def search_view(request):
    """
    Public search API endpoint.
    Returns JSON response containing matching approved public records.
    """
    query = request.GET.get('q', '').strip()
    language = request.GET.get('lang', LANGUAGE_MARATHI).strip().lower()
    content_type = request.GET.get('type', '').strip().lower()
    category = request.GET.get('category', '').strip()
    date_from = request.GET.get('from', '').strip()
    date_to = request.GET.get('to', '').strip()

    try:
        page = int(request.GET.get('page', 1))
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    try:
        page_size = int(request.GET.get('page_size', DEFAULT_PAGE_SIZE))
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    except (ValueError, TypeError):
        page_size = DEFAULT_PAGE_SIZE

    data = execute_unified_search(
        query=query,
        language=language,
        content_type=content_type,
        category=category,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    response = JsonResponse(data, status=200)
    response['Cache-Control'] = 'public, max-age=60'
    return response
