import os
import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import CaptainProfile, MerchantProfile, Product, User
from .storage import ImageKitError


def make_png():
    buffer = BytesIO()
    Image.new("RGB", (2, 2), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


PNG_BYTES = make_png()
PDF_BYTES = b"%PDF-1.4 captain identity document"
ENDPOINT = "https://ik.imagekit.io/testendpoint"
CONFIG = {
    "IMAGEKIT_PRIVATE_KEY": "test-private-key-not-a-secret",
    "IMAGEKIT_URL_ENDPOINT": ENDPOINT,
}


def png(name="photo.png"):
    return SimpleUploadedFile(name, PNG_BYTES, content_type="image/png")


def pdf(name="identity.pdf"):
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


@override_settings(**CONFIG)
class MediaUploadApiTests(TestCase):
    """End-to-end uploads for every public image type and captain documents."""

    @classmethod
    def setUpClass(cls):
        cls.media_root = tempfile.mkdtemp(prefix="waselni-upload-test-")
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            username="upload-customer", password="test-password-123", role="customer"
        )
        self.merchant = User.objects.create_user(
            username="upload-merchant", password="test-password-123", role="merchant"
        )
        self.store = MerchantProfile.objects.create(user=self.merchant, shop_name="Test Store")
        self.captain = User.objects.create_user(
            username="upload-captain", password="test-password-123", role="captain"
        )
        self.captain_profile = CaptainProfile.objects.create(user=self.captain)

    def assert_no_local_uploads(self):
        for base, _dirs, files in os.walk(self.media_root):
            self.assertEqual(files, [], base)

    def test_customer_profile_image_is_stored_on_imagekit_and_survives_reload(self):
        remote = "waselni/profiles/avatar-abc.png"
        self.client.force_authenticate(self.customer)
        with patch("core.storage.upload_to_imagekit", return_value=remote) as upload:
            response = self.client.patch(
                "/api/account/profile/", {"profile_image": png("avatar.png")}, format="multipart"
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["profile_image"], f"{ENDPOINT}/{remote}")
        upload.assert_called_once()
        self.assertFalse(upload.call_args.kwargs["private"])
        self.assert_no_local_uploads()

        reload_response = self.client.get("/api/me/")
        self.assertEqual(reload_response.data["profile_image"], f"{ENDPOINT}/{remote}")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.profile_image.name, remote)

    def test_replacing_the_profile_image_deletes_the_previous_remote_file(self):
        self.customer.profile_image = "waselni/profiles/old.png"
        self.customer.save(update_fields=["profile_image"])
        self.client.force_authenticate(self.customer)
        with patch("core.storage.upload_to_imagekit", return_value="waselni/profiles/new.png"):
            with patch("core.storage.delete_from_imagekit") as delete, patch("core.storage.purge_imagekit_url") as purge:
                response = self.client.patch(
                    "/api/account/profile/", {"profile_image": png()}, format="multipart"
                )
        self.assertEqual(response.status_code, 200, response.content)
        delete.assert_called_once()
        purge.assert_called_once()
        self.assertEqual(purge.call_args.args[0], "waselni/profiles/old.png")
        self.assertEqual(delete.call_args.args[0], "waselni/profiles/old.png")

    def test_merchant_store_logo_and_cover_are_stored_on_imagekit(self):
        logo = "waselni/stores/logos/logo-new.png"
        cover = "waselni/stores/covers/cover-new.png"
        self.client.force_authenticate(self.merchant)
        with patch("core.storage.upload_to_imagekit", side_effect=[logo, cover]) as upload:
            response = self.client.patch(
                "/api/merchant/profile/",
                {"image": png("logo.png"), "cover_image": png("cover.png")},
                format="multipart",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(upload.call_count, 2)
        self.assertEqual(response.data["image"], f"{ENDPOINT}/{logo}")
        self.assertEqual(response.data["cover_image"], f"{ENDPOINT}/{cover}")
        self.assert_no_local_uploads()

    def test_product_image_is_stored_on_imagekit(self):
        remote = "waselni/products/product-new.png"
        self.client.force_authenticate(self.merchant)
        with patch("core.storage.upload_to_imagekit", return_value=remote) as upload:
            response = self.client.post(
                "/api/products/",
                {"name": "QA product", "price": "9.99", "image": png()},
                format="multipart",
            )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["image"], f"{ENDPOINT}/{remote}")
        upload.assert_called_once()
        self.assert_no_local_uploads()

    def test_replacing_the_product_image_deletes_the_previous_remote_file(self):
        product = Product.objects.create(
            merchant=self.store, name="Old product", price="1.00", image="waselni/products/old.png"
        )
        self.client.force_authenticate(self.merchant)
        with patch("core.storage.upload_to_imagekit", return_value="waselni/products/new.png"):
            with patch("core.storage.delete_from_imagekit") as delete, patch("core.storage.purge_imagekit_url") as purge:
                response = self.client.patch(
                    f"/api/products/{product.id}/", {"image": png()}, format="multipart"
                )
        self.assertEqual(response.status_code, 200, response.content)
        delete.assert_called_once()
        purge.assert_called_once()
        self.assertEqual(delete.call_args.args[0], "waselni/products/old.png")

    def test_captain_document_upload_is_private_on_imagekit(self):
        remote = "waselni/captain_documents/identity/identity-new.pdf"
        self.client.force_authenticate(self.captain)
        with patch("core.storage.upload_to_imagekit", return_value=remote) as upload:
            response = self.client.patch(
                "/api/captains/me/", {"identity_document": pdf()}, format="multipart"
            )
        self.assertEqual(response.status_code, 200, response.content)
        upload.assert_called_once()
        self.assertTrue(upload.call_args.kwargs["private"])
        self.assert_no_local_uploads()
        self.captain_profile.refresh_from_db()
        self.assertEqual(self.captain_profile.identity_document.name, remote)
        self.assertNotIn("ik-s=", self.captain_profile.identity_document.name)

    def test_replacing_a_captain_document_deletes_the_previous_remote_file(self):
        self.captain_profile.identity_document = "waselni/captain_documents/identity/old.pdf"
        self.captain_profile.save(update_fields=["identity_document"])
        self.client.force_authenticate(self.captain)
        with patch("core.storage.upload_to_imagekit", return_value="waselni/captain_documents/identity/new.pdf"):
            with patch("core.storage.delete_from_imagekit") as delete:
                response = self.client.patch(
                    "/api/captains/me/", {"identity_document": pdf()}, format="multipart"
                )
        self.assertEqual(response.status_code, 200, response.content)
        delete.assert_called_once()
        self.assertEqual(delete.call_args.args[0], "waselni/captain_documents/identity/old.pdf")


@override_settings(**CONFIG)
class MediaUploadOutageTests(TransactionTestCase):
    """A failed save must not be retried against a broken transaction."""

    @classmethod
    def setUpClass(cls):
        cls.media_root = tempfile.mkdtemp(prefix="waselni-outage-test-")
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)

    def test_upload_outage_returns_503_without_writing_locally(self):
        customer = User.objects.create_user(
            username="outage-customer", password="test-password-123", role="customer"
        )
        customer.profile_image = "waselni/profiles/keep.png"
        customer.save(update_fields=["profile_image"])
        client = APIClient()
        client.force_authenticate(customer)
        with patch("core.storage.upload_to_imagekit", side_effect=ImageKitError("boom")):
            with self.assertLogs("waselni.storage", level="ERROR"):
                response = client.patch(
                    "/api/account/profile/", {"profile_image": png()}, format="multipart"
                )
        self.assertEqual(response.status_code, 503, response.content)
        customer.refresh_from_db()
        self.assertEqual(customer.profile_image.name, "waselni/profiles/keep.png")
        for base, _dirs, files in os.walk(self.media_root):
            self.assertEqual(files, [], base)
