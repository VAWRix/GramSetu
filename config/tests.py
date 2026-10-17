"""
GramSetu Foundation Smoke Tests

Verifies:
1. Django environment and settings load correctly.
2. Active test database connection is operational.
3. Test database is strictly confirmed to be 'gramsetu_test'.
4. Basic ORM / database queries execute successfully under test runner privileges.
"""

from django.test import TestCase
from django.db import connection
from django.conf import settings


class FoundationSmokeTest(TestCase):
    def test_environment_and_settings_loaded(self):
        """Verify core settings are loaded without error."""
        self.assertIsNotNone(settings.SECRET_KEY)
        self.assertIn('gramsetu_test', settings.DATABASES['default']['NAME'])
        self.assertEqual(settings.LANGUAGE_CODE, 'mr')
        self.assertEqual(settings.TIME_ZONE, 'Asia/Kolkata')

    def test_active_database_is_strictly_gramsetu_test(self):
        """Verify via direct SQL query that active connection is strictly to gramsetu_test."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            current_db = cursor.fetchone()[0]
            self.assertEqual(
                current_db,
                'gramsetu_test',
                f"SAFETY CHECK FAILED: Connected to '{current_db}' instead of 'gramsetu_test'"
            )

    def test_current_database_user_is_test_runner(self):
        """Verify that the test runner executes as gramsetu_test_runner."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user;")
            current_user = cursor.fetchone()[0]
            self.assertEqual(
                current_user,
                'gramsetu_test_runner',
                f"SAFETY CHECK FAILED: Connected as '{current_user}' instead of 'gramsetu_test_runner'"
            )

    def test_basic_sql_execution(self):
        """Verify arithmetic query execution on test database."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 + 1;")
            result = cursor.fetchone()[0]
            self.assertEqual(result, 2)
