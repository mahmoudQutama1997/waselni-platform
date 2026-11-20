from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_login_endpoint_throttles_repeated_attempts_from_same_client(self):
        responses = [
            self.client.post(
                "/api/auth/token/",
                {"username": "not-a-user", "password": "wrong"},
                format="json",
            )
            for _ in range(6)
        ]

        self.assertEqual([response.status_code for response in responses[:5]], [401] * 5)
        self.assertEqual(responses[5].status_code, 429)
