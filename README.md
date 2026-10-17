# GramSetu — Project Foundation (Milestone 1)

Official information portal and administrative platform foundation for Gram Panchayats in Maharashtra, India.

---

## 1. Architecture Overview

- **Backend Framework:** Python 3.11 & Django 5.2 LTS (`Django==5.2.18`) (Monolith with Django Templates)
- **Database Engine:** PostgreSQL 16 (`postgres:16-alpine`)
- **Default Locale:** Marathi (`mr`), Timezone: `Asia/Kolkata`
- **Isolation Boundary:**
  - Dedicated Docker Compose service: `gramsetu-postgres`
  - Host Port Binding: `127.0.0.1:5433:5432` (strictly IPv4 loopback)
  - Dedicated Volume: `gramsetu_pgdata`
  - Dedicated Network: `gramsetu-net`

---

## 2. Least-Privilege Database Role Model

| Role Identifier | Environment Variable | Granted Capabilities | Security Boundaries |
| :--- | :--- | :--- | :--- |
| **`postgres`** | `BOOTSTRAP_DB_USER` | Initial cluster bootstrap & role creation. | Used **exclusively** during first initialization. Never used by Django. |
| **`gramsetu_migrator`** | `MIGRATOR_DB_USER` | Schema owner in `gramsetu_dev`; DDL execution (`CREATE/ALTER/DROP TABLE`). | Used **only** when applying migrations via `DB_ROLE=migrator`. |
| **`gramsetu_app`** | `APP_DB_USER` | Runtime DML (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) on tables in `gramsetu_dev`. | **No DDL permissions.** `REVOKE CREATE ON SCHEMA public`. Cannot connect to `gramsetu_test`. |
| **`gramsetu_test_runner`**| `TEST_DB_USER` | DDL & DML permissions restricted exclusively to `gramsetu_test`. | `NOCREATEDB`. **Strictly revoked** from connecting to `gramsetu_dev`. |
| **`gramsetu_backup`** | `BACKUP_DB_USER` | `pg_read_all_data` + `USAGE ON SCHEMA public` in `gramsetu_dev`. | Read-only access for `pg_dump`. Cannot alter or delete data. |

---

## 3. Getting Started & Local Setup

### 3.1 Prerequisites
- Python 3.11+
- Docker Desktop (with Linux engine active)
- Git

### 3.2 Setup Environment & Dependencies
```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Provision local environment secrets
copy .env.example .env
# Edit .env with your local secure development credentials
```

---

## 4. Operational Commands

### 4.1 Starting the PostgreSQL Service
```powershell
docker compose up -d
```
Verify the container is healthy:
```powershell
docker ps --filter "name=gramsetu-postgres"
```

### 4.2 Applying Database Migrations (Schema Owner Role)
Migrations must be executed using the schema migration role (`gramsetu_migrator`):
```powershell
# PowerShell:
$env:DB_ROLE="migrator"; python manage.py migrate; Remove-Item env:DB_ROLE

# Bash / Linux:
DB_ROLE=migrator python manage.py migrate
```

### 4.3 Running Automated Tests (Test Runner Role)
Tests automatically target `gramsetu_test` using `gramsetu_test_runner` and enforce active database validation:
```powershell
python manage.py test
```

### 4.4 Running Local Backups (Least-Privilege Backup Role)
Executes a verified, consistent logical backup (`pg_dump -Fc`) to the host `backups/` directory:
```powershell
python scripts/backup.py
```
This utility:
1. Streams custom-format backup non-interactively to a `.tmp` file.
2. Validates exit status and minimum file size (> 1KB).
3. Verifies archive Table of Contents structure via `pg_restore --list`.
4. Computes SHA-256 cryptographic digest.
5. Atomically commits the backup file (`.dump`) and writes `<filename>.dump.sha256`.

### 4.5 Stopping the Database Service
```powershell
# Gracefully stop containers without touching persistent volume
docker compose down

# Or pause containers:
docker compose stop
```

---

## 5. Critical Data Safety Warnings

> [!CAUTION]
> **PROHIBITED COMMANDS — PERMANENT DATA DESTRUCTION:**
> - **`docker compose down -v`**: The `-v` flag permanently removes the `gramsetu_pgdata` named volume, destroying all development and test data. **NEVER run `docker compose down -v`.**
> - **`docker volume rm gramsetu_pgdata`**: Deletes the database volume.
> - **`docker volume prune` / `docker system prune --volumes`**: Unconditionally deletes unattached volumes.
