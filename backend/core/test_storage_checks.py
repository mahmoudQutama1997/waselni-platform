from django.core.checks import Warning
from django.core.checks.registry import registry
from django.test import SimpleTestCase, override_settings

from .checks import imagekit_configuration, redis_configuration


@override_settings(DEBUG=False)
class ImageKitStorageCheckTests(SimpleTestCase):
    def test_check_is_registered(self):
        self.assertIn(imagekit_configuration, registry.get_checks())

    @override_settings(DEBUG=True, SERVE_MEDIA=False, IMAGEKIT_PRIVATE_KEY="", IMAGEKIT_URL_ENDPOINT="")
    def test_debug_mode_is_silent(self):
        self.assertEqual(imagekit_configuration(None), [])

    @override_settings(
        DEBUG=False,
        SERVE_MEDIA=False,
        IMAGEKIT_PRIVATE_KEY="",
        IMAGEKIT_URL_ENDPOINT="",
    )
    def test_disabled_media_without_imagekit_warns_about_404(self):
        warnings = imagekit_configuration(None)
        self.assertEqual([w.id for w in warnings], ["waselni.W001"])
        self.assertIsInstance(warnings[0], Warning)
        self.assertNotIn("PRIVATE_KEY=", warnings[0].msg)

    @override_settings(
        DEBUG=False,
        SERVE_MEDIA=True,
        IMAGEKIT_PRIVATE_KEY="",
        IMAGEKIT_URL_ENDPOINT="",
    )
    def test_local_disk_without_imagekit_warns_about_loss(self):
        self.assertEqual([w.id for w in imagekit_configuration(None)], ["waselni.W002"])

    @override_settings(
        DEBUG=False,
        SERVE_MEDIA=False,
        IMAGEKIT_PRIVATE_KEY="test-private-key-not-a-secret",
        IMAGEKIT_URL_ENDPOINT="https://ik.imagekit.io/testendpoint",
    )
    def test_configured_imagekit_is_silent(self):
        self.assertEqual(imagekit_configuration(None), [])


class RedisConfigurationCheckTests(SimpleTestCase):
    def test_check_is_registered(self):
        self.assertIn(redis_configuration, registry.get_checks())

    @override_settings(DEBUG=True, REDIS_URL="")
    def test_development_without_redis_is_allowed(self):
        self.assertEqual(redis_configuration(None), [])

    @override_settings(DEBUG=False, REDIS_URL="")
    def test_production_without_redis_warns(self):
        warnings = redis_configuration(None)
        self.assertEqual([warning.id for warning in warnings], ["waselni.W004"])
        self.assertIsInstance(warnings[0], Warning)
        self.assertNotIn("REDIS_URL=", warnings[0].msg)

    @override_settings(DEBUG=False, REDIS_URL="redis://redis.example.test:6379")
    def test_production_with_redis_is_silent(self):
        self.assertEqual(redis_configuration(None), [])
