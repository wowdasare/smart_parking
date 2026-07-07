"""
Django settings for atuparking project.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/6.0/ref/settings/
"""

from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
)
# Reads a .env file at the project root if present; all values below can be
# overridden there without touching this file (see .env.example).
environ.Env.read_env(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY', default='django-insecure-0k(u5vkmjpnvd%qh9w%ywa7)rl1p165dz377y3$5o-7lwkyg90')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DEBUG', default=True)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    'rest_framework',

    # Local apps
    'accounts',
    'vehicles',
    'reservations',
    'parking',
    'notifications',
    'dashboard',
    'permits',
    'sensors',
]

# DRF: default-deny unless a view explicitly opts in to something else. The
# sensor endpoints below set their own authentication_classes/permission_classes
# (device API key, not session/user), rather than relying on these defaults.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'atuparking.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Project-level templates (base.html, home page, shared partials) live in
        # BASE_DIR/templates. Each app also has its own templates/<app_name>/ dir
        # (APP_DIRS=True below) for app-specific pages, e.g. accounts/templates/accounts/login.html.
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'atuparking.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
#
# Controlled by the DB_ENGINE env var: 'sqlite' (default, zero setup) or
# 'mysql' (production target). To switch to MySQL, install the system MySQL
# client libraries, `pip install mysqlclient`, set DB_ENGINE=mysql and the
# DB_* vars in your .env, then rerun migrate.

if env('DB_ENGINE', default='sqlite') == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': env('DB_NAME', default='atuparking'),
            'USER': env('DB_USER', default='root'),
            'PASSWORD': env('DB_PASSWORD', default=''),
            'HOST': env('DB_HOST', default='localhost'),
            'PORT': env('DB_PORT', default='3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Custom user model (accounts app) — must be set before the first migration.
AUTH_USER_MODEL = 'accounts.User'


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


# Authentication redirects

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'home'


# Map Django's message levels to Bootstrap 5 alert classes (alert-<tag>).
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

# Accra Technical University is in Ghana (GMT, no DST).
TIME_ZONE = 'Africa/Accra'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (user-uploaded vehicle photos, permit documents, etc.)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# A sensor device is considered "offline" in the admin if it hasn't reported
# in this many minutes. Purely a display/filter threshold — nothing else
# depends on it.
SENSOR_OFFLINE_THRESHOLD_MINUTES = env.int('SENSOR_OFFLINE_THRESHOLD_MINUTES', default=10)

# When security/admin staff manually set a slot's status, sensor reports that
# conflict with it are deferred (rejected, but logged) for this many minutes
# — trusts the person on the ground over a possibly-misfiring sensor, but
# only temporarily; after this window, sensor reports resume taking priority.
MANUAL_OVERRIDE_GRACE_MINUTES = env.int('MANUAL_OVERRIDE_GRACE_MINUTES', default=15)


# Email (SMTP) — used by the notifications app for booking/status alerts.
# Falls back to printing emails to the console in DEBUG so local dev needs no
# real SMTP credentials. Set EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD in
# .env for real delivery (e.g. Gmail SMTP, SendGrid, etc.).
if DEBUG and not env('EMAIL_HOST', default=''):
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
    EMAIL_PORT = env.int('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='ATU Smart Parking <noreply@atuparking.local>')
