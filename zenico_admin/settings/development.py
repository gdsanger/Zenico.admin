"""
Development settings for zenico_admin project.
"""

from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']


# Development-specific apps
INSTALLED_APPS += [
    # Add development-specific apps here
]


# Database
# Override if needed for local development
# DATABASES['default']['NAME'] = BASE_DIR / 'db_dev.sqlite3'


# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# Django Debug Toolbar settings (if installed)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']
