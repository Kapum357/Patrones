"""
Django settings for parcial project — CQRS OTP Prototype.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-2n404zx@2j1y6y7o5)@t!w8-8_j^rh^fi@xd#kvb%eg4ch*wz8"

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "otp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "parcial.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "parcial" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "parcial.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── MongoDB (read side) ──────────────────────────────────────────────────────
MONGODB_URI = "mongodb+srv://Kapum:Kapum@cluster0.1qth2ii.mongodb.net/"
MONGODB_DB_NAME = "otp_cqrs"

# ── JWT Auth ─────────────────────────────────────────────────────────────────
JWT_SECRET_KEY = "super-secret-jwt-key-change-in-production"
JWT_EXPIRY_SECONDS = 3600

# Predefined clients (client_id → client_secret)
JWT_CLIENTS = {
    "app_web": "secret_web_123",
    "app_mobile": "secret_mobile_456",
    "demo": "demo",
}

# ── SMS Provider Microservices Settings ──────────────────────────────────────
ALDEAMO_SERVICE_URL = "http://localhost:8001/send"
TWILIO_SERVICE_URL = "http://localhost:8002/send"

# ── Circuit Breaker ───────────────────────────────────────────────────────────
CIRCUIT_BREAKER_FAIL_MAX = 2       # failures before opening
CIRCUIT_BREAKER_RESET_TIMEOUT = 20  # seconds before half-open

# ── DRF ──────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "otp.auth.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}
