from pathlib import Path
import os

try:
    from decouple import config
    _USE_DECOUPLE = True
except ImportError:
    _USE_DECOUPLE = False

BASE_DIR = Path(__file__).resolve().parent.parent


def _cfg(key, default=None, cast=None):
    """Читает из .env через decouple, иначе из os.environ или default."""
    if _USE_DECOUPLE:
        if cast is not None:
            return config(key, default=default, cast=cast)
        return config(key, default=default)
    val = os.environ.get(key, default)
    if cast and val is not None:
        return cast(val)
    return val


SECRET_KEY = _cfg(
    'SECRET_KEY',
    default='django-insecure-clinic-queue-secret-key-change-in-production-2024'
)

ALLOWED_HOSTS = ['ezapis.pythonanywhere.com', 'localhost', '127.0.0.1', '*']
DEBUG = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ─── Приложения ───────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'daphne',  # Must be FIRST for ASGI
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Required by allauth

    # Third-party
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'channels',

    # Наши приложения
    'accounts',   # Аутентификация и пользователи
    'queue_app',  # Очереди, услуги, специалисты
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # i18n
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',  # allauth
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'clinic_queue.urls'

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
                'queue_app.context_processors.notification_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'clinic_queue.wsgi.application'

# ─── База данных (SQLite) ──────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ─── Кастомная модель пользователя ────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.CustomUser'

# ─── Authentication backends (allauth) ───────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# ─── Django Sites Framework ───────────────────────────────────────────────────
SITE_ID = 1

# ─── Allauth Configuration ────────────────────────────────────────────────────
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'http' if DEBUG else 'https'  # Dynamic protocol for OAuth redirects
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[MedZapis] '
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
        'APP': {
            'client_id': _cfg('GOOGLE_CLIENT_ID', default=''),
            'secret': _cfg('GOOGLE_CLIENT_SECRET', default=''),
            'key': ''
        }
    }
}

# ─── Channels (WebSockets Real-Time) ─────────────────────────────────────────
ASGI_APPLICATION = 'clinic_queue.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}

# ─── Пароли ───────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Локализация ──────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Asia/Bishkek'
USE_I18N = True
USE_TZ = True
LANGUAGES = [
    ('ru', 'Русский'),
    ('ky', 'Кыргызча'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

# ─── Статические файлы ────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ─── Медиафайлы (фото специалистов) ──────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Редиректы после входа/выхода ─────────────────────────────────────────────
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ─── Email (консоль для разработки) ───────────────────────────────────────────
EMAIL_BACKEND = _cfg('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = _cfg('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = _cfg('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = _cfg('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = _cfg('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = _cfg('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = _cfg('DEFAULT_FROM_EMAIL', default='noreply@medzapis.kg')

# ─── Сообщения — маппинг тегов ────────────────────────────────────────────────
from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000  