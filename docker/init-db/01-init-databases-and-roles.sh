#!/bin/sh
set -e

DEV_DB="${DEV_DB_NAME:-gramsetu_dev}"
TEST_DB="${TEST_DB_NAME:-gramsetu_test}"
APP_USER="${APP_DB_USER:-gramsetu_app}"
MIGRATOR_USER="${MIGRATOR_DB_USER:-gramsetu_migrator}"
TEST_USER="${TEST_DB_USER:-gramsetu_test_runner}"
BACKUP_USER="${BACKUP_DB_USER:-gramsetu_backup}"

echo ">>> [GramSetu] Initializing databases and least-privilege roles..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- 1. Create Databases
    CREATE DATABASE "$DEV_DB";
    CREATE DATABASE "$TEST_DB";

    -- 2. Revoke default connection privileges from PUBLIC
    REVOKE CONNECT ON DATABASE "$DEV_DB" FROM PUBLIC;
    REVOKE CONNECT ON DATABASE "$TEST_DB" FROM PUBLIC;

    -- 3. Create least-privilege roles
    CREATE ROLE "$APP_USER" WITH LOGIN PASSWORD '$APP_DB_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    CREATE ROLE "$MIGRATOR_USER" WITH LOGIN PASSWORD '$MIGRATOR_DB_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
    CREATE ROLE "$TEST_USER" WITH LOGIN PASSWORD '$TEST_DB_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
    CREATE ROLE "$BACKUP_USER" WITH LOGIN PASSWORD '$BACKUP_DB_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT;
EOSQL

echo ">>> [GramSetu] Configuring permissions on $DEV_DB..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DEV_DB" <<-EOSQL
    -- Revoke public create on schema public
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;

    -- Schema ownership and DDL rights to migrator
    ALTER SCHEMA public OWNER TO "$MIGRATOR_USER";
    GRANT ALL ON SCHEMA public TO "$MIGRATOR_USER";

    -- Grant database connection rights
    GRANT CONNECT ON DATABASE "$DEV_DB" TO "$MIGRATOR_USER";
    GRANT CONNECT ON DATABASE "$DEV_DB" TO "$APP_USER";
    GRANT CONNECT ON DATABASE "$DEV_DB" TO "$BACKUP_USER";

    -- Runtime application privileges (Usage only on schema public; NO CREATE)
    GRANT USAGE ON SCHEMA public TO "$APP_USER";
    REVOKE CREATE ON SCHEMA public FROM "$APP_USER";

    -- Backup role privileges (Usage on schema public and pg_read_all_data with inheritance)
    GRANT USAGE ON SCHEMA public TO "$BACKUP_USER";
    GRANT pg_read_all_data TO "$BACKUP_USER" WITH INHERIT TRUE;

    -- Default privileges for future tables/sequences created by migrator
    ALTER DEFAULT PRIVILEGES FOR ROLE "$MIGRATOR_USER" IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$APP_USER";

    ALTER DEFAULT PRIVILEGES FOR ROLE "$MIGRATOR_USER" IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO "$APP_USER";
EOSQL

echo ">>> [GramSetu] Configuring permissions on $TEST_DB..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$TEST_DB" <<-EOSQL
    -- Revoke public create on schema public
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;

    -- Schema ownership and full DDL/DML rights to test runner
    ALTER SCHEMA public OWNER TO "$TEST_USER";
    GRANT ALL ON SCHEMA public TO "$TEST_USER";

    -- Grant database connection rights to test runner
    GRANT CONNECT ON DATABASE "$TEST_DB" TO "$TEST_USER";

    -- Explicitly prevent runtime app and migrator from connecting to test db
    REVOKE ALL ON DATABASE "$TEST_DB" FROM "$APP_USER";
    REVOKE ALL ON DATABASE "$TEST_DB" FROM "$MIGRATOR_USER";
    REVOKE ALL ON DATABASE "$TEST_DB" FROM "$BACKUP_USER";

    -- Default privileges for test runner
    ALTER DEFAULT PRIVILEGES FOR ROLE "$TEST_USER" IN SCHEMA public
        GRANT ALL ON TABLES TO "$TEST_USER";

    ALTER DEFAULT PRIVILEGES FOR ROLE "$TEST_USER" IN SCHEMA public
        GRANT ALL ON SEQUENCES TO "$TEST_USER";
EOSQL

echo ">>> [GramSetu] Database initialization completed successfully."
