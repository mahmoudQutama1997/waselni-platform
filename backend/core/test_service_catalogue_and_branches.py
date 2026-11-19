"""Customer catalogue and order routing follow the store's real relations."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    BusinessCategory, MerchantBranch, MerchantProfile, Order, PlatformService, Product,
)

User = get_user_model()


def make_service(code, name):
    return PlatformService.objects.create(
        code=code, name_ar=name, name_en=name, is_operational=True, is_active=True,
    )


def result_rows(response):
    return response.data["results"] if isinstance(response.data, dict) else response.data


class PublicCatalogueTests(TestCase):
    """A store linked only through its activity is still fully catalogued."""

    def setUp(self):
        self.pharmacy_service = make_service("pharmacy", "Pharmacy")
        self.category = BusinessCategory.objects.create(
            code="pharmacy", name_ar="صيدلية", name_en="Pharmacy",
            service=self.pharmacy_service, requires_license=True,
        )
        self.owner = User.objects.create_user(
            username="catalogue-owner", password="owner-pass-123", role="merchant",
        )
        self.store = MerchantProfile.objects.create(
            user=self.owner, shop_name="صيدلية النور", category="general",
            approval_status="approved", is_open=True,
            latitude=Decimal("31.950000"), longitude=Decimal("35.210000"),
            business_category=self.category,
        )
        # Deliberately no ``services`` row: the activity link alone must count.
        self.otc = Product.objects.create(
            merchant=self.store, name="Paracetamol", price=Decimal("12.00"), quantity=5,
            available=True, pharmacy_review_status="approved",
        )
        self.prescription = Product.objects.create(
            merchant=self.store, name="Antibiotic", price=Decimal("25.00"), quantity=5,
            available=True, pharmacy_review_status="approved", prescription_required=True,
        )
        self.pending = Product.objects.create(
            merchant=self.store, name="New medicine", price=Decimal("9.00"), quantity=5,
            available=True,
        )
        self.customer = User.objects.create_user(
            username="catalogue-customer", password="customer-pass-123", role="customer",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def test_store_is_listed_under_the_service_of_its_activity(self):
        response = self.client.get("/api/merchants/?service=pharmacy")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.store.id, [row["id"] for row in result_rows(response)])

    def test_store_page_never_exposes_prescription_or_unreviewed_medicine(self):
        response = self.client.get(f"/api/products/?merchant={self.store.id}")
        self.assertEqual(response.status_code, 200, response.data)
        names = {row["name"] for row in result_rows(response)}
        self.assertIn("Paracetamol", names)
        self.assertNotIn("Antibiotic", names)
        self.assertNotIn("New medicine", names)


class BranchRoutingTests(TestCase):
    """An order reaches the branch the customer actually chose."""

    def setUp(self):
        self.service = make_service("grocery", "Grocery")
        self.category = BusinessCategory.objects.create(
            code="supermarket", name_ar="سوبرماركت", name_en="Supermarket",
            service=self.service,
        )
        self.owner = User.objects.create_user(
            username="branch-owner", password="owner-pass-123", role="merchant",
        )
        self.store = MerchantProfile.objects.create(
            user=self.owner, shop_name="متجر الفروع", category="supermarket",
            approval_status="approved", is_open=True,
            latitude=Decimal("31.950000"), longitude=Decimal("35.210000"),
            business_category=self.category,
        )
        self.first = MerchantBranch.objects.create(merchant=self.store, name="الفرع الأول")
        self.second = MerchantBranch.objects.create(merchant=self.store, name="الفرع الثاني")
        self.product = Product.objects.create(
            merchant=self.store, name="حليب", price=Decimal("6.00"), quantity=10,
            available=True,
        )
        self.customer = User.objects.create_user(
            username="branch-customer", password="customer-pass-123", role="customer",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def payload(self, **overrides):
        data = {
            "merchant": self.store.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "dropoff_address": "شارع النجمة",
            "dropoff_latitude": "31.960000",
            "dropoff_longitude": "35.220000",
            "delivery_fee": "10.00",
            "order_type": "store",
            "payment_method": "cash",
        }
        data.update(overrides)
        return data

    def test_order_uses_the_branch_the_customer_chose(self):
        response = self.client.post("/api/orders/", self.payload(branch=self.second.id), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.get(pk=response.data["id"]).branch_id, self.second.id)

    def test_order_defaults_to_the_first_active_branch(self):
        response = self.client.post("/api/orders/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Order.objects.get(pk=response.data["id"]).branch_id, self.first.id)

    def test_another_store_branch_is_rejected(self):
        other_owner = User.objects.create_user(
            username="other-owner", password="owner-pass-123", role="merchant",
        )
        other_store = MerchantProfile.objects.create(
            user=other_owner, shop_name="متجر آخر", category="supermarket",
            approval_status="approved", is_open=True,
        )
        foreign = MerchantBranch.objects.create(merchant=other_store, name="فرع غريب")
        response = self.client.post("/api/orders/", self.payload(branch=foreign.id), format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("branch", response.data)
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())
