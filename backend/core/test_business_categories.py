"""Business activities are database rows that link a store to one service."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AuditLog, BusinessCategory, MerchantProfile, PlatformService

User = get_user_model()


def make_service(code, name="Grocery"):
    return PlatformService.objects.create(
        code=code, name_ar=name, name_en=name, is_operational=True, is_active=True,
    )


class BusinessCategoryAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="activity-admin", password="admin-pass-123", role="admin",
        )
        self.grocery = make_service("grocery")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_creates_activity_linked_to_service(self):
        response = self.client.post(
            "/api/admin/control/business-categories/",
            {"code": "bakery", "name_ar": "مخبز", "name_en": "Bakery", "service": self.grocery.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        category = BusinessCategory.objects.get(code="bakery")
        self.assertEqual(category.service, self.grocery)
        self.assertTrue(category.is_active)
        self.assertTrue(AuditLog.objects.filter(action="business_category.create").exists())

    def test_activity_cannot_reuse_an_existing_code(self):
        BusinessCategory.objects.create(code="pharmacy", name_ar="صيدلية", name_en="Pharmacy")
        response = self.client.post(
            "/api/admin/control/business-categories/",
            {"code": "pharmacy", "name_ar": "صيدلية", "name_en": "Pharmacy"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_non_service_admin_cannot_manage_activities(self):
        support = User.objects.create_user(
            username="activity-support", password="support-pass-123", role="admin", admin_role="support",
        )
        client = APIClient()
        client.force_authenticate(support)
        response = client.get("/api/admin/control/business-categories/")
        self.assertEqual(response.status_code, 403, response.data)


class StoreServiceLinkTests(TestCase):
    def setUp(self):
        self.service = make_service("grocery")
        self.category = BusinessCategory.objects.create(
            code="supermarket", name_ar="سوبرماركت", name_en="Supermarket", service=self.service,
        )
        self.owner = User.objects.create_user(
            username="link-merchant", password="merchant-pass-123", role="merchant",
        )
        self.store = MerchantProfile.objects.create(
            user=self.owner, shop_name="سوبرماركت الأمانة", category="general",
            approval_status="pending", is_open=False,
            business_category=self.category,
        )
        self.admin = User.objects.create_user(
            username="link-admin", password="admin-pass-123", role="admin",
        )

    def test_approval_puts_the_store_in_its_service(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.patch(
            f"/api/admin/control/providers/{self.store.id}/",
            {"approval_status": "approved"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.approval_status, "approved")
        self.assertEqual(list(self.store.services.values_list("code", flat=True)), ["grocery"])

    def test_merchant_activity_choice_links_the_service(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.patch(
            "/api/merchant/profile/", {"business_category": self.category.id}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.category, "supermarket")
        self.assertEqual(self.store.service_type, "grocery")
        self.assertEqual(list(self.store.services.values_list("code", flat=True)), ["grocery"])

    def test_approved_store_activity_is_admin_controlled(self):
        self.store.approval_status = "approved"
        self.store.save(update_fields=["approval_status"])
        pharmacy_service = make_service("pharmacy", name="Pharmacy")
        other = BusinessCategory.objects.create(
            code="pharmacy", name_ar="صيدلية", name_en="Pharmacy", service=pharmacy_service,
        )
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.patch(
            "/api/merchant/profile/", {"business_category": other.id}, format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.business_category_id, self.category.id)

    def test_unknown_activity_is_rejected(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.patch(
            f"/api/admin/control/providers/{self.store.id}/",
            {"business_category": 999999}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.store.refresh_from_db()
        self.assertEqual(self.store.business_category_id, self.category.id)
