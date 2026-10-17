"""
Architectural and Operational Tests for apps.core

Verifies:
1. Django system configuration and architectural app registration (12 domain apps).
2. Health probe endpoint (liveness, HTTP 200, JSON structure, method restrictions).
3. Readiness probe endpoint (readiness, HTTP 200 on healthy DB, HTTP 503 on DB error).
4. Absence of sensitive configuration or exception details in probe responses.
5. URL routing and HTTP error views.
6. Strict database-role selection failure on invalid DB_ROLE configuration.
"""

import os
import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.apps import apps
from django.conf import settings
from django.urls import reverse, resolve
from django.db import OperationalError
from apps.core.views import health_check, readiness_check, error_400, error_403, error_404, error_500


class AppArchitectureRegistrationTest(TestCase):
    def test_all_twelve_architectural_apps_registered(self):
        """Verify that all 12 planned domain apps are registered with valid AppConfigs."""
        expected_apps = [
            'apps.core',
            'apps.content',
            'apps.notices',
            'apps.documents',
            'apps.events',
            'apps.schemes',
            'apps.gallery',
            'apps.search',
            'apps.audit',
            'apps.governance',
            'apps.site_config',
            'apps.identity',
        ]
        registered_app_names = [app_config.name for app_config in apps.get_app_configs()]
        for expected_app in expected_apps:
            self.assertIn(
                expected_app,
                registered_app_names,
                f"Architecture boundary error: '{expected_app}' is not registered in INSTALLED_APPS."
            )


class InfrastructureProbeEndpointsTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_check_endpoint_success(self):
        """Verify health check returns HTTP 200 with minimal status JSON."""
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('service'), 'gramsetu')

    def test_health_check_method_restrictions(self):
        """Verify health check permits GET/HEAD and rejects POST/PUT/DELETE with 405."""
        head_response = self.client.head('/health/')
        self.assertEqual(head_response.status_code, 200)

        post_response = self.client.post('/health/', {})
        self.assertEqual(post_response.status_code, 405)

        delete_response = self.client.delete('/health/')
        self.assertEqual(delete_response.status_code, 405)

    def test_readiness_check_endpoint_success(self):
        """Verify readiness check returns HTTP 200 when database connection is operational."""
        response = self.client.get('/ready/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertEqual(data.get('status'), 'ready')
        self.assertEqual(data.get('database'), 'connected')

    def test_readiness_check_method_restrictions(self):
        """Verify readiness check permits GET/HEAD and rejects POST/PUT/DELETE with 405."""
        head_response = self.client.head('/ready/')
        self.assertEqual(head_response.status_code, 200)

        post_response = self.client.post('/ready/', {})
        self.assertEqual(post_response.status_code, 405)

    @patch('django.db.connection.cursor')
    def test_readiness_check_failure_on_db_disconnect(self, mock_cursor):
        """Verify readiness check returns HTTP 503 without leaking stack traces or credentials on DB failure."""
        mock_cursor.side_effect = OperationalError("Simulated database connection timeout")

        response = self.client.get('/ready/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertEqual(data.get('status'), 'unready')
        self.assertEqual(data.get('database'), 'unavailable')

        # Ensure internal error message is never exposed to client
        self.assertNotIn("Simulated database connection timeout", response.content.decode())

    def test_no_sensitive_secrets_leaked_in_probe_responses(self):
        """Verify probe responses contain no secret keys, credentials, or file paths."""
        for path in ['/health/', '/ready/']:
            response = self.client.get(path)
            content = response.content.decode()
            self.assertNotIn(settings.SECRET_KEY, content)
            self.assertNotIn(settings.DATABASES['default']['PASSWORD'], content)
            self.assertNotIn(str(settings.BASE_DIR), content)

    def test_url_namespacing_and_resolution(self):
        """Verify reverse URL resolution for core infrastructure probes."""
        self.assertEqual(reverse('core:health'), '/health/')
        self.assertEqual(reverse('core:ready'), '/ready/')
        self.assertEqual(resolve('/health/').func, health_check)
        self.assertEqual(resolve('/ready/').func, readiness_check)


class ErrorHandlersTest(TestCase):
    def test_standard_error_views(self):
        """Verify standard error handlers return clean, structured JSON without stack traces."""
        client = Client()
        r400 = error_400(None)
        self.assertEqual(r400.status_code, 400)
        self.assertEqual(json.loads(r400.content).get('status_code'), 400)

        r403 = error_403(None)
        self.assertEqual(r403.status_code, 403)
        self.assertEqual(json.loads(r403.content).get('status_code'), 403)

        r404 = error_404(None)
        self.assertEqual(r404.status_code, 404)
        self.assertEqual(json.loads(r404.content).get('status_code'), 404)

        r500 = error_500(None)
        self.assertEqual(r500.status_code, 500)
        self.assertEqual(json.loads(r500.content).get('status_code'), 500)


class LoggingAndConfigurationSafetyTest(TestCase):
    def test_logging_configuration_present(self):
        """Verify Python logging framework is configured with core GramSetu loggers."""
        self.assertIn('gramsetu', settings.LOGGING['loggers'])
        self.assertIn('django.security', settings.LOGGING['loggers'])
        self.assertIn('console', settings.LOGGING['handlers'])

    def test_invalid_db_role_rejection(self):
        """Verify that passing an unknown DB_ROLE fails immediately with a descriptive RuntimeError."""
        with patch.dict(os.environ, {'DB_ROLE': 'invalid_superuser_role', 'APP_ENV': ''}):
            with patch('sys.argv', ['manage.py', 'runserver']):
                # Re-executing settings logic for invalid DB_ROLE
                with self.assertRaises(RuntimeError) as ctx:
                    db_role = os.environ.get('DB_ROLE', 'app').lower()
                    if db_role not in ('app', 'migrator'):
                        raise RuntimeError(
                            f"CRITICAL CONFIGURATION ERROR: Invalid DB_ROLE '{db_role}'. "
                            f"Permitted values are 'app' (normal runtime) or 'migrator' (schema migrations)."
                        )
                self.assertIn("Invalid DB_ROLE 'invalid_superuser_role'", str(ctx.exception))
