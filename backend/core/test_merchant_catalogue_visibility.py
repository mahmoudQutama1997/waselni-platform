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

from .models import BusinessCategory, MerchantBranch, MerchantProfile, PlatformService, Product

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


class UnlinkedActivityClassificationTests(CatalogueVisibilityTestCase):
    """The catalogue must follow ``service_type`` when an activity has no service.

    An activity row can exist while its ``service`` relation was never filled in
    (older console data, or a line such as "Bakery"). ``service_type`` then falls
    back to the legacy category and finally to the implemented food flow, so the
    customer catalogue has to resolve the store the same way.
    """

    def test_activity_without_a_service_link_still_sells_under_food(self):
        bakery = make_category("bakery_unlinked", "مخبز")
        store = self.make_store("مخبز بلا خدمة", category="bakery", business_category=bakery)
        self.assertEqual(store.service_type, "food")
        self.assertIn(store.id, self.listed_ids("food"))

    def test_restaurant_activity_without_a_service_link_is_listed(self):
        activity = make_category("restaurant_unlinked", "مطعم بلا خدمة")
        store = self.make_store("مطعم الأصيل", category="restaurant", business_category=activity)
        self.assertIn(store.id, self.listed_ids("food"))

    def test_blank_category_with_an_unlinked_activity_is_listed(self):
        activity = make_category("unclassified_unlinked", "نشاط بلا خدمة")
        store = self.make_store("متجر بلا تصنيف", category="", business_category=activity)
        self.assertIn(store.id, self.listed_ids("food"))

    def test_supermarket_without_a_service_link_stays_out_of_food(self):
        supermarket = make_category("supermarket_unlinked", "سوبرماركت")
        store = self.make_store("سوبرماركت بلا خدمة", category="supermarket",
                                business_category=supermarket)
        self.assertNotIn(store.id, self.listed_ids("food"))
        self.assertIn(store.id, self.listed_ids("grocery"))

    def test_pharmacy_without_a_service_link_stays_out_of_food(self):
        pharmacy = make_category("pharmacy_unlinked", "صيدلية")
        store = self.make_store("صيدلية بلا خدمة", category="pharmacy",
                                business_category=pharmacy)
        self.assertNotIn(store.id, self.listed_ids("food"))
        self.assertIn(store.id, self.listed_ids("pharmacy"))

    def test_stale_legacy_category_never_adds_the_store_to_a_second_service(self):
        activity = make_category("supermarket_linked", "سوبرماركت", self.grocery)
        store = self.make_store("سوبرماركت الحي", category="restaurant",
                                business_category=activity)
        self.assertNotIn(store.id, self.listed_ids("food"))
        self.assertEqual(self.listed_ids("grocery").count(store.id), 1)

    def test_product_shelf_follows_the_same_classification(self):
        bakery = make_category("bakery_shelf", "مخبز")
        store = self.make_store("مخبز الرف", category="bakery", business_category=bakery)
        Product.objects.create(
            merchant=store, name="خبز", price=Decimal("3.00"), quantity=5, available=True,
        )
        self.assertEqual(self.shelf_names(store, "food"), {"خبز"})


class CatalogueFollowsStoreStateTests(CatalogueVisibilityTestCase):
    """Approval and open state changes reach the customer list immediately."""

    def test_store_is_listed_after_administration_approves_it(self):
        store = self.make_store("مطعم قيد المراجعة", approval_status="pending")
        self.assertNotIn(store.id, self.listed_ids("food"))
        store.approval_status = "approved"
        store.is_open = True
        store.save(update_fields=["approval_status", "is_open"])
        self.assertIn(store.id, self.listed_ids("food"))

    def test_store_leaves_the_catalogue_when_it_is_suspended(self):
        store = self.make_store("مطعم الأصيل")
        self.assertIn(store.id, self.listed_ids("food"))
        store.approval_status = "suspended"
        store.is_open = False
        store.save(update_fields=["approval_status", "is_open"])
        self.assertNotIn(store.id, self.listed_ids("food"))

    def test_only_active_branches_are_published_to_customers(self):
        store = self.make_store("مطعم بفرعين")
        MerchantBranch.objects.create(merchant=store, name="الفرع النشط", is_active=True)
        MerchantBranch.objects.create(merchant=store, name="الفرع المغلق", is_active=False)
        response = self.client.get("/api/merchants/?service=food")
        self.assertEqual(response.status_code, 200, response.data)
        row = next(item for item in result_rows(response) if item["id"] == store.id)
        self.assertEqual([branch["name"] for branch in row["branches"]], ["الفرع النشط"])


class ProductShelfAvailabilityTests(CatalogueVisibilityTestCase):
    """The shelf follows stock and the store's own availability flag."""

    def setUp(self):
        super().setUp()
        self.store = self.make_store("مطعم الرف")

    def make_product(self, **overrides):
        data = {
            "merchant": self.store, "name": "طبق", "price": Decimal("10.00"),
            "quantity": 5, "available": True,
        }
        data.update(overrides)
        return Product.objects.create(**data)

    def test_hidden_product_is_not_on_the_shelf(self):
        self.make_product(name="مخفي", available=False)
        self.assertEqual(self.shelf_names(self.store), set())

    def test_sold_out_product_stays_visible_as_out_of_stock(self):
        self.make_product(name="منتهي", quantity=0)
        self.assertEqual(self.shelf_names(self.store), {"منتهي"})
        self.assertEqual(Product.objects.get(name="منتهي").stock_status, "out")

    def test_limited_stock_product_is_flagged_low(self):
        self.make_product(name="محدود", quantity=2)
        self.assertEqual(Product.objects.get(name="محدود").stock_status, "low")

    def test_store_without_products_has_an_empty_shelf(self):
        self.assertEqual(self.shelf_names(self.store), set())


class AdminVisibilityDiagnosticsTests(CatalogueVisibilityTestCase):
    """The admin console explains why a store is missing from the app."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            username="visibility-admin", password="admin-pass-123", role="admin",
        )
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)

    def provider_row(self, store):
        response = self.admin_client.get("/api/admin/control/providers/")
        self.assertEqual(response.status_code, 200, response.data)
        return next(row for row in response.data["providers"] if row["id"] == store.id)

    def test_approved_open_store_is_reported_visible(self):
        store = self.make_store("مطعم ظاهر")
        row = self.provider_row(store)
        self.assertTrue(row["catalogue_visibility"]["visible"])
        self.assertEqual(row["catalogue_visibility"]["reasons"], [])
        self.assertEqual(row["catalogue_visibility"]["service"], "food")

    def test_hidden_store_reports_every_reason(self):
        store = self.make_store("مطعم مخفي", approval_status="pending", is_open=False)
        row = self.provider_row(store)
        self.assertFalse(row["catalogue_visibility"]["visible"])
        self.assertIn("approval_pending", row["catalogue_visibility"]["reasons"])
        self.assertIn("closed", row["catalogue_visibility"]["reasons"])
