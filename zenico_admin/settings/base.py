"""
Base Django settings for zenico_admin project.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-ni$3tm!li_m92-^w1zg#^mj&v@)0fw5*@-&1w^7&tjc*3^!*xj')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',') if os.getenv('ALLOWED_HOSTS') else []

# Token for the internal zenico-provisioner agent (Authorization: Bearer <token>)
PROVISIONING_AGENT_TOKEN = os.getenv('PROVISIONING_AGENT_TOKEN', '')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    'rest_framework',
    'corsheaders',
    'django_htmx',
    'django_bootstrap5',
    # Local apps
    'accounts',
    'customers',
    'instances',
    'billing',
    'audit',
    'core',
    'ui',
    'crm',
    'newsletter',
    'ai',
    'orders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'zenico_admin.urls'

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
                'ui.context_processors.alert_count',
                'ui.context_processors.pending_education_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'zenico_admin.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': dj_database_url.config(
        default=os.getenv('DATABASE_URL', 'sqlite:///db.sqlite3'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}


# Custom User Model
AUTH_USER_MODEL = 'accounts.AdminUser'


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Login URL
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'


# Default primary key field type
# https://docs.djangoproject.com/en/6.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# CORS Configuration
CORS_ALLOWED_ORIGINS = [
    "https://zenico.app",
]
CORS_URLS_REGEX = r"^/api/.*"


# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
    'UNAUTHENTICATED_USER': None,
}

# django-ratelimit
RATELIMIT_ENABLE = os.getenv('RATELIMIT_ENABLE', 'True') == 'True'


# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Celery Beat Schedule
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'process-sequence-enrollments': {
        'task': 'newsletter.tasks.process_sequence_enrollments',
        'schedule': crontab(minute=0),  # Every hour
    },
    'send-scheduled-campaigns': {
        'task': 'newsletter.tasks.send_scheduled_campaigns',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
    'cleanup-old-heartbeats': {
        'task': 'instances.tasks.cleanup_old_heartbeats',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2:00 AM
    },
    'process-cancellations': {
        'task': 'instances.tasks.process_cancellations',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6:00 AM
    },
}


# Mail Settings
MAIL_FROM_ADDRESS = os.getenv('MAIL_FROM_ADDRESS', 'noreply@zenico.app')
MAIL_FROM_NAME = os.getenv('MAIL_FROM_NAME', 'Zenico')
ADMIN_NOTIFICATION_EMAIL = os.getenv('ADMIN_NOTIFICATION_EMAIL', 'team@zenico.app')
ADMIN_BASE_URL = os.getenv('ADMIN_BASE_URL', 'https://admin.zenico.app')
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'https://zenico.app')

# Absolute URL of the Zenico-Wordmark-PNG für den Mail-Header (Outlook kann kein SVG rendern).
# Liegt als statisches Asset in Zenico.web; als Setting zentral, damit kein Template die URL hart verdrahtet.
MAIL_LOGO_URL = os.getenv('MAIL_LOGO_URL', f'{FRONTEND_BASE_URL}/static/img/zenico-logo.png')

# Order checkout redirect URLs (zeigen auf Zenico.web)
ORDER_SUCCESS_URL = os.getenv(
    'ORDER_SUCCESS_URL', f'{FRONTEND_BASE_URL}/bestellung/erfolg/?session_id={{CHECKOUT_SESSION_ID}}'
)
ORDER_CANCEL_URL = os.getenv('ORDER_CANCEL_URL', f'{FRONTEND_BASE_URL}/bestellung/abbruch/')


# Field Encryption
# Used for encrypting sensitive fields like Stripe API keys
# Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY', '')


# Stripe Configuration
STRIPE_AI_ADDON_PRICE_ID = os.getenv('STRIPE_AI_ADDON_PRICE_ID', '')


# AI Provider Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
AI_DEFAULT_PROVIDER = os.getenv('AI_DEFAULT_PROVIDER', 'anthropic')


# Logging Configuration
# Ensure logs directory exists
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'level': 'DEBUG',
        },
        'daily_file': {
            'class': 'core.logging_utils.DailyRotatingFileHandler',
            'filename': str(LOGS_DIR / 'app.log'),
            'when': 'midnight',
            'interval': 1,
            'backupCount': 7,
            'formatter': 'verbose',
            'level': 'DEBUG',
        },
    },
    'root': {
        'handlers': ['console', 'daily_file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'daily_file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'daily_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console', 'daily_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# Sentry Configuration
# Only initialize Sentry if SENTRY_DSN is provided
SENTRY_DSN = os.getenv('SENTRY_DSN', '')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
        ],
        # Set traces_sample_rate to 1.0 to capture 100% of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),

        # If you wish to associate users to errors (assuming you are using
        # django.contrib.auth) you may enable sending PII data.
        send_default_pii=True,

        # Environment name
        environment=os.getenv('SENTRY_ENVIRONMENT', 'production' if not DEBUG else 'development'),
    )
