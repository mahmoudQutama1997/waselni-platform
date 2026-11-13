"""Upload validation and health endpoint coverage for production hardening."""
import io
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from .models import CaptainProfile, MerchantProfile, Product
from .validators import MAX_IMAGE_BYTES, validate_document_upload, validate_image_upload
from .ws_auth import _token_from_scope

User = get_user_model()
MEDIA_ROOT = tempfile.mkdtemp(prefix="waselni-test-media-")


def png_bytes(size=(4, 4)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="PNG")
    return buffer.getvalue()


class UploadValidatorTests(TestCase):
    def test_accepts_real_image(self):
        upload = SimpleUploadedFile("store.png", png_bytes(), content_type="image/png")
        self.assertIs(validate_image_upload(upload), upload)

    def test_rejects_spoofed_image(self):
        upload = SimpleUploadedFile("store.png", b"not really a png", content_type="image/png")
        with self.assertRaises(ValidationError) as caught:
            validate_image_upload(upload)
        self.assertIn("not a valid image", str(caught.exception.detail))

    def test_rejects_wrong_extension_and_content_type(self):
        with self.assertRaises(ValidationError):
            validate_image_upload(SimpleUploadedFile("store.gif", png_bytes(), content_type="image/png"))
        with self.assertRaises(ValidationError):
            validate_image_upload(SimpleUploadedFile("store.png", png_bytes(), content_type="text/html"))

    def test_rejects_oversized_image_before_decoding(self):
        upload = SimpleUploadedFile("huge.png", b"\x00" * (MAX_IMAGE_BYTES + 1), content_type="image/png")
        with self.assertRaises(ValidationError):
            validate_image_upload(upload)

    def test_documents_accept_pdf_and_images(self):
        pdf = SimpleUploadedFile("identity.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")
        self.assertIs(validate_document_upload(pdf), pdf)
        image = SimpleUploadedFile("license.jpg", png_bytes(), content_type="image/png")
        self.assertIs(validate_document_upload(image), image)

    def test_documents_reject_text_and_fake_pdf(self):
        with self.assertRaises(ValidationError):
            validate_document_upload(SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain"))
        with self.assertRaises(ValidationError):
            validate_document_upload(SimpleUploadedFile("identity.pdf", b"not a pdf", content_type="application/pdf"))


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class UploadApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.merchant = User.objects.create_user(username="upload-shop", password="merchant-password-123", role="merchant")
        self.profile = MerchantProfile.objects.create(user=self.merchant, shop_name="Upload Shop")
        self.client = APIClient()
        self.client.force_authenticate(self.merchant)

    def test_product_image_accepts_real_png_and_rejects_spoofed_file(self):
        ok = self.client.post("/api/products/", {
            "name": "Fresh bread", "price": "4.00",
            "image": SimpleUploadedFile("bread.png", png_bytes(), content_type="image/png"),
        }, format="multipart")
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertTrue(Product.objects.get(pk=ok.data["id"]).image)

        bad = self.client.post("/api/products/", {
            "name": "Broken", "price": "1.00",
            "image": SimpleUploadedFile("broken.png", b"still not an image", content_type="image/png"),
        }, format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("image", bad.data)

    def test_store_cover_upload_is_validated(self):
        ok = self.client.patch("/api/merchant/profile/", {
            "cover_image": SimpleUploadedFile("cover.png", png_bytes(), content_type="image/png"),
        }, format="multipart")
        self.assertEqual(ok.status_code, 200, ok.data)
        bad = self.client.patch("/api/merchant/profile/", {
            "cover_image": SimpleUploadedFile("cover.png", b"not an image", content_type="image/png"),
        }, format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("cover_image", bad.data)

    def test_captain_document_rejects_unsupported_file(self):
        captain = User.objects.create_user(username="upload-captain", password="captain-password-123", role="captain")
        CaptainProfile.objects.create(user=captain, approved=True)
        client = APIClient()
        client.force_authenticate(captain)
        bad = client.patch("/api/captains/me/", {
            "identity_document": SimpleUploadedFile("identity.txt", b"plain text", content_type="text/plain"),
        }, format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("identity_document", bad.data)
        ok = client.patch("/api/captains/me/", {
            "identity_document": SimpleUploadedFile("identity.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertTrue(CaptainProfile.objects.get(user=captain).identity_document)


class AsgiWiringTests(SimpleTestCase):
    def test_asgi_application_imports_with_websocket_middleware(self):
        from config.asgi import application
        self.assertIsNotNone(application)

    def test_jwt_is_read_from_subprotocol_before_query(self):
        self.assertEqual(_token_from_scope({"subprotocols": ["waselni.jwt.abc"], "query_string": b"token=old"}).strip(), "abc")
        self.assertEqual(_token_from_scope({"subprotocols": ["bearer.xyz"]}), "xyz")
        self.assertEqual(_token_from_scope({"subprotocols": [], "query_string": b"token=legacy"}), "legacy")
        self.assertIsNone(_token_from_scope({"subprotocols": [], "query_string": b""}))


class HealthEndpointTests(TestCase):
    def test_health_is_public_and_reports_database(self):
        with mock.patch.dict("os.environ", {"RENDER_GIT_COMMIT": "abcdef1234567890"}):
            response = APIClient().get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["database"], "ok")
        self.assertEqual(response.data["commit"], "abcdef1")

    def test_health_returns_503_when_database_is_unavailable(self):
        with mock.patch("core.views.connection.cursor", side_effect=RuntimeError("down")):
            response = APIClient().get("/api/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["database"], "unavailable")
