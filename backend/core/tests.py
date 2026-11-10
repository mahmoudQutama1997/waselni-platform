from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import MerchantProfile, Order, Product
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
class ProductModelTests(TestCase):
    def test_merchant_product_availability(self):
        u=get_user_model().objects.create_user(username="shop",password="test-password-123",role="merchant")
        m=MerchantProfile.objects.create(user=u,shop_name="Demo Market")
        p=Product.objects.create(merchant=m,name="Water",price=Decimal("2.50"))
        self.assertTrue(p.available)

class CentralAccountSubscriptionTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.admin = get_user_model().objects.create_user(
            username="platform-admin", password="admin-password-123", role="admin"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_creates_identity_based_customer_account(self):
        response = self.client.post("/api/admin/users/", {
            "identity_number": "987654321", "first_name": "Demo", "last_name": "Customer",
            "phone": "0590000000", "role": "customer"
        }, format="json")
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(identity_number="987654321")
        self.assertEqual(user.username, "987654321")
        self.assertTrue(user.must_change_password)
        self.assertTrue(user.check_password(response.data["temporary_password"]))

    def test_admin_sets_individual_subscription(self):
        user = get_user_model().objects.create_user(
            username="captain-id", password="temporary-password", role="captain", subscription_required=True
        )
        response = self.client.post(f"/api/admin/users/{user.id}/subscription/", {
            "amount": "35.00", "months": 2, "starts_on": timezone.localdate().isoformat(), "status": "active"
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["amount"], "35.00")
        self.assertEqual(response.data["total_due"], "70.00")

    def test_admin_subscription_ledger_and_status_change(self):
        from .models import Subscription
        user = get_user_model().objects.create_user(
            username="ledger-captain", password="captain-password-123", role="captain", subscription_required=True
        )
        today = timezone.localdate()
        sub = Subscription.objects.create(
            user=user, amount=Decimal("40.00"), months=1, starts_on=today,
            ends_on=today + timedelta(days=30), status="active"
        )
        response = self.client.get("/api/admin/subscriptions/")
        self.assertEqual(response.status_code, 200)
        row = next(item for item in response.data if item["id"] == sub.id)
        self.assertTrue(row["is_current"])
        self.assertEqual(row["user_id"], user.id)
        changed = self.client.patch(f"/api/admin/subscriptions/{sub.id}/", {"status": "pending"}, format="json")
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(changed.data["subscription_active"])

    def test_public_registration_cannot_create_privileged_roles(self):
        from rest_framework.test import APIClient
        client = APIClient()
        response = client.post("/api/auth/register/", {
            "username": "open-merchant", "password": "long-password", "first_name": "Open",
            "phone": "0590000001", "role": "merchant", "shop_name": "Unapproved store"
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(username="open-merchant").exists())

    def test_public_registration_creates_customers(self):
        from rest_framework.test import APIClient
        client = APIClient()
        response = client.post("/api/auth/register/", {
            "username": "open-customer", "password": "long-password", "first_name": "Open",
            "phone": "0590000002", "role": "customer"
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["role"], "customer")

    def test_merchant_preparation_time_rejects_unsupported_value(self):
        from rest_framework.test import APIClient
        merchant_user = get_user_model().objects.create_user(
            username="prep-merchant", password="merchant-password-123", role="merchant"
        )
        customer = get_user_model().objects.create_user(
            username="prep-customer", password="customer-password-123", role="customer"
        )
        store = MerchantProfile.objects.create(user=merchant_user, shop_name="Prep Market")
        order = Order.objects.create(customer=customer, merchant=store, order_type="store", status="new")
        client = APIClient()
        client.force_authenticate(merchant_user)
        response = client.post(f"/api/orders/{order.id}/accept/", {"prep_minutes": 35}, format="json")
        self.assertEqual(response.status_code, 400)

class RideRequestTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.customer = get_user_model().objects.create_user(
            username="ride-customer", password="customer-password-123", role="customer"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def test_customer_can_create_ride_with_coordinates(self):
        response = self.client.post("/api/orders/ride/", {
            "pickup_address": "Pickup point", "dropoff_address": "Destination",
            "pickup_latitude": 31.7683, "pickup_longitude": 35.2137,
            "dropoff_latitude": 31.7800, "dropoff_longitude": 35.2200,
            "requires_checkpoint": True
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["order_type"], "ride")
        self.assertEqual(response.data["status"], "new")
        self.assertEqual(response.data["checkpoint_fee"], "15.00")
        self.assertGreater(float(response.data["total"]), 15)

    def test_ride_requires_both_coordinate_pairs(self):
        response = self.client.post("/api/orders/ride/", {
            "pickup_address": "Pickup point", "dropoff_address": "Destination"
        }, format="json")
        self.assertEqual(response.status_code, 400)

class CaptainStatusConsistencyTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from .models import CaptainProfile, Subscription
        self.User = get_user_model()
        self.admin = self.User.objects.create_user(
            username="status-admin", password="admin-password-123", role="admin"
        )
        self.captain = self.User.objects.create_user(
            username="yusuf-test", password="captain-password-123", role="captain",
            subscription_required=True,
        )
        self.profile = CaptainProfile.objects.create(
            user=self.captain, approved=True, online=False, vehicle_type="motorcycle"
        )
        today = timezone.localdate()
        Subscription.objects.create(
            user=self.captain, amount=Decimal("35.00"), months=1,
            starts_on=today, ends_on=today + timedelta(days=30), status="active",
        )
        self.client = APIClient()

    def test_admin_and_captain_both_report_missing_subscription_as_inactive(self):
        from .models import Subscription
        Subscription.objects.filter(user=self.captain).delete()
        self.client.force_authenticate(self.captain)
        captain_response = self.client.get("/api/captains/me/")
        self.assertEqual(captain_response.status_code, 200)
        self.assertFalse(captain_response.data["subscription_active"])
        self.client.force_authenticate(self.admin)
        admin_response = self.client.get("/api/admin/operations/")
        row = next(x for x in admin_response.data["captains"] if x["user_id"] == self.captain.id)
        self.assertFalse(row["subscription_active"])

    def test_captain_api_and_admin_report_same_approved_subscription_state(self):
        self.client.force_authenticate(self.captain)
        captain_response = self.client.get("/api/captains/me/")
        self.assertEqual(captain_response.status_code, 200)
        self.assertTrue(captain_response.data["approved"])
        self.assertTrue(captain_response.data["subscription_active"])
        self.assertEqual(captain_response.data["user_id"], self.captain.id)

        self.client.force_authenticate(self.admin)
        admin_response = self.client.get("/api/admin/operations/")
        self.assertEqual(admin_response.status_code, 200)
        row = next(x for x in admin_response.data["captains"] if x["id"] == self.profile.id)
        self.assertEqual(row["user_id"], self.captain.id)
        self.assertTrue(row["approved"])
        self.assertTrue(row["subscription_active"])

class StoreDeliveryPricingTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.customer = get_user_model().objects.create_user(
            username="map-customer", password="customer-password-123", role="customer"
        )
        merchant_user = get_user_model().objects.create_user(
            username="map-merchant", password="merchant-password-123", role="merchant"
        )
        self.store = MerchantProfile.objects.create(
            user=merchant_user, shop_name="Map Store", address="Nablus",
            latitude=Decimal("32.2211"), longitude=Decimal("35.2544"),
        )
        self.product = Product.objects.create(
            merchant=self.store, name="Test item", price=Decimal("8.00")
        )
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def test_store_order_saves_customer_proposed_delivery_fee_and_total(self):
        response = self.client.post("/api/orders/", {
            "merchant": self.store.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "dropoff_address": "Nablus centre",
            "dropoff_latitude": 32.2217,
            "dropoff_longitude": 35.2550,
            "delivery_fee": "12.50",
            "payment_method": "cash",
            "order_type": "store",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["subtotal"], "16.00")
        self.assertEqual(response.data["delivery_fee"], "12.50")
        self.assertEqual(response.data["total"], "28.50")
        self.assertEqual(float(response.data["pickup_latitude"]), float(self.store.latitude))

    def test_store_order_requires_customer_coordinates_and_delivery_fee(self):
        response = self.client.post("/api/orders/", {
            "merchant": self.store.id,
            "items": [{"product_id": self.product.id, "quantity": 1}],
            "dropoff_address": "Nablus centre",
            "payment_method": "cash",
            "order_type": "store",
        }, format="json")
        self.assertEqual(response.status_code, 400)


class CashSettlementAfterDeliveryTests(TestCase):
    def test_store_cash_settlement_is_created_only_after_completion(self):
        from rest_framework.test import APIClient
        from .models import CaptainProfile, CashSettlement
        User = get_user_model()
        customer = User.objects.create_user(username="settle-customer", password="password-123")
        merchant_user = User.objects.create_user(username="settle-merchant", password="password-123", role="merchant")
        captain_user = User.objects.create_user(username="settle-captain", password="password-123", role="captain")
        store = MerchantProfile.objects.create(user=merchant_user, shop_name="Settlement Store")
        captain = CaptainProfile.objects.create(user=captain_user)
        order = Order.objects.create(
            customer=customer, merchant=store, captain=captain, order_type="store",
            status="delivering", payment_method="cash", subtotal=Decimal("40.00"),
            delivery_fee=Decimal("10.00"), total=Decimal("50.00"),
        )
        self.assertFalse(CashSettlement.objects.filter(order=order).exists())
        client = APIClient()
        client.force_authenticate(captain_user)
        response = client.post(f"/api/orders/{order.id}/status/", {"status": "completed"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        settlement = CashSettlement.objects.get(order=order)
        self.assertEqual(settlement.amount, Decimal("40.00"))
        self.assertFalse(settlement.closed)

    def test_captain_must_confirm_exact_delivery_price(self):
        from rest_framework.test import APIClient
        from .models import CaptainProfile
        captain_user = get_user_model().objects.create_user(username="price-captain", password="password-123", role="captain")
        CaptainProfile.objects.create(user=captain_user)
        customer = get_user_model().objects.create_user(username="price-customer", password="password-123")
        order = Order.objects.create(customer=customer, order_type="ride", status="new", delivery_fee=Decimal("17.50"))
        client = APIClient()
        client.force_authenticate(captain_user)
        missing = client.post(f"/api/orders/{order.id}/assign/", {}, format="json")
        self.assertEqual(missing.status_code, 400)
        wrong = client.post(f"/api/orders/{order.id}/assign/", {"accepted_delivery_fee": "18.00"}, format="json")
        self.assertEqual(wrong.status_code, 409)
