import re
from urllib.parse import unquote
from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework.test import APIClient

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="smtp.test.invalid",
    DEFAULT_FROM_EMAIL="noreply@example.test",
    PASSWORD_RESET_FRONTEND_URL="https://customer.example.test",
)
class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reset-customer",
            email="reset-customer@example.test",
            password="OriginalPassword!928",
            role="customer",
            must_change_password=True,
        )

    def tearDown(self):
        cache.clear()

    def test_request_response_does_not_disclose_unknown_email(self):
        existing = self.client.post(
            "/api/auth/password-reset/",
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(existing.status_code, 202)
        existing_message = existing.data["detail"]
        self.assertEqual(len(mail.outbox), 1)

        unknown = self.client.post(
            "/api/auth/password-reset/",
            {"email": "missing@example.test"},
            format="json",
        )
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(unknown.data["detail"], existing_message)
        self.assertEqual(len(mail.outbox), 1)

    @patch("core.auth_views.PasswordResetForm.save", side_effect=SMTPException("mail unavailable"))
    def test_delivery_failure_does_not_disclose_account_existence(self, _save):
        existing = self.client.post(
            "/api/auth/password-reset/",
            {"email": self.user.email},
            format="json",
        )
        unknown = self.client.post(
            "/api/auth/password-reset/",
            {"email": "missing@example.test"},
            format="json",
        )
        self.assertEqual(existing.status_code, 202)
        self.assertEqual(existing.data, unknown.data)

    def test_email_link_resets_password_once_and_clears_temporary_password_flag(self):
        response = self.client.post(
            "/api/auth/password-reset/",
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        match = re.search(
            r"#password-reset\?uid=([^&\s]+)&token=([^\s]+)",
            mail.outbox[0].body,
        )
        self.assertIsNotNone(match)
        uid, token = (unquote(value) for value in match.groups())
        self.assertIn("https://customer.example.test/#password-reset", mail.outbox[0].body)

        confirmation = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "NewUnique!Password742",
                "confirm_password": "NewUnique!Password742",
            },
            format="json",
        )
        self.assertEqual(confirmation.status_code, 200, confirmation.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewUnique!Password742"))
        self.assertFalse(self.user.must_change_password)

        reused = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "AnotherUnique!Password752",
                "confirm_password": "AnotherUnique!Password752",
            },
            format="json",
        )
        self.assertEqual(reused.status_code, 400)
        self.assertTrue(self.user.check_password("NewUnique!Password742"))

    def test_password_reset_revokes_existing_access_and_refresh_tokens(self):
        login = self.client.post(
            "/api/auth/token/",
            {"username": self.user.username, "password": "OriginalPassword!928"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        access_token = login.data["access"]
        refresh_token = login.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        self.assertEqual(self.client.get("/api/me/").status_code, 200)

        self.client.credentials()
        request = self.client.post(
            "/api/auth/password-reset/",
            {"email": self.user.email},
            format="json",
        )
        self.assertEqual(request.status_code, 202)
        match = re.search(
            r"#password-reset\?uid=([^&\s]+)&token=([^\s]+)",
            mail.outbox[0].body,
        )
        self.assertIsNotNone(match)
        uid, token = (unquote(value) for value in match.groups())
        confirmation = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "NewUnique!Password742",
                "confirm_password": "NewUnique!Password742",
            },
            format="json",
        )
        self.assertEqual(confirmation.status_code, 200, confirmation.data)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        self.assertEqual(self.client.get("/api/me/").status_code, 401)
        self.client.credentials()
        refreshed = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        self.assertEqual(self.client.get("/api/me/").status_code, 401)

    def test_invalid_or_expired_link_does_not_change_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": "invalid-token",
                "new_password": "NewUnique!Password742",
                "confirm_password": "NewUnique!Password742",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OriginalPassword!928"))


@override_settings(DEBUG=False, EMAIL_HOST="", DEFAULT_FROM_EMAIL="")
class PasswordResetConfigurationTests(TestCase):
    def test_production_reset_requests_fail_explicitly_without_mail_configuration(self):
        response = APIClient().post(
            "/api/auth/password-reset/",
            {"email": "someone@example.test"},
            format="json",
        )
        self.assertEqual(response.status_code, 503)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_HOST="smtp.example.test",
        DEFAULT_FROM_EMAIL="noreply@example.test",
    )
    def test_production_console_email_backend_is_not_treated_as_delivery(self):
        response = APIClient().post(
            "/api/auth/password-reset/",
            {"email": "someone@example.test"},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
