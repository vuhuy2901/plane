# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Development settings"""

import os

from .common import *  # noqa

DEBUG = os.environ.get("DEBUG", "1") == "1"

# Keep local redirects and browser cookies on the same origin when the API is
# started directly from the host instead of Docker.
WEB_URL = os.environ.get("WEB_URL", "http://localhost:8000")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:3000")

# Debug Toolbar settings (set DEBUG=0 to skip its per-request SQL/panel instrumentation)
if DEBUG:
    INSTALLED_APPS += ("debug_toolbar",)  # noqa
    MIDDLEWARE += ("debug_toolbar.middleware.DebugToolbarMiddleware",)  # noqa
    DEBUG_TOOLBAR_PATCH_SETTINGS = False

# Disable CSRF verification and allow all CORS origins in local development
MIDDLEWARE = [
    "plane.middleware.disable_csrf.DisableCSRFMiddleware",
    *MIDDLEWARE,
]
CORS_ALLOW_ALL_ORIGINS = True

# Only show emails in console don't send it to smtp
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

CORE_MODE = os.environ.get("PLANE_CORE_MODE", "0") == "1"

if CORE_MODE:
    # The browser submits the login form from the web dev server to the API.
    # Django checks that Origin separately from CORS, so the web origin must
    # be trusted even when CORS accepts it.
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([*CSRF_TRUSTED_ORIGINS, APP_BASE_URL]))  # noqa: F405

    # Use isolated cookie names so stale Docker/127.0.0.1 sessions cannot
    # invalidate local authentication and CSRF requests.
    SESSION_COOKIE_NAME = "plane-core-session-id"
    CSRF_COOKIE_NAME = "plane-core-csrftoken"

    # Core local mode does not require Redis for Django's cache layer.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "plane-core-local",
        }
    }
    # Run Celery calls synchronously so a worker/broker is not needed locally.
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
    # Only background containers use RabbitMQ; core API cookies/storage stay unchanged.
    if os.environ.get("PLANE_BACKGROUND_WORKER") == "1":
        CELERY_TASK_ALWAYS_EAGER = False
        CELERY_BROKER_URL = os.environ["PLANE_WORKER_BROKER_URL"]
        CELERY_RESULT_BACKEND = None
    # Store uploads on disk. Upload-related features remain optional, but no
    # MinIO/S3 service is needed to boot the core task/workflow experience.
    STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}  # noqa: F405
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,  # noqa
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }

INTERNAL_IPS = ("127.0.0.1",)

MEDIA_URL = "/uploads/"
MEDIA_ROOT = os.path.join(BASE_DIR, "uploads")  # noqa

LOG_DIR = os.path.join(BASE_DIR, "logs")  # noqa

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(levelname)s %(asctime)s %(module)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "loggers": {
        "plane.api.request": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.api": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "plane.worker": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "plane.exception": {
            "level": "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.external": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.authentication": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "plane.migrations": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
