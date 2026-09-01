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
        # Пробуем загрузить .env явно из корня проекта
        from decouple import Config, RepositoryEnv
        env_path = BASE_DIR / '.env'
        if env_path.exists():
            config_env = Config(RepositoryEnv(str(env_path)))
            if cast is not None:
                return config_env(key, default=default, cast=cast)
            return config_env(key, default=default)
        
        if cast is not None:
            return config(key, default=default, cast=cast)
        return config(key, default=default)
    val = os.environ.get(key, default)
    if cast and val is not None:
        return cast(val)
    return val


SECRET_KEY = _cfg(
    'SECRET_KEY',
    default='django-insecure-CHANGE-ME-in-production!'
)

DEBUG = _cfg('DEBUG', default=True, cast=bool)

_allowed = _cfg('ALLOWED_HOSTS', default='localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# CSRF & Session Security for Production
CSRF_TRUSTED_ORIGINS = ['https://ezapis.pythonanywhere.com']
SESSION_COOKIE_SECURE = not DEBUG  # False on localhost (HTTP), True on production (HTTPS)
CSRF_COOKIE_SECURE = not DEBUG    # False on localhost (HTTP), True on production (HTTPS)
CSRF_COOKIE_HTTPONLY = False  # Allows JS to read the cookie if needed for AJAX
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# ─── Приложения ───────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Required by allauth

    # Наши приложения
    'accounts',   # Аутентификация и пользователи
    'queue_app',  # Очереди, услуги, специалисты

    # API и интеграции
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Static files (production)
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # i18n
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

STATICFILES_STORAGE = (
    'whitenoise.storage.CompressedStaticFilesStorage'
    if DEBUG
    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
)

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

# ─── База данных (PostgreSQL / SQLite fallback) ───────────────────────────────
_db_url = _cfg('DATABASE_URL', default='')
if _db_url:
    try:
        import dj_database_url
        DATABASES = {'default': dj_database_url.parse(_db_url, conn_max_age=600)}
    except ImportError:
        import warnings
        warnings.warn('dj-database-url not installed, falling back to SQLite')
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
else:
    # Localhost SQLite (development)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ─── Кастомная модель пользователя ────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.CustomUser'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# ─── Django Sites Framework ───────────────────────────────────────────────────
SITE_ID = 1

# ─── Allauth Configuration ────────────────────────────────────────────────────
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'http' if DEBUG else 'https'
ACCOUNT_EMAIL_SUBJECT_PREFIX = '[MedZapis] '
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_ADAPTER = 'accounts.adapter.RobustSocialAccountAdapter'
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
        'APP': {
            'client_id': _cfg('GOOGLE_CLIENT_ID', default=''),
            'secret': _cfg('GOOGLE_CLIENT_SECRET', default=''),
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
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ─── Медиафайлы (фото специалистов) ──────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Редиректы после входа/выхода ─────────────────────────────────────────────
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ─── Email (Gmail SMTP) ───────────────────────────────────────────────────────
EMAIL_BACKEND = _cfg('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = _cfg('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = _cfg('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_TLS = _cfg('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_USE_SSL = _cfg('EMAIL_USE_SSL', default=True, cast=bool)
EMAIL_HOST_USER = _cfg('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = _cfg('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = _cfg('DEFAULT_FROM_EMAIL', default='akunaliuulumirlan@gmail.com')

# ─── Сообщения — маппинг тегов ────────────────────────────────────────────────
from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000  

# ─── Динамическое подключение (Survival Mode) ──────────────────────────────────
# Daphne, Allauth and Channels are loaded safely for compatibility
try:
    import daphne
    if 'daphne' not in INSTALLED_APPS:
        INSTALLED_APPS.insert(0, 'daphne')
except ImportError:
    pass

try:
    import allauth
    if 'allauth' not in INSTALLED_APPS:
        INSTALLED_APPS += [
            'allauth',
            'allauth.account',
            'allauth.socialaccount',
            'allauth.socialaccount.providers.google',
        ]
    # Add allauth middleware and backend dynamically
    if 'allauth.account.middleware.AccountMiddleware' not in MIDDLEWARE:
        MIDDLEWARE.insert(6, 'allauth.account.middleware.AccountMiddleware')
    if 'allauth.account.auth_backends.AuthenticationBackend' not in AUTHENTICATION_BACKENDS:
        AUTHENTICATION_BACKENDS.append('allauth.account.auth_backends.AuthenticationBackend')
    
    # Use robust adapter to prevent MultipleObjectsReturned errors
    SOCIALACCOUNT_ADAPTER = 'accounts.adapter.RobustSocialAccountAdapter'
except ImportError:
    pass

try:
    import channels
    if 'channels' not in INSTALLED_APPS:
        INSTALLED_APPS.append('channels')
except ImportError:
    pass

# ─── Django REST Framework & CORS ──────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
}

# Production-до DEBUG=False болгондо CORS_ALLOW_ALL_ORIGINS=False болот
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = [
        h for h in [
            f'https://{host}' for host in ALLOWED_HOSTS
            if host not in ('localhost', '127.0.0.1', '*')
        ]
    ]

# ─── Logging ──────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO' if DEBUG else 'WARNING',
            'propagate': False,
        },
        'queue_app': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}