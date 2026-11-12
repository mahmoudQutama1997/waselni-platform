import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import CaptainProfile, User

DOC_CONTENT = b"%PDF-1.4 captain identity document"


class CaptainDocumentSecurityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_root = tempfile.mkdtemp(prefix="waselni-doc-test-")
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root, SERVE_MEDIA=True)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.captain = User.objects.create_user(
            username="doc-captain", password="test-password-123", role="captain"
        )
        self.profile = CaptainProfile.objects.create(user=self.captain)
        self.profile.identity_document.save(
            "identity.pdf",
            SimpleUploadedFile("identity.pdf", DOC_CONTENT, content_type="application/pdf"),
            save=True,
        )
        self.document_name = self.profile.identity_document.name
        self.url = f"/api/captain-documents/{self.profile.id}/identity/"

        self.other_captain = User.objects.create_user(
            username="doc-other-captain", password="test-password-123", role="captain"
        )
        CaptainProfile.objects.create(user=self.other_captain)
        self.customer = User.objects.create_user(
            username="doc-customer", password="test-password-123", role="customer"
        )
        self.merchant = User.objects.create_user(
            username="doc-merchant", password="test-password-123", role="merchant"
        )
        self.admin = User.objects.create_user(
            username="doc-admin", password="test-password-123", role="admin"
        )

    def assert_no_document_leak(self, response):
        body = response.content.decode("utf-8", errors="replace")
        self.assertNotIn(DOC_CONTENT.decode(), body)
        self.assertNotIn("captain_documents", body)
        self.assertNotIn("identity.pdf", body)

    def relative_document_name(self):
        return self.document_name.split("/", 1)[1]

    def assert_media_blocked(self, url):
        for user in (None, self.captain, self.admin):
            self.client.force_authenticate(user)
            response = self.client.get(url)
            label = getattr(user, "username", "anonymous")
            self.assertEqual(response.status_code, 404, (url, label))
            self.assert_no_document_leak(response)

    def test_anonymous_cannot_download(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (401, 403))
        self.assert_no_document_leak(response)

    def test_owner_can_download_own_document(self):
        self.client.force_authenticate(self.captain)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), DOC_CONTENT)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Pragma"], "no-cache")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_other_captain_cannot_download(self):
        self.client.force_authenticate(self.other_captain)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assert_no_document_leak(response)

    def test_customer_cannot_download(self):
        self.client.force_authenticate(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assert_no_document_leak(response)

    def test_merchant_cannot_download(self):
        self.client.force_authenticate(self.merchant)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assert_no_document_leak(response)

    def test_admin_can_download(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), DOC_CONTENT)

    def test_direct_media_url_is_blocked_for_anonymous_user(self):
        response = self.client.get(f"/media/{self.document_name}")
        self.assertEqual(response.status_code, 404)
        self.assert_no_document_leak(response)

    def test_direct_media_url_is_blocked_even_for_the_owner(self):
        self.client.force_authenticate(self.captain)
        response = self.client.get(f"/media/{self.document_name}")
        self.assertEqual(response.status_code, 404)
        self.assert_no_document_leak(response)

    def test_encoded_traversal_into_captain_documents_is_blocked(self):
        response = self.client.get(f"/media/profiles/%2e%2e/{self.document_name}")
        self.assertEqual(response.status_code, 404)
        self.assert_no_document_leak(response)

    def test_public_store_media_still_serves(self):
        path = os.path.join(self.media_root, "stores", "logos", "logo.png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"public-logo-bytes")
        response = self.client.get("/media/stores/logos/logo.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.getvalue() if hasattr(response, "getvalue") else b"".join(response.streaming_content), b"public-logo-bytes")

    def test_missing_document_is_not_disclosed(self):
        self.client.force_authenticate(self.other_captain)
        response = self.client.get(f"/api/captain-documents/{self.other_captain.captain_profile.id}/identity/")
        self.assertEqual(response.status_code, 404)
        self.assert_no_document_leak(response)

    def test_captain_status_api_does_not_leak_document_paths(self):
        self.client.force_authenticate(self.captain)
        response = self.client.get("/api/captains/me/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertNotIn("captain_documents", body)
        self.assertNotIn("identity.pdf", body)
        self.assertTrue(response.data["documents"]["identity_uploaded"])

    def test_unknown_field_and_profile_are_rejected(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get(f"/api/captain-documents/{self.profile.id}/passport/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/captain-documents/999999/identity/").status_code,
            404,
        )

    def test_windows_trailing_dot_and_space_folder_aliases_are_blocked(self):
        relative = self.relative_document_name()
        for folder in (
            "captain_documents.",
            "captain_documents%2E",
            "captain_documents%20",
            "captain_documents.%20",
        ):
            self.assert_media_blocked(f"/media/{folder}/{relative}")

    def test_folder_case_variants_are_blocked(self):
        relative = self.relative_document_name()
        for folder in ("CAPTAIN_DOCUMENTS", "Captain_Documents", "cApTaIn_DoCuMeNtS"):
            self.assert_media_blocked(f"/media/{folder}/{relative}")

    def test_backslash_separators_are_blocked(self):
        relative = self.relative_document_name().replace("/", "\\")
        self.assert_media_blocked(f"/media/captain_documents\\{relative}")
        self.assert_media_blocked(f"/media/profiles\\..\\captain_documents\\{relative}")

    def test_dot_segments_and_traversal_are_blocked(self):
        relative = self.relative_document_name()
        filename = relative.rsplit("/", 1)[-1]
        for url in (
            f"/media/./captain_documents/{relative}",
            f"/media/profiles/../captain_documents/{relative}",
            f"/media/profiles/%2e%2e/captain_documents/{relative}",
            f"/media/captain_documents/identity/../identity/{filename}",
        ):
            self.assert_media_blocked(url)

    def test_public_store_product_and_profile_media_still_serve(self):
        files = {
            "stores/logos/logo.png": b"store-logo",
            "stores/covers/cover.png": b"store-cover",
            "products/product.png": b"product-image",
            "profiles/avatar.png": b"profile-image",
            "captain_documents_public/notice.png": b"similar-folder",
        }
        for relative, content in files.items():
            path = os.path.join(self.media_root, *relative.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(content)
            response = self.client.get(f"/media/{relative}")
            self.assertEqual(response.status_code, 200, relative)
            body = response.getvalue() if hasattr(response, "getvalue") else b"".join(response.streaming_content)
            self.assertEqual(body, content, relative)

    def test_stored_name_outside_private_folder_is_rejected(self):
        self.profile.identity_document.name = "profiles/identity.pdf"
        self.profile.save(update_fields=["identity_document"])
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assert_no_document_leak(response)

    def test_malicious_stored_name_is_rejected_without_server_error(self):
        self.profile.identity_document.name = "../profiles/identity.pdf"
        self.profile.save(update_fields=["identity_document"])
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
