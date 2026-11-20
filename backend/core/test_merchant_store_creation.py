"""Saving a store profile creates a real pending store and the admin publishes it.

The merchant screen previously required an existing MerchantProfile row, so a
merchant account without a store could not save anything at all, and the API
response did not expose the approval state that the message talks about.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BusinessCategory, MerchantProfile, PlatformService

User = get_user_model()


def make_service(code, name):
    return PlatformService.objects.create(
        code=code, name_ar=name, name_en=name, is_operational=True, is_active=True,
    )


class MerchantStoreCreationTests(TestCase):
    def setUp(self):
        self.food = make_service("food", "Food delivery")
        self.restaurant = BusinessCategory.objects.create(
            code="restaurant", name_ar="مطعم", name_en="Restaurant", service=self.food,
        )
        self.merchant = User.objects.create_user(
            username="new-merchant", password="merchant-pass-123", role="merchant",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.merchant)
        self.admin = User.objects.create_superuser(
            username="store-admin", password="admin-pass-123", email="store-admin@example.com",
        )
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)
        self.customer = User.objects.create_user(
            username="store-customer", password="customer-pass-123", role="customer",
        )
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer)

    def save_store(self, **payload):
        body = {"shop_name": "مطعم تجريبي", "business_category": self.restaurant.id}
        body.update(payload)
        return self.client.patch("/api/merchant/profile/", body, format="json")

    def visible_store_ids(self, service="food"):
        response = self.customer_client.get(f"/api/merchants/?service={service}")
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return {row["id"] for row in rows}

    def test_saving_creates_a_real_pending_store(self):
        response = self.save_store()
        self.assertEqual(response.status_code, 201, response.data)
        store = MerchantProfile.objects.get(user=self.merchant)
        self.assertEqual(store.shop_name, "مطعم تجريبي")
        self.assertEqual(store.approval_status, "pending")
        self.assertFalse(store.is_open)
        self.assertEqual(store.business_category_id, self.restaurant.id)
        self.assertEqual(store.category, "restaurant")
        self.assertEqual(store.service_type, "food")
        self.assertEqual(list(store.services.values_list("code", flat=True)), ["food"])
        self.assertEqual(response.data["approval_status"], "pending")
        self.assertTrue(response.data["store_created"])
        self.assertIn("awaiting administration approval", response.data["message"])

    def test_saved_store_is_returned_after_reopening_the_screen(self):
        self.save_store(description="وصف أول")
        response = self.client.get("/api/merchant/profile/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["shop_name"], "مطعم تجريبي")
        self.assertEqual(response.data["description"], "وصف أول")
        self.assertEqual(response.data["approval_status"], "pending")

    def test_merchant_can_edit_the_store_before_approval(self):
        self.save_store()
        response = self.client.patch(
            "/api/merchant/profile/",
            {"shop_name": "مطعم تجريبي 2", "description": "تحديث", "address": "نابلس"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store = MerchantProfile.objects.get(user=self.merchant)
        self.assertEqual(store.shop_name, "مطعم تجريبي 2")
        self.assertEqual(store.description, "تحديث")
        self.assertEqual(store.approval_status, "pending")

    def test_merchant_cannot_approve_their_own_store(self):
        response = self.save_store(approval_status="approved", is_open=True)
        self.assertEqual(response.status_code, 201, response.data)
        store = MerchantProfile.objects.get(user=self.merchant)
        self.assertEqual(store.approval_status, "pending")
        self.assertFalse(store.is_open)

    def test_pending_store_is_not_visible_to_customers(self):
        self.save_store()
        store = MerchantProfile.objects.get(user=self.merchant)
        self.assertNotIn(store.id, self.visible_store_ids())

    def test_admin_approval_publishes_the_store_in_the_food_service(self):
        self.save_store()
        store = MerchantProfile.objects.get(user=self.merchant)
        response = self.admin_client.patch(
            f"/api/admin/control/providers/{store.id}/",
            {"approval_status": "approved"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store.refresh_from_db()
        self.assertEqual(store.approval_status, "approved")
        self.assertTrue(store.is_open)
        self.assertIn("food", set(store.services.values_list("code", flat=True)))
        self.assertIn(store.id, self.visible_store_ids())
        self.assertNotIn(store.id, self.visible_store_ids("grocery"))

    def test_supermarket_activity_publishes_under_grocery(self):
        grocery = make_service("grocery", "Grocery")
        supermarket = BusinessCategory.objects.create(
            code="supermarket", name_ar="سوبرماركت", name_en="Supermarket", service=grocery,
        )
        response = self.save_store(shop_name="سوبرماركت تجريبي", business_category=supermarket.id)
        self.assertEqual(response.status_code, 201, response.data)
        store = MerchantProfile.objects.get(user=self.merchant)
        self.admin_client.patch(
            f"/api/admin/control/providers/{store.id}/",
            {"approval_status": "approved"},
            format="json",
        )
        store.refresh_from_db()
        self.assertEqual(store.service_type, "grocery")
        self.assertIn(store.id, self.visible_store_ids("grocery"))
