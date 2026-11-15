"""Inventory reservations, stock restoration and in-app notifications."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading
import time
import uuid

from django.contrib.auth import get_user_model
from django.db import OperationalError, connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from .models import CaptainProfile, MerchantProfile, Notification, Order, Product

User = get_user_model()


class InventoryNotificationTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="inv-customer", password="test-password-123", role="customer",
            first_name="Sami", last_name="Tester")
        self.merchant_user = User.objects.create_user(
            username="inv-merchant", password="test-password-123", role="merchant")
        self.merchant = MerchantProfile.objects.create(
            user=self.merchant_user, shop_name="Inv Market", address="Market Street",
            latitude=Decimal("31.949934"), longitude=Decimal("35.213710"), is_open=True)
        self.other_merchant_user = User.objects.create_user(
            username="inv-merchant-2", password="test-password-123", role="merchant")
        self.other_merchant = MerchantProfile.objects.create(
            user=self.other_merchant_user, shop_name="Other Market", address="Other Street",
            latitude=Decimal("31.950000"), longitude=Decimal("35.220000"), is_open=True)
        self.captain_user = User.objects.create_user(
            username="inv-captain", password="test-password-123", role="captain")
        self.captain = CaptainProfile.objects.create(
            user=self.captain_user, approved=True, online=True, vehicle_type="motorcycle",
            vehicle_model="Model", plate_number="12345", license_verified=True,
            insurance_verified=True, digital_undertaking_signed_at="2026-01-01T00:00:00Z")
        self.admin = User.objects.create_user(
            username="inv-admin", password="test-password-123", role="admin")
        self.product = Product.objects.create(
            merchant=self.merchant, name="Milk", price=Decimal("6.50"),
            available=True, quantity=10, low_stock_threshold=5)
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def payload(self, quantity=2, **overrides):
        data = {
            "merchant": self.merchant.id,
            "items": [{"product_id": self.product.id, "quantity": quantity}],
            "dropoff_address": "Home",
            "dropoff_latitude": 31.949934,
            "dropoff_longitude": 35.213710,
            "delivery_fee": "10.00",
            "order_type": "store",
        }
        data.update(overrides)
        return data

    def create_order(self, quantity=2, **kwargs):
        response = self.client.post("/api/orders/", self.payload(quantity, **kwargs), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Order.objects.get(pk=response.data["id"])

    # --- inventory ---------------------------------------------------------
    def test_product_stock_status(self):
        self.assertEqual(self.product.stock_status, "in")
        self.product.quantity = 5
        self.product.save(update_fields=["quantity"])
        self.assertEqual(Product.objects.get(pk=self.product.pk).stock_status, "low")
        self.product.quantity = 0
        self.product.save()
        self.assertEqual(Product.objects.get(pk=self.product.pk).stock_status, "out")

    def test_order_decrements_stock_and_stores_tracked_flag(self):
        order = self.create_order(3)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 7)
        self.assertTrue(order.items[0]["stock_tracked"])

    def test_insufficient_stock_is_rejected_and_notified(self):
        response = self.client.post("/api/orders/", self.payload(11), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)
        self.assertTrue(Notification.objects.filter(user=self.customer, event="stock.out").exists())

    def test_idempotent_retry_reserves_stock_once(self):
        key = str(uuid.uuid4())
        first = self.client.post("/api/orders/", self.payload(2), format="json", HTTP_IDEMPOTENCY_KEY=key)
        second = self.client.post("/api/orders/", self.payload(2), format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 8)

    def test_low_stock_and_out_of_stock_notifications_fire_on_crossing(self):
        self.product.quantity = 6
        self.product.save(update_fields=["quantity"])
        self.create_order(2)  # 6 -> 4 crosses the threshold (5)
        self.assertTrue(Notification.objects.filter(user=self.merchant_user, event="stock.low").exists())
        self.product.refresh_from_db()
        self.create_order(4)  # 4 -> 0
        self.assertTrue(Notification.objects.filter(user=self.merchant_user, event="stock.out").exists())
        self.assertTrue(Notification.objects.filter(user=self.admin, event="stock.out").exists())
        # A second order cannot be created once the count reaches zero.
        response = self.client.post("/api/orders/", self.payload(1), format="json")
        self.assertEqual(response.status_code, 400)

    def test_customer_cancel_restores_stock_once(self):
        order = self.create_order(2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 8)
        response = self.client.post(f"/api/orders/{order.id}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)
        self.assertIsNotNone(order.stock_restored_at)
        # A second cancellation is refused and cannot restore stock twice.
        again = self.client.post(f"/api/orders/{order.id}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(again.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_admin_cancel_after_accept_restores_stock_once(self):
        order = self.create_order(2)
        accepted = self.client_for(self.merchant_user).post(
            f"/api/orders/{order.id}/accept/", {"prep_minutes": 10}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        cancelled = self.client_for(self.admin).post(
            f"/api/orders/{order.id}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_merchant_reject_restores_stock(self):
        order = self.create_order(2)
        rejected = self.client_for(self.merchant_user).post(
            f"/api/orders/{order.id}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(rejected.data["status"], "cancelled")
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_untracked_product_cannot_be_ordered(self):
        # A missing count must never mean "unlimited": the merchant's ceiling
        # only exists once a quantity is stored.
        self.product.quantity = None
        self.product.save(update_fields=["quantity"])
        response = self.client.post("/api/orders/", self.payload(1), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(response.data["stock"][0]["reason"], "untracked")
        self.assertEqual(str(response.data["stock"][0]["available"]), "0")
        self.product.refresh_from_db()
        self.assertIsNone(self.product.quantity)

    # --- merchant tracking -------------------------------------------------
    def active_order_with_captain(self):
        order = self.create_order(1)
        order.captain = self.captain
        order.status = "assigned"
        order.save(update_fields=["captain", "status"])
        self.captain.current_latitude = Decimal("31.951000")
        self.captain.current_longitude = Decimal("35.215000")
        from django.utils import timezone
        self.captain.current_location_updated_at = timezone.now()
        self.captain.save()
        return order

    def test_tracking_is_scoped_to_the_merchant_active_order(self):
        order = self.active_order_with_captain()
        response = self.client_for(self.merchant_user).get("/api/orders/tracking/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [order.id])
        self.assertEqual(float(response.data[0]["captain_latitude"]), 31.951)
        self.assertEqual(float(response.data[0]["captain_longitude"]), 35.215)
        other = self.client_for(self.other_merchant_user).get("/api/orders/tracking/")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data, [])
        self.assertEqual(self.client_for(self.captain_user).get("/api/orders/tracking/").status_code, 403)
        self.assertEqual(self.client.get("/api/orders/tracking/").status_code, 403)

    def test_tracking_hides_location_when_order_not_active(self):
        order = self.active_order_with_captain()
        order.status = "completed"
        order.save(update_fields=["status"])
        response = self.client_for(self.merchant_user).get("/api/orders/tracking/")
        self.assertEqual(response.data, [])
        detail = self.client_for(self.merchant_user).get(f"/api/orders/{order.id}/")
        self.assertIsNone(detail.data["captain_latitude"])

    # --- notifications -----------------------------------------------------
    def test_order_creation_notifies_merchant_and_admin_only(self):
        self.create_order(1)
        self.assertTrue(Notification.objects.filter(user=self.merchant_user, event="order.created").exists())
        self.assertTrue(Notification.objects.filter(user=self.admin, event="order.created").exists())
        self.assertFalse(Notification.objects.filter(user=self.other_merchant_user).exists())
        self.assertFalse(Notification.objects.filter(user=self.customer).exists())

    def test_status_change_notifies_customer(self):
        order = self.create_order(1)
        accepted = self.client_for(self.merchant_user).post(
            f"/api/orders/{order.id}/accept/", {"prep_minutes": 15}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertTrue(Notification.objects.filter(
            user=self.customer, event="order.accepted", order=order).exists())
        ready = self.client_for(self.merchant_user).post(
            f"/api/orders/{order.id}/status/", {"status": "ready"}, format="json")
        self.assertEqual(ready.status_code, 200, ready.data)
        self.assertTrue(Notification.objects.filter(
            user=self.customer, event="order.ready", order=order).exists())

    def test_notifications_are_private_and_markable(self):
        self.create_order(1)
        merchant_client = self.client_for(self.merchant_user)
        listing = merchant_client.get("/api/notifications/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["unread"], 1)
        row = listing.data["results"][0]
        self.assertEqual(row["event"], "order.created")
        # Another user cannot mark this notification as read.
        forbidden = self.client_for(self.other_merchant_user).post(
            f"/api/notifications/{row['id']}/read/", {}, format="json")
        self.assertEqual(forbidden.status_code, 404)
        marked = merchant_client.post(f"/api/notifications/{row['id']}/read/", {}, format="json")
        self.assertEqual(marked.status_code, 200)
        self.assertTrue(marked.data["is_read"])
        self.assertEqual(merchant_client.get("/api/notifications/").data["unread"], 0)
        # Reading all only touches the caller's own notifications.
        self.create_order(1)
        merchant_client.post("/api/notifications/read-all/", {}, format="json")
        self.assertEqual(merchant_client.get("/api/notifications/").data["unread"], 0)
        self.assertEqual(self.client_for(self.admin).get("/api/notifications/").data["unread"], 2)

    def test_product_api_exposes_stock_state_to_customers(self):
        self.product.quantity = 0
        self.product.save(update_fields=["quantity"])
        response = self.client.get(f"/api/products/?merchant={self.merchant.id}")
        self.assertEqual(response.status_code, 200)
        rows = response.data if isinstance(response.data, list) else response.data["results"]
        row = next(item for item in rows if item["id"] == self.product.id)
        self.assertEqual(row["quantity"], 0)
        self.assertEqual(row["stock_status"], "out")
        blocked = self.client.post("/api/orders/", self.payload(1), format="json")
        self.assertEqual(blocked.status_code, 400)

    def test_merchant_stock_delta_is_atomic_and_never_negative(self):
        merchant_client = self.client_for(self.merchant_user)
        url = f"/api/products/{self.product.id}/stock/"
        bumped = merchant_client.post(url, {"delta": 1}, format="json")
        self.assertEqual(bumped.status_code, 200)
        self.assertEqual(bumped.data["quantity"], 11)
        drained = merchant_client.post(url, {"delta": -50}, format="json")
        self.assertEqual(drained.status_code, 200)
        self.assertEqual(drained.data["quantity"], 0)
        self.assertEqual(drained.data["stock_status"], "out")
        self.assertTrue(
            Notification.objects.filter(user=self.merchant_user, event="stock.out").exists())
        self.assertEqual(merchant_client.post(url, {"delta": 0}, format="json").status_code, 400)

    def test_stock_delta_rejects_other_merchants_and_initializes_untracked(self):
        other_client = self.client_for(self.other_merchant_user)
        url = f"/api/products/{self.product.id}/stock/"
        self.assertEqual(other_client.post(url, {"delta": 1}, format="json").status_code, 404)
        legacy = Product.objects.create(
            merchant=self.merchant, name="Legacy", price=Decimal("3.00"), available=True)
        self.assertIsNone(legacy.quantity)
        merchant_client = self.client_for(self.merchant_user)
        response = merchant_client.post(f"/api/products/{legacy.id}/stock/", {"delta": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["quantity"], 1)
        legacy.refresh_from_db()
        self.assertEqual(legacy.quantity, 1)


class LastUnitGuardTests(TransactionTestCase):
    """The last unit can only be reserved once (the UPDATE is conditional)."""

    def setUp(self):
        self.merchant_user = User.objects.create_user(
            username="race-merchant", password="test-password-123", role="merchant")
        self.merchant = MerchantProfile.objects.create(
            user=self.merchant_user, shop_name="Race Market", address="Race Street",
            latitude=Decimal("31.949934"), longitude=Decimal("35.213710"), is_open=True)
        self.product = Product.objects.create(
            merchant=self.merchant, name="Last Unit", price=Decimal("4.00"),
            available=True, quantity=1)
        self.customer = User.objects.create_user(
            username="race-customer", password="test-password-123", role="customer")

    def test_reservation_guard_refuses_the_second_take(self):
        from .views import StockUnavailable, reserve_stock
        row = [{"product_id": self.product.id, "quantity": 1, "name": "Last Unit", "stock_tracked": True}]
        reserve_stock(row)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)
        with self.assertRaises(StockUnavailable):
            reserve_stock(row)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)

    def test_two_sequential_orders_cannot_both_take_the_last_unit(self):
        client = APIClient()
        client.force_authenticate(self.customer)
        payload = {
            "merchant": self.merchant.id,
            "items": [{"product_id": self.product.id, "quantity": 1}],
            "dropoff_address": "Home", "dropoff_latitude": 31.949934, "dropoff_longitude": 35.213710,
            "delivery_fee": "10.00", "order_type": "store",
        }
        first = client.post("/api/orders/", payload, format="json")
        second = client.post("/api/orders/", payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 400, second.data)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)


class StockLifecycleMatrixTests(TestCase):
    """The required stock matrix: deduction, refusal, restore-once, idempotency."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username="matrix-customer", password="test-password-123", role="customer")
        self.other_customer = User.objects.create_user(
            username="matrix-customer-2", password="test-password-123", role="customer")
        self.merchant_user = User.objects.create_user(
            username="matrix-merchant", password="test-password-123", role="merchant")
        self.merchant = MerchantProfile.objects.create(
            user=self.merchant_user, shop_name="Matrix Market", address="Matrix Street",
            latitude=Decimal("31.949934"), longitude=Decimal("35.213710"), is_open=True)
        self.captain_user = User.objects.create_user(
            username="matrix-captain", password="test-password-123", role="captain")
        self.admin = User.objects.create_user(
            username="matrix-admin", password="test-password-123", role="admin")
        self.product = Product.objects.create(
            merchant=self.merchant, name="Bread", price=Decimal("4.00"),
            available=True, quantity=4, low_stock_threshold=2)
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def payload(self, quantity, **overrides):
        data = {
            "merchant": self.merchant.id,
            "items": [{"product_id": self.product.id, "quantity": quantity}],
            "dropoff_address": "Home",
            "dropoff_latitude": 31.949934,
            "dropoff_longitude": 35.213710,
            "delivery_fee": "10.00",
            "order_type": "store",
        }
        data.update(overrides)
        return data

    def order(self, quantity, client=None, **headers):
        return (client or self.client).post(
            "/api/orders/", self.payload(quantity), format="json", **headers)

    def stock(self):
        self.product.refresh_from_db()
        return self.product.quantity

    @staticmethod
    def rows(response):
        return response.data if isinstance(response.data, list) else response.data["results"]

    # 1) stock 4 + order 1 -> 3, and both portals see the new count.
    def test_order_one_of_four_leaves_three(self):
        response = self.order(1)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock(), 3)
        customer_row = next(
            row for row in self.rows(self.client.get(f"/api/products/?merchant={self.merchant.id}"))
            if row["id"] == self.product.id)
        self.assertEqual(customer_row["quantity"], 3)
        merchant_row = next(
            row for row in self.rows(self.client_for(self.merchant_user).get("/api/products/"))
            if row["id"] == self.product.id)
        self.assertEqual(merchant_row["quantity"], 3)
        self.assertEqual(merchant_row["stock_status"], "in")

    # 2) stock 4 + order 2 -> 2.
    def test_order_two_of_four_leaves_two(self):
        response = self.order(2)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock(), 2)

    # 3) stock 4 + order 4 -> 0, then nothing else can be ordered.
    def test_order_four_of_four_leaves_zero_and_blocks_next(self):
        response = self.order(4)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stock(), 0)
        blocked = self.order(1, client=self.client_for(self.other_customer))
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(str(blocked.data["stock"][0]["available"]), "0")
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.stock(), 0)

    # 4) stock 4 + order 5 -> rejected, nothing changes.
    def test_order_five_of_four_is_rejected_without_deduction(self):
        response = self.order(5)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Bread", response.data["items"])
        self.assertIn("4", response.data["items"])
        self.assertEqual(str(response.data["stock"][0]["requested"]), "5")
        self.assertEqual(str(response.data["stock"][0]["available"]), "4")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(), 4)

    # 5) zero stock cannot be ordered at all.
    def test_zero_stock_is_rejected(self):
        self.product.quantity = 0
        self.product.save(update_fields=["quantity"])
        response = self.order(1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(), 0)

    # Stock consumed by one customer is gone for every other customer.
    def test_second_customer_cannot_take_consumed_stock(self):
        self.product.quantity = 2
        self.product.save(update_fields=["quantity"])
        first = self.order(2)
        self.assertEqual(first.status_code, 201, first.data)
        second = self.order(1, client=self.client_for(self.other_customer))
        self.assertEqual(second.status_code, 400)
        self.assertEqual(self.stock(), 0)

    # 7 + 8) cancellation restores once; repeats and later updates never restore again.
    def test_cancel_restores_once_and_repeats_never_restore(self):
        from .views import restore_order_stock
        order = Order.objects.get(pk=self.order(2).data["id"])
        self.assertEqual(self.stock(), 2)
        cancelled = self.client.post(
            f"/api/orders/{order.id}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.assertEqual(self.stock(), 4)
        repeated = self.client.post(
            f"/api/orders/{order.id}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(self.stock(), 4)
        admin_again = self.client_for(self.admin).post(
            f"/api/orders/{order.id}/status/", {"status": "cancelled"}, format="json")
        self.assertEqual(admin_again.status_code, 400)
        self.assertEqual(self.stock(), 4)
        order.refresh_from_db()
        self.assertIsNotNone(order.stock_restored_at)
        self.assertFalse(restore_order_stock(order))
        self.assertEqual(self.stock(), 4)

    # 9) resending the same order with the same key deducts once.
    def test_resend_same_order_deducts_once(self):
        key = str(uuid.uuid4())
        first = self.order(2, HTTP_IDEMPOTENCY_KEY=key)
        second = self.order(2, HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.stock(), 2)

    # 10) every non-customer role is refused by the only order-creation API.
    def test_non_customer_roles_cannot_create_orders(self):
        for user in (self.merchant_user, self.captain_user, self.admin):
            response = self.order(1, client=self.client_for(user))
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("Only customers", str(response.data))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(), 4)

    # An unset count is not a licence to sell: both the serializer flag and the
    # reservation refuse it, and the structured payload explains why.
    def test_untracked_product_is_refused_by_order_creation(self):
        self.product.quantity = None
        self.product.save(update_fields=["quantity"])
        response = self.order(1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["stock"][0]["reason"], "untracked")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.stock(), None)


class ConcurrentLastUnitOrderTests(TransactionTestCase):
    """Two simultaneous orders for the last unit: exactly one may win."""

    def setUp(self):
        self.merchant_user = User.objects.create_user(
            username="conc-merchant", password="test-password-123", role="merchant")
        self.merchant = MerchantProfile.objects.create(
            user=self.merchant_user, shop_name="Conc Market", address="Conc Street",
            latitude=Decimal("31.949934"), longitude=Decimal("35.213710"), is_open=True)
        self.product = Product.objects.create(
            merchant=self.merchant, name="Single", price=Decimal("4.00"),
            available=True, quantity=1)
        self.customers = [
            User.objects.create_user(
                username=f"conc-customer-{index}", password="test-password-123", role="customer")
            for index in (1, 2)
        ]

    def test_only_one_of_two_simultaneous_orders_wins(self):
        payload = {
            "merchant": self.merchant.id,
            "items": [{"product_id": self.product.id, "quantity": 1}],
            "dropoff_address": "Home", "dropoff_latitude": 31.949934,
            "dropoff_longitude": 35.213710,
            "delivery_fee": "10.00", "order_type": "store",
        }
        barrier = threading.Barrier(2)

        def place(user):
            try:
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait()
                # SQLite's shared in-memory cache raises on write contention
                # instead of waiting; the loser retries and then sees zero
                # units, which is the same outcome PostgreSQL reaches by
                # re-evaluating the conditional UPDATE after the row lock.
                for attempt in range(6):
                    try:
                        return client.post("/api/orders/", payload, format="json").status_code
                    except OperationalError:
                        if attempt == 5:
                            raise
                        time.sleep(0.2 * (attempt + 1))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(place, self.customers))
        self.assertEqual(statuses, [201, 400])
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)


class ProductAvailabilityDefaultTests(TestCase):
    """Creating from the merchant form must not hide the product by default."""

    def setUp(self):
        self.merchant_user = User.objects.create_user(
            username="avail-merchant", password="test-password-123", role="merchant")
        self.merchant = MerchantProfile.objects.create(
            user=self.merchant_user, shop_name="Avail Market", address="Avail Street",
            latitude=Decimal("31.949934"), longitude=Decimal("35.213710"), is_open=True)
        self.client = APIClient()
        self.client.force_authenticate(self.merchant_user)

    def create(self, data, fmt):
        return self.client.post("/api/products/", data, format=fmt)

    def test_multipart_create_without_available_is_available(self):
        response = self.create({"name": "No Checkbox", "price": "5.00", "quantity": 3}, "multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["available"])
        self.assertTrue(Product.objects.get(pk=response.data["id"]).available)

    def test_multipart_create_with_explicit_false_stays_hidden(self):
        response = self.create({"name": "Hidden", "price": "5.00", "available": "false"}, "multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["available"])

    def test_json_create_without_available_is_available(self):
        response = self.create({"name": "Json Product", "price": "5.00"}, "json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["available"])

    def test_multipart_update_without_available_keeps_hidden_state(self):
        product = Product.objects.create(
            merchant=self.merchant, name="Stays Hidden", price=Decimal("5.00"), available=False)
        response = self.client.patch(
            f"/api/products/{product.id}/", {"name": "Stays Hidden Renamed"}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["available"])
        product.refresh_from_db()
        self.assertFalse(product.available)

    def test_explicit_toggle_is_honored_in_both_formats(self):
        product = Product.objects.create(
            merchant=self.merchant, name="Toggle", price=Decimal("5.00"), available=True)
        hidden = self.client.patch(
            f"/api/products/{product.id}/", {"available": False}, format="json")
        self.assertEqual(hidden.status_code, 200, hidden.data)
        self.assertFalse(hidden.data["available"])
        shown = self.client.patch(
            f"/api/products/{product.id}/", {"available": "true"}, format="multipart")
        self.assertEqual(shown.status_code, 200, shown.data)
        self.assertTrue(shown.data["available"])
