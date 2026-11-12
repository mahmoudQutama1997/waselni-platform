import os
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import User


KEYS = {
    "customer": "test-customer-key-0001",
    "captain": "test-captain-key-0002",
    "merchant": "test-merchant-key-0003",
}
ENV = {
    "STADIA_KEY_CUSTOMER": KEYS["customer"],
    "STADIA_KEY_CAPTAIN": KEYS["captain"],
    "STADIA_KEY_MERCHANT": KEYS["merchant"],
}


class MapConfigTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.users = {
            role: User.objects.create_user(
                username=f"map-{role}", password="test-password-123", role=role
            )
            for role in KEYS
        }
        self.admin = User.objects.create_user(
            username="map-admin", password="test-password-123", role="admin"
        )

    def test_unauthenticated_cannot_get_a_key(self):
        with patch.dict(os.environ, ENV, clear=False):
            response = self.client.get("/api/map/config/")
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn("api_key", response.data)

    def test_each_role_receives_only_its_own_key(self):
        with patch.dict(os.environ, ENV, clear=False):
            for role, user in self.users.items():
                self.client.force_authenticate(user)
                response = self.client.get("/api/map/config/")
                self.assertEqual(response.status_code, 200, role)
                self.assertEqual(response.data["api_key"], KEYS[role], role)
                self.assertEqual(response.data["role"], role, role)
                for other_role, other_key in KEYS.items():
                    if other_role != role:
                        self.assertNotIn(other_key, response.content.decode(), (role, other_role))

    def test_client_supplied_role_is_ignored(self):
        with patch.dict(os.environ, ENV, clear=False):
            self.client.force_authenticate(self.users["customer"])
            response = self.client.get("/api/map/config/?role=merchant")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["api_key"], KEYS["customer"])
        self.assertNotEqual(response.data["api_key"], KEYS["merchant"])

    def test_admin_never_receives_a_native_key(self):
        with patch.dict(os.environ, ENV, clear=False):
            self.client.force_authenticate(self.admin)
            response = self.client.get("/api/map/config/?role=captain")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("api_key", response.data)
        for key in KEYS.values():
            self.assertNotIn(key, response.content.decode())

    def test_missing_server_key_is_reported_without_leaking_anything(self):
        with patch.dict(os.environ, {"STADIA_KEY_CUSTOMER": ""}, clear=False):
            self.client.force_authenticate(self.users["customer"])
            response = self.client.get("/api/map/config/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("api_key", response.data)

    def test_response_is_not_cacheable(self):
        with patch.dict(os.environ, ENV, clear=False):
            self.client.force_authenticate(self.users["customer"])
            response = self.client.get("/api/map/config/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Pragma"], "no-cache")
