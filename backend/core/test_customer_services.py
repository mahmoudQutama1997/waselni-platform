from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import CaptainProfile, CaptainServiceEligibility, MerchantProfile, Order, Product


class CustomerServiceRequestTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(username="service-customer", password="password-123")
        self.admin = User.objects.create_user(username="service-admin", password="password-123", role="admin")
        self.client = APIClient()
        self.client.force_authenticate(self.customer)
        self.locations = {
            "pickup_address": "Nablus centre",
            "dropoff_address": "Rafidia",
            "pickup_latitude": 32.2211,
            "pickup_longitude": 35.2544,
            "dropoff_latitude": 32.2240,
            "dropoff_longitude": 35.2460,
        }

    def test_customer_service_directory_contains_the_six_operational_services(self):
        response = self.client.get("/api/services/?lang=ar")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row["code"] for row in response.data},
            {"food", "grocery", "pharmacy", "parcel", "ride", "logistics"},
        )

    def test_customer_can_create_a_priced_parcel_for_dispatch(self):
        response = self.client.post("/api/orders/service/parcel/", {
            **self.locations,
            "recipient_name": "Recipient",
            "recipient_phone": "0590000000",
            "weight_kg": "2",
            "package_type": "documents",
        }, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.order_type, "parcel")
        self.assertEqual(order.service_type, "parcel")
        self.assertEqual(order.status, "ready")
        self.assertGreater(order.total, Decimal("0"))
        self.assertEqual(order.service_details["recipient_name"], "Recipient")

    def test_logistics_request_waits_for_quote_acceptance_before_dispatch(self):
        request = self.client.post("/api/orders/service/logistics/", {
            **self.locations,
            "sender_name": "Sender",
            "sender_phone": "0590000001",
            "recipient_name": "Recipient",
            "recipient_phone": "0590000002",
            "piece_count": 3,
        }, format="json")
        self.assertEqual(request.status_code, 201, request.data)
        order_id = request.data["id"]
        self.assertEqual(request.data["status"], "new")
        self.assertEqual(request.data["service_details"]["quote_status"], "requested")

        self.client.force_authenticate(self.admin)
        offered = self.client.post(f"/api/orders/{order_id}/quote/", {"amount": "75.00"}, format="json")
        self.assertEqual(offered.status_code, 200, offered.data)
        self.assertEqual(offered.data["service_details"]["quote_status"], "offered")
        self.assertEqual(offered.data["status"], "new")

        self.client.force_authenticate(self.customer)
        accepted = self.client.post(f"/api/orders/{order_id}/quote/", {"accept": True}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data["status"], "ready")
        self.assertEqual(accepted.data["service_details"]["quote_status"], "accepted")
        self.assertEqual(accepted.data["total"], "75.00")

    def test_parcel_dispatch_only_lists_orders_for_eligible_captains(self):
        created = self.client.post("/api/orders/service/parcel/", {
            **self.locations,
            "recipient_name": "Recipient",
            "recipient_phone": "0590000000",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)

        User = get_user_model()
        eligible_user = User.objects.create_user(username="parcel-captain", password="password-123", role="captain")
        eligible_profile = CaptainProfile.objects.create(user=eligible_user, approved=True, online=True)
        CaptainServiceEligibility.objects.create(captain=eligible_profile, service="parcel", status="approved")
        unqualified_user = User.objects.create_user(username="food-captain", password="password-123", role="captain")
        CaptainProfile.objects.create(user=unqualified_user, approved=True, online=True)

        self.client.force_authenticate(unqualified_user)
        unavailable = self.client.get("/api/orders/available/")
        self.assertEqual(unavailable.status_code, 200)
        self.assertEqual(unavailable.data, [])
        denied = self.client.post(
            f"/api/orders/{created.data['id']}/assign/",
            {"accepted_delivery_fee": created.data["delivery_fee"]},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(eligible_user)
        available = self.client.get("/api/orders/available/")
        self.assertEqual([row["id"] for row in available.data], [created.data["id"]])

    def test_pharmacy_restricted_items_are_hidden_and_cannot_be_ordered(self):
        merchant_user = get_user_model().objects.create_user(
            username="pharmacy-owner", password="password-123", role="merchant"
        )
        pharmacy = MerchantProfile.objects.create(
            user=merchant_user, shop_name="Community Pharmacy", category="pharmacy",
            address="Nablus", latitude=Decimal("32.221100"), longitude=Decimal("35.254400"),
        )
        product = Product.objects.create(
            merchant=pharmacy, name="Prescription item", price=Decimal("12.00"),
            quantity=5, prescription_required=True,
        )

        listed = self.client.get(f"/api/products/?merchant={pharmacy.id}&service=pharmacy")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data, [])

        self.client.force_authenticate(self.admin)
        refused = self.client.patch(
            f"/api/admin/control/pharmacy-products/{product.id}/",
            {"status": "approved"},
            format="json",
        )
        self.assertEqual(refused.status_code, 400)
        otc = Product.objects.create(
            merchant=pharmacy, name="Non-prescription item", price=Decimal("3.00"), quantity=3,
        )
        approved = self.client.patch(
            f"/api/admin/control/pharmacy-products/{otc.id}/",
            {"status": "approved"},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        self.client.force_authenticate(merchant_user)
        changed = self.client.patch(
            f"/api/products/{otc.id}/",
            {"prescription_required": True},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.data["pharmacy_review_status"], "pending")
        self.client.force_authenticate(self.admin)
        reapproved = self.client.patch(
            f"/api/admin/control/pharmacy-products/{otc.id}/",
            {"status": "approved"},
            format="json",
        )
        self.assertEqual(reapproved.status_code, 400)
        self.client.force_authenticate(merchant_user)
        changed_back = self.client.patch(
            f"/api/products/{otc.id}/",
            {"prescription_required": False},
            format="json",
        )
        self.assertEqual(changed_back.status_code, 200, changed_back.data)
        self.client.force_authenticate(self.admin)
        reapproved = self.client.patch(
            f"/api/admin/control/pharmacy-products/{otc.id}/",
            {"status": "approved"},
            format="json",
        )
        self.assertEqual(reapproved.status_code, 200, reapproved.data)
        self.client.force_authenticate(self.customer)
        listed = self.client.get(f"/api/products/?merchant={pharmacy.id}&service=pharmacy")
        self.assertEqual([row["id"] for row in listed.data], [otc.id])

        order = self.client.post("/api/orders/", {
            "merchant": pharmacy.id,
            "items": [{"product_id": product.id, "quantity": 1}],
            "dropoff_address": "Rafidia",
            "dropoff_latitude": 32.2240,
            "dropoff_longitude": 35.2460,
            "delivery_fee": "10.00",
            "order_type": "store",
        }, format="json")
        self.assertEqual(order.status_code, 400)
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())
