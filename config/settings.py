"""
Django settings for GramSetu project.

Configured for local PostgreSQL 16 foundation with least-privilege role separation:
- Runtime application role (gramsetu_app): DML only
- Schema migration role (gramsetu_migrator): DDL and schema ownership
- Test runner role (gramsetu_test_runner): Restricted to test database
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')


# ------------------------------------------------------------------------------
# Core Security Settings
# ------------------------------------------------------------------------------

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError(
        "CRITICAL CONFIGURATION ERROR: 'DJANGO_SECRET_KEY' environment variable is missing. "
        "Define it in your local .env file."
    )

DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in ('true', '1', 't')

allowed_hosts_str = os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,testserver')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(',') if host.strip()]


# ------------------------------------------------------------------------------
# Application Definition & Architectural Domains
# ------------------------------------------------------------------------------

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

# 12 Domain Apps establishing clear architectural module boundaries
LOCAL_APPS = [
    'apps.core',            # Core infrastructure, health/readiness, error handlers
    'apps.content',         # Future informational pages and content revision management
    'apps.notices',         # Future announcements, notices, effective dates, and expiry
    'apps.documents',       # Future document metadata, file access controls, disclosure
    'apps.events',          # Future meetings and events
    'apps.schemes',         # Future government schemes and official links
    'apps.gallery',         # Future approved public photographs and media metadata
    'apps.search',          # Future unified search across approved public information
    'apps.audit',           # Future immutable application audit-event recording
    'apps.governance',      # Future publishing approval and publication-state coordination
    'apps.site_config',     # Future navigation, themes, homepage, public-site settings
    'apps.identity',        # Future invitation-only CMS accounts, role permissions
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

# Custom User Model (Email-based identity in apps.identity)
AUTH_USER_MODEL = 'identity.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ------------------------------------------------------------------------------
# Database & Least-Privilege Role Configuration
# ------------------------------------------------------------------------------

# Operational mode detection
IS_TESTING = 'test' in sys.argv or os.getenv('APP_ENV') == 'test'
DB_ROLE = os.getenv('DB_ROLE', 'app').lower()

DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = os.getenv('DB_PORT', '5433')

if IS_TESTING:
    # Test Mode: Connects strictly to gramsetu_test using gramsetu_test_runner
    ACTIVE_DB_NAME = os.getenv('TEST_DB_NAME', 'gramsetu_test')
    ACTIVE_DB_USER = os.getenv('TEST_DB_USER', 'gramsetu_test_runner')
    ACTIVE_DB_PASSWORD = os.getenv('TEST_DB_PASSWORD')
    if not ACTIVE_DB_PASSWORD:
        raise RuntimeError("CRITICAL CONFIGURATION ERROR: 'TEST_DB_PASSWORD' environment variable is missing.")
elif DB_ROLE == 'migrator':
    # Migration Mode: Connects to gramsetu_dev using gramsetu_migrator (schema owner)
    ACTIVE_DB_NAME = os.getenv('DEV_DB_NAME', 'gramsetu_dev')
    ACTIVE_DB_USER = os.getenv('MIGRATOR_DB_USER', 'gramsetu_migrator')
    ACTIVE_DB_PASSWORD = os.getenv('MIGRATOR_DB_PASSWORD')
    if not ACTIVE_DB_PASSWORD:
        raise RuntimeError("CRITICAL CONFIGURATION ERROR: 'MIGRATOR_DB_PASSWORD' environment variable is missing.")
elif DB_ROLE == 'app':
    # Runtime Application Mode: Connects to gramsetu_dev using gramsetu_app (DML only)
    ACTIVE_DB_NAME = os.getenv('DEV_DB_NAME', 'gramsetu_dev')
    ACTIVE_DB_USER = os.getenv('APP_DB_USER', 'gramsetu_app')
    ACTIVE_DB_PASSWORD = os.getenv('APP_DB_PASSWORD')
    if not ACTIVE_DB_PASSWORD:
        raise RuntimeError("CRITICAL CONFIGURATION ERROR: 'APP_DB_PASSWORD' environment variable is missing.")
else:
    raise RuntimeError(
        f"CRITICAL CONFIGURATION ERROR: Invalid DB_ROLE '{DB_ROLE}'. "
        f"Permitted values are 'app' (normal runtime) or 'migrator' (schema migrations)."
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': ACTIVE_DB_NAME,
        'USER': ACTIVE_DB_USER,
        'PASSWORD': ACTIVE_DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'TEST': {
            'NAME': os.getenv('TEST_DB_NAME', 'gramsetu_test'),
        },
    }
}

# Enforce custom test runner with active database verification
TEST_RUNNER = 'config.test_runner.GramSetuTestRunner'


# ------------------------------------------------------------------------------
# Logging Conventions
# ------------------------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} [{name}:{lineno}] {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose' if DEBUG else 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'gramsetu': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}


# ------------------------------------------------------------------------------
# Password Validation
# ------------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ------------------------------------------------------------------------------
# Internationalization (Maharashtra Gram Panchayat: Marathi Default)
# ------------------------------------------------------------------------------

LANGUAGE_CODE = 'mr'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_TZ = True


# ------------------------------------------------------------------------------
# Static Files & Storage
# ------------------------------------------------------------------------------

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
