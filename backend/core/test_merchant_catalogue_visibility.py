"""Every approved, open store must reach the service its console row shows.

The customer catalogue used to return every open store. Once it started
filtering by service, a store that administration listed as Food could still be
missing from the customer app: a store created from the console's merchant form
keeps ``category="general"`` and has no activity or service row, while
``MerchantProfile.service_type`` (what the admin and merchant screens show)
resolves it to the generic food flow. These tests pin that agreement, and they
also pin the gates that must keep hiding stores: approval, open state and an
active subscription.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BusinessCategory, MerchantProfile, PlatformService, Product

User = get_user_model()


def make_service(code, name):
    return PlatformService.objects.create(
        code=code, name_ar=name, name_en=name, is_operational=True, is_active=True,
    )


def make_category(code, name, service=None):
    return BusinessCategory.objects.create(
        code=code, name_ar=name, name_en=name, service=service,
    )


def result_rows(response):
    return response.data["results"] if isinstance(response.data, dict) else response.data


class CatalogueVisibilityTestCase(TestCase):
    def setUp(self):
        self.food = make_service("food", "Food delivery")
        self.grocery = make_service("grocery", "Grocery & supermarket")
        self.pharmacy = make_service("pharmacy", "Pharmacy")
        self.restaurant_activity = make_category("restaurant", "مطعم", self.food)
        self.supermarket_activity = make_category("supermarket", "سوبرماركت", self.grocery)
        self.pharmacy_activity = make_category("pharmacy", "صيدلية", self.pharmacy)
        self.customer = User.objects.create_user(
            username="catalogue-customer", password="customer-pass-123", role="customer",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def make_store(self, name, **overrides):
        owner = User.objects.create_user(
            username=f"owner-{name}", password="owner-pass-123", role="merchant",
        )
        data = {
            "user": owner,
            "shop_name": name,
            "category": "general",
            "approval_status": "approved",
            "is_open": True,
            "latitude": Decimal("31.950000"),
            "longitude": Decimal("35.210000"),
        }
        data.update(overrides)
        return MerchantProfile.objects.create(**data)

    def listed_ids(self, service):
        response = self.client.get(f"/api/merchants/?service={service}")
        self.assertEqual(response.status_code, 200, response.data)
        return [row["id"] for row in result_rows(response)]

    def shelf_names(self, store, service="food"):
        response = self.client.get(f"/api/products/?merchant={store.id}&service={service}")
        self.assertEqual(response.status_code, 200, response.data)
        return {row["name"] for row in result_rows(response)}


class ApprovedRestaurantVisibilityTests(CatalogueVisibilityTestCase):
    def test_store_linked_through_its_restaurant_activity_is_listed(self):
        store = self.make_store("مطعم الأصيل", category="restaurant",
                                business_category=self.restaurant_activity)
        self.assertIn(store.id, self.listed_ids("food"))

    def test_store_without_activity_still_reaches_the_food_catalogue(self):
        """Regression: this store used to disappear from the customer app."""
        store = self.make_store("مطعم بلا نشاط")
        # Administration and the merchant screen report it as a food store, so
        # the customer app must show it too instead of hiding it silently.
        self.assertEqual(store.service_type, "food")
        self.assertIn(store.id, self.listed_ids("food"))

    def test_its_products_are_on_the_same_shelf(self):
        store = self.make_store("مطعم بلا نشاط")
        Product.objects.create(
            merchant=store, name="شاورما", price=Decimal("18.00"), quantity=10, available=True,
        )
        self.assertIn(store.id, self.listed_ids("food"))
        self.assertEqual(self.shelf_names(store), {"شاورما"})

    def test_blank_category_store_is_listed_once(self):
        store = self.make_store("مطعم قديم", category="")
        ids = self.listed_ids("food")
        self.assertEqual(ids.count(store.id), 1)


class ApprovalAndBillingGatesStayEnforcedTests(CatalogueVisibilityTestCase):
    def test_closed_store_is_not_listed(self):
        store = self.make_store("مطعم مغلق", is_open=False)
        self.assertNotIn(store.id, self.listed_ids("food"))

    def test_paused_store_is_not_listed(self):
        store = self.make_store("مطعم موقوف مؤقتاً", temporarily_closed=True)
        self.assertNotIn(store.id, self.listed_ids("food"))

    def test_pending_store_is_not_listed(self):
        store = self.make_store("مطعم قيد المراجعة", approval_status="pending")
        self.assertNotIn(store.id, self.listed_ids("food"))

    def test_rejected_store_is_not_listed(self):
        store = self.make_store("مطعم مرفوض", approval_status="rejected")
        self.assertNotIn(store.id, self.listed_ids("food"))

    def test_suspended_store_is_not_listed(self):
        store = self.make_store("مطعم موقوف", approval_status="suspended")
        self.assertNotIn(store.id, self.listed_ids("food"))

    def test_store_without_an_active_subscription_is_not_listed(self):
        store = self.make_store("مطعم بلا اشتراك")
        store.user.subscription_required = True
        store.user.save(update_fields=["subscription_required"])
        self.assertNotIn(store.id, self.listed_ids("food"))


class ServiceIsolationTests(CatalogueVisibilityTestCase):
    def test_supermarket_stays_out_of_the_food_catalogue(self):
        store = self.make_store("سوبرماركت الحي", category="supermarket",
                                business_category=self.supermarket_activity)
        self.assertNotIn(store.id, self.listed_ids("food"))
        self.assertIn(store.id, self.listed_ids("grocery"))

    def test_pharmacy_stays_out_of_the_food_catalogue(self):
        store = self.make_store("صيدلية الشفاء", category="pharmacy",
                                business_category=self.pharmacy_activity)
        self.assertNotIn(store.id, self.listed_ids("food"))
        self.assertIn(store.id, self.listed_ids("pharmacy"))

    def test_supermarket_product_shelf_is_not_the_food_shelf(self):
        store = self.make_store("سوبرماركت الحي", category="supermarket",
                                business_category=self.supermarket_activity)
        Product.objects.create(
            merchant=store, name="حليب", price=Decimal("6.00"), quantity=10, available=True,
        )
        self.assertEqual(self.shelf_names(store, "grocery"), {"حليب"})
        self.assertEqual(self.shelf_names(store, "food"), set())
