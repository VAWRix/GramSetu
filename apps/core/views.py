import logging
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe

logger = logging.getLogger('gramsetu.core')


@require_safe
def health_check(request):
    """
    Process Liveness Probe.
    Returns HTTP 200 if the Django application process is alive and responding.
    Does not touch external dependencies or databases.
    """
    return JsonResponse(
        {
            "status": "ok",
            "service": "gramsetu",
        },
        status=200
    )


@require_safe
def readiness_check(request):
    """
    Service Readiness Probe.
    Checks whether the application process can interact with its configured database.
    Returns HTTP 200 when ready, HTTP 503 when the database is unavailable.
    Never exposes internal error messages, SQL queries, paths, or secrets.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if not row or row[0] != 1:
                logger.error("Readiness check returned unexpected query result.")
                return JsonResponse(
                    {
                        "status": "unready",
                        "database": "unhealthy",
                    },
                    status=503
                )
        return JsonResponse(
            {
                "status": "ready",
                "database": "connected",
            },
            status=200
        )
    except Exception as exc:
        # Log minimal technical details internally without leaking to client
        logger.error("Readiness check failed: database connection error: %s", type(exc).__name__)
        return JsonResponse(
            {
                "status": "unready",
                "database": "unavailable",
            },
            status=503
        )


def error_400(request, exception=None):
    return JsonResponse({"error": "Bad Request", "status_code": 400}, status=400)


def error_403(request, exception=None):
    return JsonResponse({"error": "Forbidden", "status_code": 403}, status=403)


def error_404(request, exception=None):
    return JsonResponse({"error": "Not Found", "status_code": 404}, status=404)


def error_500(request):
    return JsonResponse({"error": "Internal Server Error", "status_code": 500}, status=500)
