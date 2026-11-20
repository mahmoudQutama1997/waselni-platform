"""Approved stores must keep saving their profile without an activity change.

The merchant form always posts the current business activity together with the
ordinary store fields. That value is not a change request unless it actually
differs, and a blank value must never clear an approved store's activity.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BusinessCategory, MerchantProfile, PlatformService

User = get_user_model()


def make_service(code, name="Grocery"):
    return PlatformService.objects.create(
        code=code, name_ar=name, name_en=name, is_operational=True, is_active=True,
    )


class ApprovedMerchantProfileSaveTests(TestCase):
    def setUp(self):
        self.grocery = make_service("grocery")
        self.pharmacy = make_service("pharmacy", name="Pharmacy")
        self.activity = BusinessCategory.objects.create(
            code="supermarket", name_ar="سوبرماركت", name_en="Supermarket", service=self.grocery,
        )
        self.other_activity = BusinessCategory.objects.create(
            code="pharmacy", name_ar="صيدلية", name_en="Pharmacy", service=self.pharmacy,
        )
        self.owner = User.objects.create_user(
            username="approved-merchant", password="merchant-pass-123", role="merchant",
        )
        self.store = MerchantProfile.objects.create(
            user=self.owner,
            shop_name="سوبرماركت الأمانة",
            category="supermarket",
            description="متجر الحي",
            address="نابلس - شارع تونس",
            opening_hours="8:00 - 22:00",
            latitude="32.221100",
            longitude="35.254400",
            prep_minutes=20,
            approval_status="approved",
            business_category=self.activity,
        )
        self.store.services.add(self.grocery)
        self.admin = User.objects.create_user(
            username="approved-admin", password="admin-pass-123", role="admin",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def assert_store_intact(self):
        self.store.refresh_from_db()
        self.assertEqual(self.store.business_category_id, self.activity.id)
        self.assertEqual(self.store.category, "supermarket")
        self.assertEqual(list(self.store.services.values_list("code", flat=True)), ["grocery"])
        return self.store

    def test_approved_merchant_saves_profile_with_unchanged_activity(self):
        response = self.client.patch(
            "/api/merchant/profile/",
            {"shop_name": "سوبرماركت الأمانة الجديد", "business_category": self.activity.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store = self.assert_store_intact()
        self.assertEqual(store.shop_name, "سوبرماركت الأمانة الجديد")
        self.assertEqual(response.data["business_category"], self.activity.id)
        self.assertEqual(response.data["service_type"], "grocery")

    def test_approved_merchant_updates_ordinary_profile_fields(self):
        response = self.client.patch(
            "/api/merchant/profile/",
            {
                "shop_name": "أمانة ماركت",
                "description": "وصف محدّث",
                "address": "نابلس - رفيديا",
                "opening_hours": "9:00 - 23:00",
                "latitude": "32.225000",
                "longitude": "35.240000",
                "prep_minutes": 25,
                "temporarily_closed": True,
                "business_category": self.activity.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store = self.assert_store_intact()
        self.assertEqual(store.shop_name, "أمانة ماركت")
        self.assertEqual(store.description, "وصف محدّث")
        self.assertEqual(store.address, "نابلس - رفيديا")
        self.assertEqual(store.opening_hours, "9:00 - 23:00")
        self.assertEqual(store.prep_minutes, 25)
        self.assertTrue(store.temporarily_closed)
        self.assertEqual(str(store.latitude), "32.225000")

    def test_same_activity_id_as_text_is_accepted(self):
        # Multipart/FormData clients send every value as text.
        response = self.client.patch(
            "/api/merchant/profile/",
            {"description": "نص من الفورم", "business_category": str(self.activity.id)},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store = self.assert_store_intact()
        self.assertEqual(store.description, "نص من الفورم")

    def test_approved_merchant_activity_change_becomes_a_request(self):
        response = self.client.patch(
            "/api/merchant/profile/",
            {"shop_name": "سوبرماركت الأمانة", "business_category": self.other_activity.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store = self.assert_store_intact()
        # The store cannot rewrite its own approved activity, but the choice is
        # kept as a review request instead of being thrown away.
        self.assertEqual(store.requested_business_category_id, self.other_activity.id)
        self.assertTrue(response.data["activity_request_pending"])
        self.assertEqual(store.shop_name, "سوبرماركت الأمانة")

    def test_admin_can_change_activity_of_approved_store(self):
        admin_client = APIClient()
        admin_client.force_authenticate(self.admin)
        response = admin_client.patch(
            f"/api/admin/control/providers/{self.store.id}/",
            {"business_category": self.other_activity.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.business_category_id, self.other_activity.id)
        self.assertEqual(self.store.category, "pharmacy")
        # No store data is lost by an administrative activity change.
        self.assertEqual(self.store.description, "متجر الحي")
        self.assertEqual(self.store.address, "نابلس - شارع تونس")
        self.assertEqual(list(self.store.services.values_list("code", flat=True)), ["grocery"])

    def test_blank_activity_never_clears_an_approved_store(self):
        response = self.client.patch(
            "/api/merchant/profile/",
            {"address": "نابلس - المخفية", "business_category": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store = self.assert_store_intact()
        self.assertEqual(store.address, "نابلس - المخفية")
        self.assertEqual(store.description, "متجر الحي")
        self.assertEqual(store.opening_hours, "8:00 - 22:00")
        self.assertEqual(response.data["business_category"], self.activity.id)

    def test_profile_save_without_activity_key_keeps_the_relation(self):
        response = self.client.patch(
            "/api/merchant/profile/", {"opening_hours": "10:00 - 20:00"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        store = self.assert_store_intact()
        self.assertEqual(store.opening_hours, "10:00 - 20:00")
        self.assertEqual(store.description, "متجر الحي")
