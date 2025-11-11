import os
from pathlib import Path
import environ
import cloudinary
import dj_database_url
from django.core.exceptions import ImproperlyConfigured


# =========================
# BASE DIRECTORY & ENV SETUP
# =========================
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    DJANGO_ENV=(str, "development")
)

# Load .env file
environ.Env.read_env(BASE_DIR / ".env")

# =========================
# CORE SETTINGS
# =========================
SECRET_KEY = env("SECRET_KEY", default="goodnewsonlygoodnewsalways")
DEBUG = env("DEBUG")
ENVIRONMENT = env("DJANGO_ENV")

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "magnet.gatewaynation.org"]
)

# =========================
# INSTALLED APPS
# =========================
INSTALLED_APPS = [
    # Django default
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Third-party
    "cloudinary",
    "cloudinary_storage",
    "widget_tweaks",
    "channels",
    "django_htmx",

    # Your apps
    "workforce.apps.WorkforceConfig",
    "magnet.apps.MagnetConfig",
    "guests.apps.GuestsConfig",
    "accounts.apps.AccountsConfig",
    "notifications.apps.NotificationsConfig",
    "messaging.apps.MessagingConfig",
]

if DEBUG:
    INSTALLED_APPS.append("debug_toolbar")

# =========================
# MIDDLEWARE
# =========================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "notifications.middleware.CurrentUserMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

# =========================
# URLS & TEMPLATES
# =========================
ROOT_URLCONF = "gforceapp.urls"
WSGI_APPLICATION = "gforceapp.wsgi.application"
ASGI_APPLICATION = "gforceapp.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "notifications.context_processors.unread_notifications",
                "notifications.context_processors.user_settings",
                "notifications.context_processors.vapid_keys",
                "messaging.context_processors.bulk_message_form",
                "guests.context_processors.superuser_guests",
            ],
        },
    },
]

# =========================
# DATABASE
# =========================
if ENVIRONMENT == "production":
    DATABASES = {
        "default": dj_database_url.config(
            default=env("DATABASE_URL"),
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    try:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": env("DB_NAME"),
                "USER": env("DB_USER"),
                "PASSWORD": env("DB_PASSWORD"),
                "HOST": env("DB_HOST"),
                "PORT": env("DB_PORT"),
            }
        }
    except Exception:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }

# =========================
# REDIS CHANNEL LAYER
# =========================
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "capacity": 1000,
            "expiry": 60,
        },
    }
}

# =========================
# VAPID for Push Notifications
# =========================
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")

# =========================
# STATIC & MEDIA
# =========================
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STATIC_URL = "/static/"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =========================
# CLOUDINARY
# =========================
cloudinary.config(
    cloud_name=env("CLOUDINARY_CLOUD_NAME"),
    api_key=env("CLOUDINARY_API_KEY"),
    api_secret=env("CLOUDINARY_API_SECRET"),
)

if not DEBUG:
    DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"
else:
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": env("CLOUDINARY_API_KEY"),
    "API_SECRET": env("CLOUDINARY_API_SECRET"),
}

# =========================
# PWA CONFIGURATION
# =========================
PWA_APP_NAME = "Gateway Nation Workforce App"
PWA_APP_SHORT_NAME = "GForceApp"
PWA_APP_DESCRIPTION = "Workforce Hub for Gateway Nation"
PWA_APP_THEME_COLOR = "#2e303e"
PWA_APP_BACKGROUND_COLOR = "#2e303e"
PWA_APP_DISPLAY = "standalone"
PWA_APP_SCOPE = "/"
PWA_APP_START_URL = "/"
PWA_APP_ORIENTATION = "portrait"
PWA_APP_STATUS_BAR_COLOR = "default"
PWA_APP_ICONS = [
    {"src": "/static/images/icons/icon-192x192.png", "sizes": "192x192"},
    {"src": "/static/images/icons/icon-512x512.png", "sizes": "512x512"},
]
PWA_APP_ICONS_APPLE = PWA_APP_ICONS
PWA_APP_SPLASH_SCREEN = [
    {
        "src": "/static/images/splash-512x1024.png",
        "media": "(device-width: 360px) and (device-height: 740px)",
    }
]
PWA_APP_DIR = "ltr"
PWA_APP_LANG = "en-US"

# =========================
# AUTHENTICATION & SESSIONS
# =========================
AUTH_USER_MODEL = "accounts.CustomUser"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 28  # 28 days
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# =========================
# PASSWORD VALIDATORS
# =========================
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =========================
# LOCALIZATION
# =========================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

# =========================
# DEFAULT AUTO FIELD
# =========================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =========================
# WEBSOCKET SCHEME
# =========================
WS_SCHEME = "wss://" if ENVIRONMENT == "production" else "ws://"

# =========================
# CSRF & SECURITY
# =========================
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["https://magnet.gatewaynation.org"]
)

CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG

if DEBUG:
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
    CSRF_TRUSTED_ORIGINS.append("http://127.0.0.1:8000")
