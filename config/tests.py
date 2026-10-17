"""
GramSetu Foundation Smoke & Database Isolation Tests

Verifies:
1. Django environment and settings load correctly.
2. Active test database connection is operational.
3. Test database is strictly confirmed to be 'gramsetu_test'.
4. Basic ORM / database queries execute successfully under test runner privileges.
5. Proof that gramsetu_test_runner CANNOT connect to gramsetu_dev (PostgreSQL permission denied).
6. Proof that destructive DDL/DML operations in test suite are confined strictly to gramsetu_test.
"""

import os
import psycopg2
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

    def test_test_runner_cannot_connect_to_dev_database(self):
        """Negative test proving test runner role is blocked from connecting to gramsetu_dev."""
        db_host = settings.DATABASES['default']['HOST']
        db_port = settings.DATABASES['default']['PORT']
        test_user = settings.DATABASES['default']['USER']
        test_pass = settings.DATABASES['default']['PASSWORD']
        dev_db_name = os.getenv('DEV_DB_NAME', 'gramsetu_dev')

        with self.assertRaises(psycopg2.OperationalError) as ctx:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                dbname=dev_db_name,
                user=test_user,
                password=test_pass
            )
            conn.close()

        self.assertIn(
            f'permission denied for database "{dev_db_name}"',
            str(ctx.exception),
            "Expected PostgreSQL permission denied error when test runner targets development database."
        )

    def test_destructive_operations_confined_to_test_db(self):
        """Verify that DDL/DML teardown and table operations run cleanly in test DB without affecting dev DB."""
        with connection.cursor() as cursor:
            # 1. Verify active DB is gramsetu_test
            cursor.execute("SELECT current_database();")
            self.assertEqual(cursor.fetchone()[0], 'gramsetu_test')

            # 2. Perform DDL: Create temporary fixture table in test db
            cursor.execute("CREATE TABLE test_isolation_fixture (id serial primary key, name varchar(50));")
            cursor.execute("INSERT INTO test_isolation_fixture (name) VALUES ('isolation_check');")

            # 3. Perform DML: Verify insertion and truncate
            cursor.execute("SELECT count(*) FROM test_isolation_fixture;")
            self.assertEqual(cursor.fetchone()[0], 1)

            cursor.execute("TRUNCATE TABLE test_isolation_fixture;")
            cursor.execute("SELECT count(*) FROM test_isolation_fixture;")
            self.assertEqual(cursor.fetchone()[0], 0)

            # 4. Teardown: Drop fixture table
            cursor.execute("DROP TABLE test_isolation_fixture;")
