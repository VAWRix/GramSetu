"""
GramSetu Custom Test Runner

Enforces strict database isolation and safety guardrails:
1. Verifies that the configured database is exclusively 'gramsetu_test'.
2. Verifies via SQL query ('SELECT current_database();') that the active connection
   is connected to 'gramsetu_test'.
3. Automatically sets keepdb=True to operate within the pre-provisioned least-privilege
   test database without attempting unauthorized CREATE DATABASE / DROP DATABASE operations.
4. Prevents test execution and teardown if any non-test database is detected.
"""

from django.test.runner import DiscoverRunner
from django.db import connection


class GramSetuTestRunner(DiscoverRunner):
    def __init__(self, *args, **kwargs):
        # Default keepdb to True since gramsetu_test is pre-provisioned with NOCREATEDB role
        if 'keepdb' not in kwargs or not kwargs['keepdb']:
            kwargs['keepdb'] = True
        super().__init__(*args, **kwargs)

    def setup_databases(self, **kwargs):
        configured_db = connection.settings_dict.get('NAME')
        if configured_db != 'gramsetu_test':
            raise RuntimeError(
                f"FATAL SAFETY VIOLATION: Test suite configured to run against '{configured_db}', "
                f"expected 'gramsetu_test'. Aborting immediately to prevent data corruption."
            )

        # Execute standard setup with keepdb=True
        old_config = super().setup_databases(**kwargs)

        # Post-setup active database verification
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            current_db = cursor.fetchone()[0]
            if current_db != 'gramsetu_test':
                raise RuntimeError(
                    f"FATAL SAFETY VIOLATION: Active connection is to database '{current_db}', "
                    f"expected 'gramsetu_test'. Aborting immediately."
                )

        return old_config

    def teardown_databases(self, old_config, **kwargs):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            current_db = cursor.fetchone()[0]
            if current_db != 'gramsetu_test':
                raise RuntimeError(
                    f"FATAL SAFETY VIOLATION: Teardown targeted non-test database '{current_db}'! "
                    f"Aborting immediately."
                )
        return super().teardown_databases(old_config, **kwargs)
