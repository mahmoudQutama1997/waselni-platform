"""Multi-service captain dispatch, schedules and capacity limits."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from django.test import TestCase

from .models import (
    CaptainProfile, CaptainServiceEligibility, CaptainWorkingWindow, MerchantProfile,
    Order, OrderActivity, Product, SERVICE_CODES,
)

User = get_user_model()


def make_customer(username="cust"):
    return User.objects.create_user(username=username, password="customer-pass-123", role="customer")


def make_merchant(username="store", category="restaurant", open_store=True):
    owner = User.objects.create_user(username=username, password="merchant-pass-123", role="merchant")
    return MerchantProfile.objects.create(
        user=owner, shop_name=f"{username} shop", category=category,
        address="Main street", latitude=Decimal("31.949934"), longitude=Decimal("35.213710"),
        is_open=open_store,
    )


def make_captain(username="cap", services=("food",), online=True, max_active=1, windows=None):
    user = User.objects.create_user(username=username, password="captain-pass-123", role="captain")
    profile = CaptainProfile.objects.create(
        user=user, approved=True, online=online, vehicle_type="motorcycle",
        vehicle_model="Honda", plate_number=f"PL-{username}",
    )
    for service in services:
        CaptainServiceEligibility.objects.create(captain=profile, service=service, status="approved")
    if max_active != 1:
        profile.max_active_tasks = max_active
        profile.save(update_fields=["max_active_tasks"])
    for weekday, start, end, is_break in windows or []:
        CaptainWorkingWindow.objects.create(
            captain=profile, weekday=weekday, start_time=start, end_time=end, is_break=is_break,
        )
    return user, profile


def make_product(merchant, name="Rice", price="10.00", quantity=10, **kw):
    return Product.objects.create(
        merchant=merchant, name=name, price=Decimal(price), quantity=quantity,
        available=True, low_stock_threshold=3, **kw,
    )


def make_store_order(merchant, customer, product, quantity=1, status="ready", service="food"):
    return Order.objects.create(
        customer=customer, merchant=merchant, order_type="store", service_type=service,
        status=status, items=[{
            "product_id": product.id, "name": product.name, "quantity": quantity,
            "unit_price": str(product.price), "line_total": str(product.price * quantity),
            "stock_tracked": True,
        }],
        subtotal=product.price * quantity, delivery_fee=Decimal("10.00"),
        total=product.price * quantity + Decimal("10.00"),
        pickup_address=merchant.address, dropoff_address="Home",
        pickup_latitude=merchant.latitude, pickup_longitude=merchant.longitude,
        dropoff_latitude=Decimal("31.960000"), dropoff_longitude=Decimal("35.220000"),
    )


class ServiceEligibilityApiTests(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.food_store = make_merchant("food-store", "restaurant")
        self.grocery_store = make_merchant("grocery-store", "supermarket")
        self.food_product = make_product(self.food_store, "Burger")
        self.grocery_product = make_product(self.grocery_store, "Milk")
        self.food_order = make_store_order(self.food_store, self.customer, self.food_product, service="food")
        self.grocery_order = make_store_order(self.grocery_store, self.customer, self.grocery_product, service="grocery")
        self.client = APIClient()

    def available_ids(self, user):
        self.client.force_authenticate(user)
        response = self.client.get("/api/orders/available/")
        self.assertEqual(response.status_code, 200, response.data)
        return [row["id"] for row in response.data]

    def accept(self, user, order):
        self.client.force_authenticate(user)
        return self.client.post(
            f"/api/orders/{order.id}/assign/",
            {"accepted_delivery_fee": str(order.delivery_fee)}, format="json",
        )

    def test_food_only_captain_sees_and_accepts_food_only(self):
        user, _ = make_captain("food-only", services=("food",))
        self.assertEqual(self.available_ids(user), [self.food_order.id])
        self.assertEqual(self.accept(user, self.food_order).status_code, 200)
        response = self.accept(user, self.grocery_order)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["reason"], "service_not_eligible")

    def test_captain_with_two_services_receives_both(self):
        user, _ = make_captain("multi", services=("food", "grocery"))
        self.assertCountEqual(
            self.available_ids(user), [self.food_order.id, self.grocery_order.id],
        )
        self.assertEqual(self.accept(user, self.grocery_order).status_code, 200)

    def test_admin_approval_enables_service_and_is_independent(self):
        user, profile = make_captain("cap-admin", services=("food",))
        admin = User.objects.create_user(username="admin", password="admin-pass-123", role="admin")
        self.client.force_authenticate(admin)
        denied = self.client.post(
            f"/api/admin/captains/{profile.id}/services/",
            {"service": "grocery", "status": "approved"}, format="json",
        )
        self.assertEqual(denied.status_code, 200, denied.data)
        row = CaptainServiceEligibility.objects.get(captain=profile, service="grocery")
        self.assertEqual(row.status, "approved")
        self.assertIsNotNone(row.approved_at)
        # Approving grocery did not change food, which stays approved.
        self.assertEqual(
            CaptainServiceEligibility.objects.get(captain=profile, service="food").status, "approved"
        )
        self.assertIn(self.grocery_order.id, self.available_ids(user))
        self.client.force_authenticate(user)
        self.assertEqual(self.client.post(
            f"/api/admin/captains/{profile.id}/services/",
            {"service": "parcel", "status": "approved"}, format="json",
        ).status_code, 403)

    def test_suspending_one_service_keeps_the_other(self):
        user, profile = make_captain("cap-suspend", services=("food", "grocery"))
        CaptainServiceEligibility.objects.filter(captain=profile, service="grocery").update(status="suspended")
        self.assertEqual(self.available_ids(user), [self.food_order.id])
        response = self.accept(user, self.grocery_order)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["reason"], "service_suspended")

    def test_captain_service_preference_cannot_approve_itself(self):
        user, profile = make_captain("cap-pref", services=("food",))
        CaptainServiceEligibility.objects.create(captain=profile, service="grocery", status="pending")
        self.client.force_authenticate(user)
        response = self.client.post(
            "/api/captains/me/services/", {"services": [{"service": "grocery", "accepting": True}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            CaptainServiceEligibility.objects.get(captain=profile, service="grocery").status, "pending"
        )
        ok = self.client.post(
            "/api/captains/me/services/", {"services": [{"service": "food", "accepting": False}]},
            format="json",
        )
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(self.available_ids(user), [])


class ScheduleTests(TestCase):
    def setUp(self):
        self.customer = make_customer("sched-cust")
        self.merchant = make_merchant("sched-store")
        self.product = make_product(self.merchant)
        self.order = make_store_order(self.merchant, self.customer, self.product)
        self.client = APIClient()

    def available(self, user):
        self.client.force_authenticate(user)
        return [row["id"] for row in self.client.get("/api/orders/available/").data]

    def test_no_schedule_means_always_available(self):
        user, _ = make_captain("no-window")
        self.assertEqual(self.available(user), [self.order.id])

    def test_outside_window_blocks_new_tasks(self):
        today = timezone.localtime().weekday()
        user, _ = make_captain("closed-window", windows=[(today, "00:01", "00:02", False)])
        self.assertEqual(self.available(user), [])
        self.client.force_authenticate(user)
        response = self.client.post(
            f"/api/orders/{self.order.id}/assign/",
            {"accepted_delivery_fee": str(self.order.delivery_fee)}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["reason"], "outside_working_hours")

    def test_break_window_blocks_even_inside_working_hours(self):
        today = timezone.localtime().weekday()
        user, _ = make_captain("break-window", windows=[
            (today, "00:00", "23:59", False),
            (today, "00:00", "23:59", True),
        ])
        self.assertEqual(self.available(user), [])

    def test_open_window_allows_dispatch(self):
        today = timezone.localtime().weekday()
        user, _ = make_captain("open-window", windows=[(today, "00:00", "23:59", False)])
        self.assertEqual(self.available(user), [self.order.id])

    def test_schedule_endpoint_replaces_windows(self):
        user, profile = make_captain("sched-api")
        self.client.force_authenticate(user)
        put = self.client.put("/api/captains/me/schedule/", {"windows": [
            {"weekday": 0, "start_time": "08:00", "end_time": "12:00", "is_break": False},
            {"weekday": 0, "start_time": "12:00", "end_time": "13:00", "is_break": True},
        ]}, format="json")
        self.assertEqual(put.status_code, 200, put.data)
        self.assertEqual(len(put.data["windows"]), 2)
        self.assertEqual(profile.working_windows.count(), 2)
        invalid = self.client.put("/api/captains/me/schedule/", {"windows": [
            {"weekday": 1, "start_time": "12:00", "end_time": "08:00", "is_break": False},
        ]}, format="json")
        self.assertEqual(invalid.status_code, 400)


class CapacityTests(TestCase):
    def setUp(self):
        self.customer = make_customer("cap-cust")
        self.merchant = make_merchant("cap-store")
        self.product = make_product(self.merchant, quantity=20)
        self.orders = [make_store_order(self.merchant, self.customer, self.product) for _ in range(2)]
        self.client = APIClient()

    def accept(self, user, order):
        self.client.force_authenticate(user)
        return self.client.post(
            f"/api/orders/{order.id}/assign/",
            {"accepted_delivery_fee": str(order.delivery_fee)}, format="json",
        )

    def test_default_single_active_task(self):
        user, _ = make_captain("single")
        self.assertEqual(self.accept(user, self.orders[0]).status_code, 200)
        second = self.accept(user, self.orders[1])
        self.assertEqual(second.status_code, 403)
        self.assertEqual(second.data["reason"], "max_active_tasks")

    def test_configurable_capacity(self):
        user, _ = make_captain("double", max_active=2)
        self.assertEqual(self.accept(user, self.orders[0]).status_code, 200)
        self.assertEqual(self.accept(user, self.orders[1]).status_code, 200)
        other = make_store_order(self.merchant, self.customer, self.product)
        self.assertEqual(self.accept(user, other).status_code, 403)

    def test_two_captains_only_one_wins(self):
        first, _ = make_captain("race-1")
        second, _ = make_captain("race-2")
        self.assertEqual(self.accept(first, self.orders[0]).status_code, 200)
        response = self.accept(second, self.orders[0])
        self.assertEqual(response.status_code, 409)
        self.orders[0].refresh_from_db()
        self.assertEqual(self.orders[0].captain.user.username, "race-1")
        self.assertEqual(
            OrderActivity.objects.filter(order=self.orders[0], event="assigned").count(), 1
        )
