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
