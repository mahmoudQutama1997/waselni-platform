
import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from corsheaders.defaults import default_headers
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

if not DEBUG and SECRET_KEY == "dev-only-change-me":
    raise ImproperlyConfigured("Set a unique SECRET_KEY before running with DEBUG=False.")

ALLOWED_HOSTS = [
    x.strip()
    for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if x.strip()
]

# Render injects the public hostname of the web service. Keeping it in the
# allow-list means the blueprint still boots when Render appends a suffix
# because the requested service name is already taken.
_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "channels",
    "core",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

REDIS_URL = os.getenv("REDIS_URL", "").strip()
if not REDIS_URL:
    # Render's Blueprint only exposes host/port for Key Value instances.
    REDIS_HOST = os.getenv("REDIS_HOST", "").strip()
    if REDIS_HOST:
        REDIS_URL = f"redis://{REDIS_HOST}:{os.getenv('REDIS_PORT', '6379').strip() or '6379'}"

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "waselni-local-cache",
        }
    }
    # In-memory channels only reach clients connected to this single process.
    # Set REDIS_URL in production so WebSocket events cross workers/instances.
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3"
        }
    }

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Hebron"
USE_I18N = True
USE_TZ = True

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "webmaster@localhost" if DEBUG else ""
).strip()
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
PASSWORD_RESET_FRONTEND_URL = os.getenv(
    "PASSWORD_RESET_FRONTEND_URL",
    "https://waselni-customer1.vercel.app",
).strip().rstrip("/")

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(
    os.getenv("MEDIA_ROOT") or (BASE_DIR / "media")
)

# Every new public image is uploaded to ImageKit when both the private key and
# the URL endpoint are set. Captain documents are uploaded as private ImageKit
# files and are only readable through short-lived signed URLs generated by the
# backend. Without ImageKit (development/tests) uploads stay on local disk.
IMAGEKIT_PUBLIC_KEY = os.getenv("IMAGEKIT_PUBLIC_KEY", "").strip()
IMAGEKIT_PRIVATE_KEY = os.getenv("IMAGEKIT_PRIVATE_KEY", "").strip()
IMAGEKIT_URL_ENDPOINT = os.getenv("IMAGEKIT_URL_ENDPOINT", "").strip().rstrip("/")
IMAGEKIT_UPLOAD_FOLDER_PREFIX = os.getenv("IMAGEKIT_UPLOAD_FOLDER_PREFIX", "waselni").strip().strip("/")
# Lifetime of the signed URL used when the backend reads a private captain
# document. It is never sent to clients.
IMAGEKIT_PRIVATE_URL_TTL = int(os.getenv("IMAGEKIT_PRIVATE_URL_TTL", "300"))

STORAGES = {
    "default": {"BACKEND": "core.storage.WaselniMediaStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS configuration
CORS_ALLOWED_ORIGINS = [
    x.strip()
    for x in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,https://localhost,capacitor://localhost"
    ).split(",")
    if x.strip()
]

CORS_ALLOW_HEADERS = [
    *default_headers,
    "idempotency-key",
]

# Legacy preview deployments remain allowed by default; add new origins through
# CORS_ALLOWED_ORIGIN_REGEXES (comma-separated regexes) without editing code.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://waselni-customer1-[a-z0-9-]+-mahmoud13\.vercel\.app$",
    r"^https://waselni-captain-[a-z0-9-]+-mahmoud13\.vercel\.app$",
    r"^https://waselni-merchan-[a-z0-9-]+-mahmoud13\.vercel\.app$",
    r"^https://waselni-platform-5xd8-[a-z0-9-]+-mahmoud13\.vercel\.app$",
] + [
    x.strip()
    for x in os.getenv("CORS_ALLOWED_ORIGIN_REGEXES", "").split(",")
    if x.strip()
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login": "5/min",
        "password_reset": "5/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "CHECK_REVOKE_TOKEN": True,
}

# HTTPS protections default on for production and remain off for local development.
SECURE_SSL_REDIRECT = os.getenv(
    "SECURE_SSL_REDIRECT",
    str(not DEBUG)
).lower() == "true"

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SECURE_HSTS_SECONDS = int(
    os.getenv(
        "SECURE_HSTS_SECONDS",
        "31536000" if not DEBUG else "0"
    )
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = [
    x.strip()
    for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if x.strip()
]

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https"
)

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Django itself rejects request bodies larger than this; the per-file validators
# in core.validators enforce the tighter image/document limits.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE", str(12 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", str(5 * 1024 * 1024)))

# Serve uploaded media through Django when no external object storage / web
# server is in front. Enabled automatically in DEBUG, opt-in in production.
SERVE_MEDIA = os.getenv("SERVE_MEDIA", str(DEBUG)).lower() == "true"
