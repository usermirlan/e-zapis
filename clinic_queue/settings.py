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

DEBUG = _cfg('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = ['*']

# ─── Приложения ───────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Наши приложения
    'accounts',   # Аутентификация и пользователи
    'queue_app',  # Очереди, услуги, специалисты
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
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

# ─── Пароли ───────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Локализация ──────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Asia/Almaty'
USE_I18N = True
USE_TZ = True

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
EMAIL_BACKEND = _cfg(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend'
)
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