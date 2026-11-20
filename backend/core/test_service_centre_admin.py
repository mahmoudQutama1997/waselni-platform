"""Service centre: every service is controllable on its own from the console.

These tests cover the two defects that made Restaurants, Food delivery and
Supermarket & Grocery impossible to manage: a catalogue entry without its own
order flow could never be enabled, and the store/service resolution compared the
activity's own catalogue row instead of the flow that executes its orders.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BusinessCategory, MerchantProfile, PlatformService
from .services.service_scope import merchant_service_q

User = get_user_model()


def make_service(code, name=None, operational=True, active=True, **extra):
    return PlatformService.objects.create(
        code=code,
        name_ar=name or code,
        name_en=name or code,
        is_operational=operational,
        is_active=active,
        **extra,
    )


class ServiceCentreAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="service-admin", password="admin-pass-123", email="service-admin@example.com",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.food = make_service("food", "Food delivery")
        self.grocery = make_service("grocery", "Grocery & supermarket")
        self.pharmacy = make_service("pharmacy", "Pharmacy")
        self.restaurants = make_service("restaurants", "Restaurants", operational=False, active=False)
        self.supermarket = make_service("supermarket", "Supermarkets", operational=False, active=False)

    def patch(self, service, payload):
        return self.client.patch(f"/api/admin/control/services/{service.id}/", payload, format="json")

    def rows(self):
        response = self.client.get("/api/admin/control/services/")
        self.assertEqual(response.status_code, 200, response.data)
        return {row["code"]: row for row in response.data["services"]}

    def test_disabling_one_service_never_disables_the_others(self):
        response = self.patch(self.food, {"is_active": False})
        self.assertEqual(response.status_code, 200, response.data)
        self.food.refresh_from_db()
        self.grocery.refresh_from_db()
        self.pharmacy.refresh_from_db()
        self.assertFalse(self.food.is_active)
        self.assertTrue(self.grocery.is_active)
        self.assertTrue(self.pharmacy.is_active)
        rows = self.rows()
        self.assertFalse(rows["food"]["is_active"])
        self.assertTrue(rows["grocery"]["is_active"])
        self.assertTrue(rows["pharmacy"]["is_active"])

    def test_edited_name_and_description_survive_a_reload(self):
        response = self.patch(self.food, {
            "name_ar": "توصيل الطعام السريع",
            "name_en": "Fast food delivery",
            "description_ar": "وصف محدّث من الإدارة",
            "description_en": "Updated by administration",
            "is_active": True,
        })
        self.assertEqual(response.status_code, 200, response.data)
        row = self.rows()["food"]
        self.assertEqual(row["name_ar"], "توصيل الطعام السريع")
        self.assertEqual(row["name_en"], "Fast food delivery")
        self.assertEqual(row["description_ar"], "وصف محدّث من الإدارة")
        self.assertEqual(row["description_en"], "Updated by administration")
        self.assertTrue(row["is_active"])
        # The value is really in the database, not only in the response.
        self.food.refresh_from_db()
        self.assertEqual(self.food.description_ar, "وصف محدّث من الإدارة")

    def test_catalogue_entry_is_enabled_through_its_real_order_flow(self):
        response = self.patch(self.supermarket, {
            "fulfilment_service": self.grocery.id,
            "is_active": True,
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.supermarket.refresh_from_db()
        self.assertTrue(self.supermarket.is_active)
        self.assertEqual(self.supermarket.fulfilment_service_id, self.grocery.id)
        self.assertEqual(self.supermarket.effective_code, "grocery")
        # Customer-side gates now accept the entry because a wired flow runs it.
        self.assertTrue(PlatformService.is_offered("supermarket"))

    def test_entry_without_any_order_flow_cannot_be_enabled(self):
        response = self.patch(self.restaurants, {"is_active": True})
        self.assertEqual(response.status_code, 400, response.data)
        self.restaurants.refresh_from_db()
        self.assertFalse(self.restaurants.is_active)

    def test_self_referencing_fulfilment_link_is_rejected(self):
        response = self.patch(self.restaurants, {"fulfilment_service": self.restaurants.id})
        self.assertEqual(response.status_code, 400, response.data)

    def test_service_payload_lists_its_linked_business_activities(self):
        BusinessCategory.objects.create(
            code="restaurant", name_ar="مطعم", name_en="Restaurant", service=self.restaurants,
        )
        row = self.rows()["restaurants"]
        self.assertEqual(row["activities_count"], 1)
        self.assertEqual(row["activities"][0]["code"], "restaurant")

    def test_activity_link_moves_store_to_the_implemented_flow(self):
        restaurant = BusinessCategory.objects.create(
            code="bakery", name_ar="مخبز", name_en="Bakery", service=self.restaurants,
        )
        self.patch(self.restaurants, {"fulfilment_service": self.food.id})
        owner = User.objects.create_user(username="alias-merchant", password="merchant-pass-123", role="merchant")
        store = MerchantProfile.objects.create(
            user=owner, shop_name="مخبز الحي", category="bakery",
            approval_status="pending", is_open=False, business_category=restaurant,
        )
        store.refresh_from_db()
        self.assertEqual(store.service_type, "food")
        self.assertEqual(
            MerchantProfile.objects.filter(pk=store.pk).filter(merchant_service_q("food")).count(), 1,
        )
        self.assertEqual(
            MerchantProfile.objects.filter(pk=store.pk).filter(merchant_service_q("grocery")).count(), 0,
        )
