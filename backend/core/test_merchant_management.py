"""Merchant management, staff permissions, inventory ledger, promotions and proof."""
import tempfile
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import (
    CaptainProfile, CaptainServiceEligibility, InventoryMovement, MerchantBranch,
    MerchantProfile, Order, OrderProof, PriceChange, Product,
)

User = get_user_model()


def make_user(username, role, password="test-pass-123", **kw):
    return User.objects.create_user(username=username, password=password, role=role, **kw)


def make_merchant(username, category="restaurant"):
    owner = make_user(username, "merchant")
    return MerchantProfile.objects.create(
        user=owner, shop_name=f"{username} shop", category=category, address="Street 1",
        latitude=Decimal("31.949934"), longitude=Decimal("35.213710"), is_open=True,
    )


def make_captain(username, services=("food", "parcel"), online=True):
    user = make_user(username, "captain")
    profile = CaptainProfile.objects.create(
        user=user, approved=True, online=online, vehicle_type="motorcycle",
        vehicle_model="Honda", plate_number="PL-1",
    )
    for service in services:
        CaptainServiceEligibility.objects.create(captain=profile, service=service, status="approved")
    return user, profile


def png_file(name="proof.png"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (120, 60, 200)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class MerchantFlowTests(TestCase):
    def setUp(self):
        self.customer = make_user("flow-customer", "customer")
        self.merchant = make_merchant("flow-store")
        self.product = Product.objects.create(
            merchant=self.merchant, name="Bread", price=Decimal("8.00"),
            quantity=5, low_stock_threshold=2,
        )
        self.client = APIClient()

    def payload(self, quantity=2):
        return {
            "merchant": self.merchant.id,
            "items": [{"product_id": self.product.id, "quantity": quantity}],
            "dropoff_address": "Home", "dropoff_latitude": 31.9601,
            "dropoff_longitude": 35.2201, "delivery_fee": "10.00", "order_type": "store",
        }

    def create_order(self, quantity=2):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/orders/", self.payload(quantity), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Order.objects.get(pk=response.data["id"])

    def test_order_reserves_stock_once_and_records_ledger(self):
        order = self.create_order(2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 3)
        movement = InventoryMovement.objects.get(order=order, reason="order")
        self.assertEqual(movement.delta, -2)
        self.assertEqual(movement.quantity_before, 5)
        self.assertEqual(movement.quantity_after, 3)
        self.assertEqual(order.service_type, "food")
        self.assertEqual(movement.product_id, self.product.id)

    def test_insufficient_stock_rolls_back_order_and_ledger(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post("/api/orders/", self.payload(9), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(InventoryMovement.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 5)

    def test_merchant_accept_prepare_ready_and_captain_assign(self):
        order = self.create_order(1)
        self.client.force_authenticate(self.merchant.user)
        accepted = self.client.post(f"/api/orders/{order.id}/accept/", {"prep_minutes": 10}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data["status"], "accepted")
        preparing = self.client.post(f"/api/orders/{order.id}/status/", {"status": "preparing"}, format="json")
        self.assertEqual(preparing.status_code, 200, preparing.data)
        ready = self.client.post(f"/api/orders/{order.id}/status/", {"status": "ready"}, format="json")
        self.assertEqual(ready.status_code, 200, ready.data)
        captain_user, captain_profile = make_captain("flow-cap")
        self.client.force_authenticate(captain_user)
        assigned = self.client.post(
            f"/api/orders/{order.id}/assign/", {"accepted_delivery_fee": "10.00"}, format="json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)
        order.refresh_from_db()
        self.assertEqual(order.captain_id, captain_profile.id)
        self.assertEqual(order.status, "assigned")
        # Pickup requires the captain to report arrival at the store first.
        blocked = self.client.post(f"/api/orders/{order.id}/status/", {"status": "picked_up"}, format="json")
        self.assertEqual(blocked.status_code, 400)
        self.client.post(f"/api/orders/{order.id}/arrive/", {}, format="json")
        picked = self.client.post(f"/api/orders/{order.id}/status/", {"status": "picked_up"}, format="json")
        self.assertEqual(picked.status_code, 200, picked.data)

    def test_merchant_reject_requires_reason_and_restores_stock_once(self):
        order = self.create_order(2)
        self.client.force_authenticate(self.merchant.user)
        missing = self.client.post(f"/api/orders/{order.id}/reject/", {}, format="json")
        self.assertEqual(missing.status_code, 400)
        rejected = self.client.post(
            f"/api/orders/{order.id}/reject/", {"reason": "Out of ingredients"}, format="json",
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 5)
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.cancellation_reason, "Out of ingredients")
        self.assertIsNotNone(order.stock_restored_at)
        self.assertEqual(InventoryMovement.objects.filter(order=order, reason="cancel").count(), 1)
        # A cancelled order cannot be rejected twice or restore stock again.
        again = self.client.post(f"/api/orders/{order.id}/reject/", {"reason": "again"}, format="json")
        self.assertEqual(again.status_code, 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 5)

    def test_merchant_cannot_touch_another_store_order(self):
        order = self.create_order(1)
        other = make_merchant("other-store")
        self.client.force_authenticate(other.user)
        response = self.client.post(f"/api/orders/{order.id}/accept/", {"prep_minutes": 10}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_dashboard_uses_real_numbers(self):
        self.create_order(4)  # 5 -> 1, below threshold
        self.client.force_authenticate(self.merchant.user)
        response = self.client.get("/api/merchant/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["orders"]["new"], 1)
        self.assertEqual(response.data["products"]["low_stock"], 1)
        self.assertEqual(response.data["store"]["service_type"], "food")
        self.assertIn("reports", response.data["permissions"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class InventoryAndPromotionTests(TestCase):
    def setUp(self):
        self.merchant = make_merchant("inv-store")
        self.product = Product.objects.create(
            merchant=self.merchant, name="Oil", price=Decimal("20.00"),
            quantity=None, low_stock_threshold=2,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.merchant.user)

    def test_stock_adjustment_writes_movement_with_reason(self):
        response = self.client.post(
            f"/api/products/{self.product.id}/stock/",
            {"delta": 12, "reason": "restock", "note": "Weekly delivery"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 12)
        movement = InventoryMovement.objects.get(product=self.product)
        self.assertEqual(movement.delta, 12)
        self.assertEqual(movement.reason, "restock")
        self.assertEqual(movement.note, "Weekly delivery")
        listing = self.client.get("/api/merchant/inventory/movements/")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(len(listing.data), 1)

    def test_price_edit_is_audited(self):
        response = self.client.patch(
            f"/api/products/{self.product.id}/", {"price": "22.50"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        change = PriceChange.objects.get(product=self.product)
        self.assertEqual(str(change.old_price), "20.00")
        self.assertEqual(str(change.new_price), "22.50")
        self.assertEqual(change.changed_by_id, self.merchant.user_id)

    def test_discount_price_is_validated_and_used_server_side(self):
        invalid = self.client.patch(
            f"/api/products/{self.product.id}/", {"discount_price": "25.00"}, format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        valid = self.client.patch(
            f"/api/products/{self.product.id}/",
            {"discount_price": "15.00", "discount_starts_at": "2026-01-01T00:00:00Z",
             "discount_ends_at": "2030-01-01T00:00:00Z"},
            format="json",
        )
        self.assertEqual(valid.status_code, 200, valid.data)
        self.product.refresh_from_db()
        self.assertTrue(self.product.discount_active)
        self.assertEqual(self.product.effective_price, Decimal("15.00"))
        self.product.quantity = 10
        self.product.save(update_fields=["quantity"])
        customer = make_user("promo-customer", "customer")
        self.client.force_authenticate(customer)
        response = self.client.post("/api/orders/", {
            "merchant": self.merchant.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "dropoff_address": "Home", "dropoff_latitude": 31.96,
            "dropoff_longitude": 35.22, "delivery_fee": "5.00",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["subtotal"]), Decimal("30.00"))
        self.assertEqual(response.data["items"][0]["unit_price"], "15.00")


class MerchantStaffTests(TestCase):
    def setUp(self):
        self.merchant = make_merchant("staff-store")
        self.other_merchant = make_merchant("staff-other")
        self.product = Product.objects.create(
            merchant=self.merchant, name="Cheese", price=Decimal("12.00"), quantity=10,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.merchant.user)

    def create_staff(self, role, username):
        response = self.client.post("/api/merchant/staff/", {
            "username": username, "password": "staff-pass-123", "first_name": "Staff",
            "role": role,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return User.objects.get(username=username)

    def test_owner_creates_staff_and_inventory_role_can_adjust_stock_only(self):
        user = self.create_staff("inventory", "inv-staff")
        staff_client = APIClient()
        staff_client.force_authenticate(user)
        stock = staff_client.post(
            f"/api/products/{self.product.id}/stock/", {"delta": 3}, format="json",
        )
        self.assertEqual(stock.status_code, 200, stock.data)
        self.assertEqual(staff_client.get("/api/admin/users/").status_code, 403)
        self.assertEqual(staff_client.get("/api/merchant/staff/").status_code, 200)
        create_attempt = staff_client.post("/api/merchant/staff/", {
            "username": "x-staff", "password": "staff-pass-123", "first_name": "X", "role": "orders",
        }, format="json")
        self.assertEqual(create_attempt.status_code, 403)

    def test_preparation_role_cannot_change_prices_or_stock(self):
        user = self.create_staff("preparation", "prep-staff")
        staff_client = APIClient()
        staff_client.force_authenticate(user)
        price = staff_client.patch(
            f"/api/products/{self.product.id}/", {"price": "1.00"}, format="json",
        )
        self.assertEqual(price.status_code, 403)
        stock = staff_client.post(
            f"/api/products/{self.product.id}/stock/", {"delta": 1}, format="json",
        )
        self.assertEqual(stock.status_code, 403)
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), "12.00")
        self.assertEqual(self.product.quantity, 10)

    def test_staff_cannot_see_another_merchant_orders_or_branches(self):
        user = self.create_staff("manager", "mgr-staff")
        customer = make_user("staff-cust", "customer")
        Order.objects.create(
            customer=customer, merchant=self.other_merchant, order_type="store",
            service_type="food", status="new", total=Decimal("10.00"),
        )
        staff_client = APIClient()
        staff_client.force_authenticate(user)
        rows = staff_client.get("/api/orders/").data
        self.assertFalse(any(row["merchant"] == self.other_merchant.id for row in rows))
        foreign_branch = MerchantBranch.objects.create(
            merchant=self.other_merchant, name="Foreign",
        )
        self.assertEqual(
            staff_client.patch(f"/api/merchant/branches/{foreign_branch.id}/",
                               {"name": "Hacked"}, format="json").status_code, 404
        )
        reports = staff_client.get("/api/merchant/analytics/")
        self.assertEqual(reports.status_code, 200, reports.data)
        self.assertEqual(reports.data["inventory"][0]["id"], self.product.id)

    def test_deactivated_staff_loses_access(self):
        user = self.create_staff("orders", "gone-staff")
        self.client.delete(f"/api/merchant/staff/{user.merchant_staff_roles.first().id}/")
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        staff_client = APIClient()
        staff_client.force_authenticate(user)
        self.assertEqual(staff_client.get("/api/merchant/dashboard/").status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class OrderProofTests(TestCase):
    def setUp(self):
        self.customer = make_user("proof-customer", "customer")
        self.other_customer = make_user("proof-other", "customer")
        self.captain_user, self.captain = make_captain("proof-cap")
        self.order = Order.objects.create(
            customer=self.customer, captain=self.captain, order_type="parcel",
            service_type="parcel", status="delivering", delivery_otp="123456",
            delivery_fee=Decimal("10.00"), total=Decimal("10.00"),
            pickup_address="Office", dropoff_address="Home",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.captain_user)

    def proof(self, **data):
        payload = {"kind": "delivery", **data}
        return self.client.post(f"/api/orders/{self.order.id}/proof/", payload, format="multipart")

    def test_wrong_or_missing_otp_is_rejected(self):
        self.assertEqual(self.proof(recipient_name="Sami", photo=png_file()).status_code, 400)
        response = self.proof(otp="000000", recipient_name="Sami", photo=png_file())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "The delivery code is incorrect.")

    def test_photo_is_required_for_parcels(self):
        response = self.proof(otp="123456", recipient_name="Sami")
        self.assertEqual(response.status_code, 400)
        self.assertIn("photo", response.data)

    def test_valid_proof_unlocks_delivery_and_hides_otp(self):
        created = self.proof(otp="123456", recipient_name="Sami", notes="Left at door", photo=png_file())
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data["otp_verified"])
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivery_otp_verified_at)
        self.assertTrue(OrderProof.objects.filter(order=self.order, kind="delivery", photo__isnull=False).exists())
        delivered = self.client.post(f"/api/orders/{self.order.id}/status/", {"status": "awaiting_confirmation"}, format="json")
        self.assertEqual(delivered.status_code, 200, delivered.data)
        # The code is only exposed to the order's own customer.
        self.client.force_authenticate(self.customer)
        self.assertIsNone(self.client.get(f"/api/orders/{self.order.id}/").data["delivery_otp"])
        self.client.force_authenticate(self.captain_user)
        self.assertIsNone(self.client.get(f"/api/orders/{self.order.id}/").data["delivery_otp"])
        self.client.force_authenticate(self.other_customer)
        self.assertEqual(self.client.get(f"/api/orders/{self.order.id}/proofs/delivery/photo/").status_code, 403)

    def test_delivery_blocked_without_proof(self):
        response = self.client.post(f"/api/orders/{self.order.id}/status/", {"status": "awaiting_confirmation"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("proof", response.data["detail"].lower())

    def test_unassigned_captain_cannot_record_proof(self):
        other_user, _ = make_captain("proof-other-cap")
        self.client.force_authenticate(other_user)
        self.assertEqual(
            self.proof(otp="123456", recipient_name="X", photo=png_file()).status_code, 403
        )
