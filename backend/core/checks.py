from django.conf import settings
from django.core.checks import Warning, register


@register()
def imagekit_configuration(app_configs, **kwargs):
    """Surface the production storage setup that makes uploaded images 404.

    Without both ImageKit values, public uploads are written to local disk. On
    an ephemeral host they disappear on restart, and with SERVE_MEDIA off their
    /media/ URLs return 404 as soon as they are saved.
    """
    if settings.DEBUG:
        return []

    private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY", "")
    endpoint = getattr(settings, "IMAGEKIT_URL_ENDPOINT", "")
    if private_key and endpoint:
        return []

    if not getattr(settings, "SERVE_MEDIA", False):
        return [
            Warning(
                "ImageKit is not configured and SERVE_MEDIA is off: uploaded public "
                "images are stored locally but their /media/ URLs return 404.",
                hint=(
                    "Set IMAGEKIT_PRIVATE_KEY and IMAGEKIT_URL_ENDPOINT in the hosting "
                    "environment, or turn on SERVE_MEDIA with a persistent MEDIA_ROOT."
                ),
                id="waselni.W001",
            )
        ]

    return [
        Warning(
            "ImageKit is not configured: uploaded public images are stored on local "
            "disk and will be lost when an ephemeral host restarts or redeploys.",
            hint=(
                "Set IMAGEKIT_PRIVATE_KEY and IMAGEKIT_URL_ENDPOINT in the hosting "
                "environment, or mount a persistent disk at MEDIA_ROOT."
            ),
            id="waselni.W002",
        )
    ]


@register()
def redis_configuration(app_configs, **kwargs):
    if settings.DEBUG or getattr(settings, "REDIS_URL", "").strip():
        return []

    return [
        Warning(
            "Redis is not configured in production; shared throttling and "
            "cross-worker WebSocket delivery are unavailable.",
            hint="Set REDIS_URL or REDIS_HOST and REDIS_PORT in the hosting environment.",
            id="waselni.W004",
        )
    ]


@register()
def password_reset_email_configuration(app_configs, **kwargs):
    if settings.DEBUG:
        return []

    if (
        settings.EMAIL_HOST
        and settings.DEFAULT_FROM_EMAIL
        and settings.EMAIL_BACKEND != "django.core.mail.backends.console.EmailBackend"
    ):
        return []

    return [
        Warning(
            "Password recovery email is not configured; account recovery will return HTTP 503.",
            hint=(
                "Configure a production email backend, EMAIL_HOST, "
                "DEFAULT_FROM_EMAIL, and the required SMTP credentials."
            ),
            id="waselni.W003",
        )
    ]
