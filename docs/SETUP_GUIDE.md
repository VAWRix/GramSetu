# GramSetu — Local Development Setup & Execution Guide

**Project Title:** GramSetu – A Digital Gram Panchayat Information and Governance Portal  
**Anchor Village:** Narayangaon Gram Panchayat (LGD Code: `549493`, Paithan, Chhatrapati Sambhajinagar, Maharashtra)  

---

## 1. Prerequisites & Required Software

| Software | Minimum Version | Purpose |
|:---|:---|:---|
| **Python** | 3.11+ | Backend Django framework, psycopg2 adapter, and OTP CLI commands |
| **Node.js** | 20+ (LTS) | Frontend Next.js 16, React 19, and Tailwind CSS v4 |
| **Docker Desktop** | 26+ | PostgreSQL 16 Alpine containerized database isolation |

---

## 2. Environment Configuration

1. Copy the example configuration template:
   ```powershell
   copy .env.example .env
   ```
2. Configure your local passwords and secrets in `.env`:
   - `DJANGO_SECRET_KEY`: Random 50+ character string.
   - `BOOTSTRAP_DB_PASSWORD`: Password for `postgres` superuser.
   - `APP_DB_PASSWORD`: Password for runtime DML role `gramsetu_app`.
   - `MIGRATOR_DB_PASSWORD`: Password for migration DDL role `gramsetu_migrator`.
   - `TEST_DB_PASSWORD`: Password for test runner role `gramsetu_test_runner`.
   - `BACKUP_DB_PASSWORD`: Password for backup role `gramsetu_backup`.

---

## 3. Database Setup & Initialization

1. Start the PostgreSQL 16 Docker container:
   ```powershell
   docker compose up -d
   ```
   *Verify container health*:
   ```powershell
   docker ps --filter "name=gramsetu-postgres"
   ```

2. Apply database migrations using the schema owner role (`gramsetu_migrator`):
   ```powershell
   # PowerShell:
   $env:DB_ROLE="migrator"
   .venv\Scripts\python.exe manage.py migrate
   Remove-Item env:DB_ROLE

   # Bash / Linux:
   DB_ROLE=migrator python manage.py migrate
   ```

3. Seed initial testing accounts and trilingual village knowledge data:
   ```powershell
   .venv\Scripts\python.exe manage.py seed_testing_accounts
   .venv\Scripts\python.exe scripts/sync_trilingual_knowledge.py
   ```

---

## 4. Backend Setup & Startup

1. Create and activate a Python 3.11 virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

2. Start the Django backend development server (Port 8000):
   ```powershell
   .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
   ```

3. Health check verification:
   - **Liveness probe**: `http://127.0.0.1:8000/health/`
   - **Readiness probe**: `http://127.0.0.1:8000/ready/`

---

## 5. Frontend Setup & Startup

1. Install Node.js dependencies:
   ```powershell
   cd frontend
   npm install
   ```

2. Start the Next.js development server (Port 3005):
   ```powershell
   npx next dev -p 3005
   ```

3. Access the portals:
   - **Citizen Public Portal**: `http://localhost:3005`
   - **Staff Administrative CMS**: `http://localhost:3005/cms`

---

## 6. Development OTP Commands

In development (`settings.DEBUG == True`), retrieve single-use MFA codes directly from the terminal without external SMTP:

```powershell
# Super Admin OTP (Gramsevak)
.venv\Scripts\python.exe manage.py superadmin_otp

# Operator OTP (Computer Operator)
.venv\Scripts\python.exe manage.py operator_otp

# Raw 6-digit code for rapid copy-paste
.venv\Scripts\python.exe manage.py superadmin_otp --raw
```

---

## 7. Future Scope

The following components are planned for future development milestones and are not currently implemented:

- **Android Mobile Application**: Development of a dedicated Android mobile application to extend GramSetu's accessibility to smartphone users.
