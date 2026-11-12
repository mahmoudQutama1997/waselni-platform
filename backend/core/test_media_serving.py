import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8ffff3f0005fe02fea7d6a5c00000000049454e44ae426082"
)


class MediaServingTests(TestCase):
    def test_uploaded_image_is_served_when_debug_is_off(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            target = Path(root) / "products" / "probe.png"
            target.parent.mkdir(parents=True)
            target.write_bytes(PNG_BYTES)
            with override_settings(DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=root):
                response = self.client.get("/media/products/probe.png")
                body = b"".join(response.streaming_content)
                response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(body, PNG_BYTES)

    def test_media_is_not_served_when_serve_media_is_disabled(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            target = Path(root) / "products" / "probe.png"
            target.parent.mkdir(parents=True)
            target.write_bytes(PNG_BYTES)
            with override_settings(DEBUG=False, SERVE_MEDIA=False, MEDIA_ROOT=root):
                response = self.client.get("/media/products/probe.png")

        self.assertEqual(response.status_code, 404)

    def test_missing_media_returns_404(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            with override_settings(DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=root):
                response = self.client.get("/media/products/missing.png")

        self.assertEqual(response.status_code, 404)

    def test_media_path_cannot_escape_media_root(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
            with override_settings(DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=root):
                response = self.client.get("/media/../config/settings.py")

        self.assertIn(response.status_code, (400, 404))
