"""An approved store may request another activity; administration applies it."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BusinessCategory, MerchantProfile, PlatformService

User = get_user_model()


def make_service(code, name):
    return PlatformService.objects.create(
        code=code, name_ar=name, name_en=name, is_operational=True, is_active=True,
    )


class MerchantActivityRequestTests(TestCase):
    def setUp(self):
        self.grocery = make_service("grocery", "Grocery")
        self.pharmacy = make_service("pharmacy", "Pharmacy")
        self.supermarket = BusinessCategory.objects.create(
            code="supermarket", name_ar="سوبرماركت", name_en="Supermarket", service=self.grocery,
        )
        self.pharmacy_activity = BusinessCategory.objects.create(
            code="pharmacy", name_ar="صيدلية", name_en="Pharmacy", service=self.pharmacy,
        )
        self.inactive_activity = BusinessCategory.objects.create(
            code="closed_activity", name_ar="نشاط موقوف", name_en="Closed activity",
            service=self.pharmacy, is_active=False,
        )
        self.owner = User.objects.create_user(
            username="request-merchant", password="merchant-pass-123", role="merchant",
        )
        self.store = MerchantProfile.objects.create(
            user=self.owner, shop_name="سوبرماركت الأمانة", category="supermarket",
            approval_status="approved", is_open=True, business_category=self.supermarket,
        )
        self.store.services.add(self.grocery)
        self.admin = User.objects.create_user(
            username="request-admin", password="admin-pass-123", role="admin",
        )

    def merchant_client(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        return client

    def admin_client(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        return client

    def test_approved_store_change_is_stored_as_a_request(self):
        response = self.merchant_client().patch(
            "/api/merchant/profile/",
            {"shop_name": "سوبرماركت الأمانة", "business_category": self.pharmacy_activity.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        # The current activity keeps selling; the choice waits for the admin.
        self.assertEqual(self.store.business_category_id, self.supermarket.id)
        self.assertEqual(self.store.requested_business_category_id, self.pharmacy_activity.id)
        self.assertIsNotNone(self.store.activity_requested_at)
        self.assertEqual(response.data["business_category"], self.supermarket.id)
        self.assertEqual(response.data["requested_business_category"], self.pharmacy_activity.id)
        self.assertEqual(response.data["requested_business_category_code"], "pharmacy")
        self.assertTrue(response.data["activity_request_pending"])

    def test_admin_approval_applies_the_requested_activity(self):
        self.merchant_client().patch(
            "/api/merchant/profile/",
            {"business_category": self.pharmacy_activity.id}, format="json",
        )
        response = self.admin_client().patch(
            f"/api/admin/control/providers/{self.store.id}/",
            {"approval_status": "approved"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.business_category_id, self.pharmacy_activity.id)
        self.assertEqual(self.store.category, "pharmacy")
        self.assertIsNone(self.store.requested_business_category_id)
        self.assertEqual(list(self.store.services.values_list("code", flat=True)), ["pharmacy"])

    def test_admin_can_see_the_pending_request(self):
        self.merchant_client().patch(
            "/api/merchant/profile/",
            {"business_category": self.pharmacy_activity.id}, format="json",
        )
        response = self.admin_client().get("/api/admin/control/providers/")
        self.assertEqual(response.status_code, 200, response.data)
        row = next(item for item in response.data["providers"] if item["id"] == self.store.id)
        self.assertEqual(row["business_category"]["id"], self.supermarket.id)
        self.assertEqual(row["requested_business_category"]["id"], self.pharmacy_activity.id)

    def test_resubmitting_the_current_activity_withdraws_the_request(self):
        self.merchant_client().patch(
            "/api/merchant/profile/",
            {"business_category": self.pharmacy_activity.id}, format="json",
        )
        response = self.merchant_client().patch(
            "/api/merchant/profile/",
            {"business_category": self.supermarket.id}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.requested_business_category_id)
        self.assertFalse(response.data["activity_request_pending"])

    def test_inactive_activity_cannot_be_requested(self):
        response = self.merchant_client().patch(
            "/api/merchant/profile/",
            {"business_category": self.inactive_activity.id}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.store.refresh_from_db()
        self.assertIsNone(self.store.requested_business_category_id)
        self.assertEqual(self.store.business_category_id, self.supermarket.id)

    def test_pending_store_still_picks_its_activity_directly(self):
        self.store.approval_status = "pending"
        self.store.save(update_fields=["approval_status"])
        response = self.merchant_client().patch(
            "/api/merchant/profile/",
            {"business_category": self.pharmacy_activity.id}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.business_category_id, self.pharmacy_activity.id)
        self.assertIsNone(self.store.requested_business_category_id)
