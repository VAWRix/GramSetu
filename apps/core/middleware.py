"""
Deliberate CORS Middleware for GramSetu platform.

Enforces secure, explicit cross-origin policy for local Next.js development:
- Matches incoming Origin strictly against settings.CORS_ALLOWED_ORIGINS.
- Never emits wildcard '*' when Access-Control-Allow-Credentials is true.
- Handles preflight OPTIONS requests without modifying application state.
"""

from django.conf import settings
from django.http import HttpResponse


class DeliberateCorsMiddleware:
    """
    Deliberate, non-wildcard CORS middleware supporting session cookie credentials.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin', '')
        allowed_origins = getattr(
            settings,
            'CORS_ALLOWED_ORIGINS',
            ['http://localhost:3000', 'http://127.0.0.1:3000'],
        )

        # Handle preflight OPTIONS request
        if request.method == 'OPTIONS' and origin in allowed_origins:
            response = HttpResponse()
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            if request.path.startswith('/api/cms/') or request.path.startswith('/api/auth/'):
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS'
            else:
                response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken, Authorization, Accept'
            response['Access-Control-Max-Age'] = '86400'
            return response

        response = self.get_response(request)

        if origin and origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRFToken, Authorization, Accept'

        return response
