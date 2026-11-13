import hashlib
import hmac
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings

from .storage import (
    ImageKitError,
    WaselniMediaStorage,
    _unique_name,
    is_captain_document,
    purge_imagekit_url,
    signed_private_url,
    upload_to_imagekit,
)

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8ffff3f0005fe02fea7d6a5c00000000049454e44ae426082"
)
PDF_BYTES = b"%PDF-1.4 captain identity document"
ENDPOINT = "https://ik.imagekit.io/testendpoint"
PRIVATE_KEY = "test-private-key-not-a-secret"
CONFIGURED = {
    "IMAGEKIT_PRIVATE_KEY": PRIVATE_KEY,
    "IMAGEKIT_URL_ENDPOINT": ENDPOINT,
}
CONFIG = {
    "private_key": PRIVATE_KEY,
    "endpoint": ENDPOINT,
    "upload_api": "https://upload.imagekit.io/api/v1/files/upload",
    "media_api": "https://api.imagekit.io/v1",
    "prefix": "waselni",
}


class _BytesResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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

    def assert_no_local_files(self):
        self.assertEqual(sorted(p for p in self.root.rglob("*") if p.is_file()), [])

    def test_captain_documents_upload_to_imagekit_as_private_files(self):
        storage = WaselniMediaStorage()
        remote = "waselni/captain_documents/identity/licence-abc.pdf"
        with patch("core.storage.upload_to_imagekit", return_value=remote) as upload:
            name = storage.save("captain_documents/identity/licence.pdf", ContentFile(PDF_BYTES))
        upload.assert_called_once()
        self.assertTrue(upload.call_args.kwargs["private"])
        self.assertTrue(upload.call_args.args[0].startswith("captain_documents/identity/licence-"))
        self.assert_no_local_files()
        self.assertEqual(name, remote)
        self.assertTrue(storage.is_remote_captain_document(name))
        self.assertFalse(storage.is_remote_captain_document("profiles/avatar.png"))

    def test_private_documents_never_get_a_public_imagekit_url(self):
        storage = WaselniMediaStorage()
        name = "waselni/captain_documents/identity/licence.pdf"
        with patch("core.storage.upload_to_imagekit", return_value=name):
            storage.save("captain_documents/identity/licence.pdf", ContentFile(PDF_BYTES))
        self.assertNotIn("ik.imagekit.io", storage.url(name))
        self.assertEqual(storage.url(name), "/media/waselni/captain_documents/identity/licence.pdf")

    def test_captain_document_stays_local_without_configuration(self):
        with override_settings(IMAGEKIT_PRIVATE_KEY="", IMAGEKIT_URL_ENDPOINT=""):
            storage = WaselniMediaStorage()
            with patch("core.storage.upload_to_imagekit") as upload:
                name = storage.save("captain_documents/identity/licence.pdf", ContentFile(PDF_BYTES))
            upload.assert_not_called()
            self.assertTrue((self.root / "captain_documents" / "identity" / "licence.pdf").exists())
            self.assertEqual(name, "captain_documents/identity/licence.pdf")

    def test_public_image_uploads_to_imagekit(self):
        storage = WaselniMediaStorage()
        remote = "waselni/products/photo-deadbeef.png"
        with patch("core.storage.upload_to_imagekit", return_value=remote) as upload:
            name = storage.save("products/photo.png", ContentFile(PNG_BYTES))
        upload.assert_called_once()
        self.assertFalse(upload.call_args.kwargs["private"])
        uploaded_name = upload.call_args.args[0]
        self.assertTrue(uploaded_name.startswith("products/photo-"), uploaded_name)
        self.assert_no_local_files()
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

    def test_failed_public_upload_raises_and_writes_nothing_locally(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", side_effect=ImageKitError("boom")):
            with self.assertLogs("waselni.storage", level="ERROR"):
                with self.assertRaises(ImageKitError):
                    storage.save("profiles/avatar.png", ContentFile(PNG_BYTES))
        self.assert_no_local_files()

    def test_failed_private_upload_raises_and_writes_nothing_locally(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", side_effect=ImageKitError("boom")):
            with self.assertLogs("waselni.storage", level="ERROR"):
                with self.assertRaises(ImageKitError):
                    storage.save("captain_documents/identity/licence.pdf", ContentFile(PDF_BYTES))
        self.assert_no_local_files()

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
        with (
            patch("core.storage.delete_from_imagekit") as delete,
            patch("core.storage.purge_imagekit_url") as purge,
        ):
            storage.delete(name)
        delete.assert_called_once_with(name, storage._config())
        purge.assert_called_once_with(name, storage._config())

    def test_delete_of_remote_captain_document_uses_imagekit(self):
        storage = WaselniMediaStorage()
        remote = "waselni/captain_documents/identity/licence.pdf"
        with patch("core.storage.upload_to_imagekit", return_value=remote):
            name = storage.save("captain_documents/identity/licence.pdf", ContentFile(PDF_BYTES))
        with (
            patch("core.storage.delete_from_imagekit") as delete,
            patch("core.storage.purge_imagekit_url") as purge,
        ):
            storage.delete(name)
        delete.assert_called_once_with(remote, storage._config())
        purge.assert_not_called()

    def test_delete_skips_cache_purge_when_remote_delete_fails(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", return_value="waselni/products/remote.png"):
            name = storage.save("products/remote.png", ContentFile(PNG_BYTES))
        with (
            patch("core.storage.delete_from_imagekit", side_effect=ImageKitError("offline")),
            patch("core.storage.purge_imagekit_url") as purge,
        ):
            with self.assertLogs("waselni.storage", level="WARNING"):
                storage.delete(name)
        purge.assert_not_called()

    def test_purge_failure_is_logged_and_does_not_raise(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.upload_to_imagekit", return_value="waselni/products/remote.png"):
            name = storage.save("products/remote.png", ContentFile(PNG_BYTES))
        with (
            patch("core.storage.delete_from_imagekit"),
            patch("core.storage.purge_imagekit_url", side_effect=ImageKitError("purge offline")),
        ):
            with self.assertLogs("waselni.storage", level="WARNING"):
                storage.delete(name)

    def test_purge_uses_the_public_url_for_the_file(self):
        storage = WaselniMediaStorage()
        with patch("core.storage.urlopen", return_value=_BytesResponse(b"{}")) as call:
            purge_imagekit_url("waselni/profiles/photo.png", storage._config())
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.imagekit.io/v1/files/purge")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data.decode()), {"url": f"{ENDPOINT}/waselni/profiles/photo.png"})


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

    def test_private_document_handle_reads_through_a_signed_url(self):
        storage = WaselniMediaStorage()
        name = "waselni/captain_documents/identity/licence.pdf"
        with patch("core.storage.urlopen", return_value=_BytesResponse(PDF_BYTES)) as call:
            handle = storage.private_document_handle(name, expires_in=60)
        self.assertEqual(handle.read(), PDF_BYTES)
        signed_url = call.call_args.args[0].full_url
        self.assertTrue(signed_url.startswith(f"{ENDPOINT}/{name}?"), signed_url)
        self.assertIn("ik-t=", signed_url)
        self.assertIn("ik-s=", signed_url)

    def test_private_document_handle_is_unavailable_without_imagekit(self):
        with override_settings(IMAGEKIT_PRIVATE_KEY="", IMAGEKIT_URL_ENDPOINT=""):
            storage = WaselniMediaStorage()
            with self.assertRaises(FileNotFoundError):
                storage.private_document_handle("captain_documents/identity/licence.pdf")

    def test_private_document_handle_refuses_public_paths(self):
        storage = WaselniMediaStorage()
        with self.assertRaises(FileNotFoundError):
            storage.private_document_handle("profiles/avatar.png")


class SignedUrlTests(SimpleTestCase):
    def test_signature_matches_imagekit_algorithm(self):
        name = "waselni/captain_documents/identity/licence.pdf"
        with patch("core.storage.time.time", return_value=1000):
            url = signed_private_url(name, CONFIG, expires_in=120)
        expected_signature = hmac.new(
            PRIVATE_KEY.encode(), f"/{name}1120".encode(), hashlib.sha1
        ).hexdigest()
        self.assertEqual(url, f"{ENDPOINT}/{name}?ik-t=1120&ik-s={expected_signature}")

    def test_signature_changes_between_requests(self):
        name = "waselni/captain_documents/identity/licence.pdf"
        with patch("core.storage.time.time", return_value=1000):
            first = signed_private_url(name, CONFIG, expires_in=120)
        with patch("core.storage.time.time", return_value=2000):
            second = signed_private_url(name, CONFIG, expires_in=120)
        self.assertNotEqual(first, second)

    def test_expiry_has_a_floor_of_thirty_seconds(self):
        name = "waselni/captain_documents/identity/licence.pdf"
        with patch("core.storage.time.time", return_value=1000):
            url = signed_private_url(name, CONFIG, expires_in=1)
        self.assertIn("ik-t=1030", url)


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
        self.assertNotIn(b"isPrivateFile", body)

    def test_private_upload_marks_the_file_as_private(self):
        remote = "/waselni/captain_documents/identity/licence.pdf"
        with patch("core.storage.urlopen", return_value=self._Response({"filePath": remote})) as call:
            path = upload_to_imagekit("captain_documents/identity/licence.pdf", PDF_BYTES, CONFIG, private=True)
        self.assertEqual(path, "waselni/captain_documents/identity/licence.pdf")
        body = call.call_args.args[0].data
        self.assertIn(b'name="isPrivateFile"', body)
        self.assertIn(b"\r\n\r\ntrue\r\n", body)
        self.assertIn(b"/waselni/captain_documents/identity", body)

    def test_windows_separators_are_normalised_before_upload(self):
        # Django's generate_filename uses the host separator, so on Windows the
        # name arrives as "profiles\\photo.png" and must not become one segment.
        with patch("core.storage.urlopen", return_value=self._Response({"filePath": "/waselni/profiles/photo.png"})) as call:
            path = upload_to_imagekit("profiles\\photo.png", PNG_BYTES, CONFIG)
        self.assertEqual(path, "waselni/profiles/photo.png")
        body = call.call_args.args[0].data
        self.assertIn(b"\r\n\r\n/waselni/profiles\r\n", body)
        self.assertIn(b'name="file"; filename="photo.png"', body)

    def test_windows_separators_are_normalised_in_unique_names(self):
        name = _unique_name("profiles\\photo.png")
        self.assertTrue(name.startswith("profiles/"), name)
        self.assertNotIn("\\", name)

    def test_windows_separators_are_normalised_in_urls(self):
        storage = WaselniMediaStorage()
        with override_settings(IMAGEKIT_PRIVATE_KEY="key", IMAGEKIT_URL_ENDPOINT=ENDPOINT):
            with patch.object(storage._local, "exists", return_value=False):
                self.assertEqual(storage.url("profiles\\photo.png"), f"{ENDPOINT}/profiles/photo.png")
