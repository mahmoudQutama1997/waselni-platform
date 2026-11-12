import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings

from .storage import (
    ImageKitError,
    WaselniMediaStorage,
    is_captain_document,
    upload_to_imagekit,
)

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8ffff3f0005fe02fea7d6a5c00000000049454e44ae426082"
)
ENDPOINT = "https://ik.imagekit.io/testendpoint"
CONFIGURED = {
    "IMAGEKIT_PRIVATE_KEY": "test-private-key-not-a-secret",
    "IMAGEKIT_URL_ENDPOINT": ENDPOINT,
}


class CaptainDocumentRoutingTests(SimpleTestCase):
    def test_detects_captain_document_paths(self):
        for name in (
            "captain_documents/identity/a.jpg",
            "captain_documents/licenses/a.jpg",
            "captain_documents.",
            "Captain_Documents/identity/a.jpg",
            "profiles\\..\\captain_documents\\a.jpg",
            "./captain_documents/a.jpg",
        ):
            self.assertTrue(is_captain_document(name), name)

    def test_public_names_are_not_treated_as_documents(self):
        for name in ("profiles/a.jpg", "products/a.jpg", "stores/logos/a.jpg", "captain_documents_public/a.jpg"):
            self.assertFalse(is_captain_document(name), name)


class StorageRoutingTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._override = override_settings(MEDIA_ROOT=self.root, **CONFIGURED)
        self._override.enable()
        self.addCleanup(self._override.disable)

    def test_captain_documents_stay_local_and_never_reach_imagekit(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit") as upload:
            name = storage.save("captain_documents/identity/licence.png", ContentFile(PNG_BYTES))
        upload.assert_not_called()
        self.assertTrue((self.root / "captain_documents" / "identity" / "licence.png").exists())
        self.assertEqual(name, "captain_documents/identity/licence.png")
        self.assertEqual(storage.url(name), "/media/captain_documents/identity/licence.png")

    def test_public_image_uploads_to_imagekit(self):
        storage = WaselniMediaStorage()
        remote = "waselni/products/photo-deadbeef.png"
        with patch("core.storage.upload_to_imagekit", return_value=remote) as upload:
            name = storage.save("products/photo.png", ContentFile(PNG_BYTES))
        upload.assert_called_once()
        uploaded_name = upload.call_args.args[0]
        self.assertTrue(uploaded_name.startswith("products/photo-"), uploaded_name)
        self.assertFalse((self.root / uploaded_name).exists())
        self.assertEqual(name, remote)
        self.assertEqual(storage.url(name), f"{ENDPOINT}/{remote}")
        self.assertTrue(storage.exists(name))

    def test_public_image_stays_local_without_configuration(self):
        with override_settings(IMAGEKIT_PRIVATE_KEY="", IMAGEKIT_URL_ENDPOINT=""):
            storage = WaselniMediaStorage()
            with patch("core.storage.upload_to_imagekit") as upload:
                name = storage.save("stores/logos/logo.png", ContentFile(PNG_BYTES))
            upload.assert_not_called()
            self.assertTrue((self.root / "stores" / "logos" / "logo.png").exists())
            self.assertEqual(storage.url(name), "/media/stores/logos/logo.png")

    def test_failed_upload_falls_back_to_local_and_logs(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", side_effect=ImageKitError("boom")):
            with self.assertLogs("waselni.storage", level="ERROR"):
                name = storage.save("profiles/avatar.png", ContentFile(PNG_BYTES))
        self.assertTrue(name.startswith("profiles/avatar-"), name)
        self.assertTrue((self.root / name).exists())
        self.assertEqual(storage.url(name), f"/media/{name}")

    def test_existing_local_file_keeps_its_media_url(self):
        legacy = self.root / "products" / "legacy.png"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(PNG_BYTES)
        storage = WaselniMediaStorage()
        self.assertEqual(storage.url("products/legacy.png"), "/media/products/legacy.png")

    def test_delete_of_missing_remote_file_is_logged_and_does_not_raise(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", return_value="waselni/products/remote.png"):
            name = storage.save("products/remote.png", ContentFile(PNG_BYTES))
        with patch("core.storage.delete_from_imagekit", side_effect=ImageKitError("offline")):
            with self.assertLogs("waselni.storage", level="WARNING"):
                storage.delete(name)

    def test_delete_of_remote_file_uses_imagekit(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", return_value="waselni/products/remote.png"):
            name = storage.save("products/remote.png", ContentFile(PNG_BYTES))
        with patch("core.storage.delete_from_imagekit") as delete:
            storage.delete(name)
        delete.assert_called_once_with(name, storage._config())

    def test_imagekit_names_are_unique_per_upload(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", side_effect=["waselni/products/a.png", "waselni/products/b.png"]) as upload:
            first = storage.save("products/same.png", ContentFile(PNG_BYTES))
            second = storage.save("products/same.png", ContentFile(PNG_BYTES))
        self.assertNotEqual(upload.call_args_list[0].args[0], upload.call_args_list[1].args[0])
        self.assertNotEqual(first, second)

    def test_remote_files_cannot_expose_a_local_path(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", return_value="waselni/products/remote.png"):
            name = storage.save("products/remote.png", ContentFile(PNG_BYTES))
        with self.assertRaises(NotImplementedError):
            storage.path(name)


class ImageKitRequestTests(SimpleTestCase):
    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return json.dumps(self._payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_upload_request_uses_private_key_and_returns_file_path(self):
        config = {
            "private_key": "test-private-key-not-a-secret",
            "endpoint": ENDPOINT,
            "upload_api": "https://upload.imagekit.io/api/v1/files/upload",
            "media_api": "https://api.imagekit.io/v1",
            "prefix": "waselni",
        }
        with patch("core.storage.urlopen", return_value=self._Response({"filePath": "/waselni/products/a.png"})) as call:
            path = upload_to_imagekit("products/a.png", PNG_BYTES, config)
        request = call.call_args.args[0]
        self.assertEqual(path, "waselni/products/a.png")
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("Basic ", request.get_header("Authorization"))
        self.assertIn("multipart/form-data", request.get_header("Content-type"))
        body = request.data
        self.assertIn(b'name="fileName"', body)
        self.assertIn(b"\r\n\r\na.png\r\n", body)
        self.assertIn(b"/waselni/products", body)
        self.assertIn(b'name="file"; filename="a.png"', body)
