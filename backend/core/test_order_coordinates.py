"""Coordinate precision and geographic bounds for order creation."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import MerchantProfile, Order, Product

User = get_user_model()

RAW_LAT = 31.94993417521601
RAW_LNG = 35.21370999999999


class OrderCoordinateTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="coord-customer", password="test-password-123", role="customer"
        )
        self.merchant_user = User.objects.create_user(
            username="coord-merchant", password="test-password-123", role="merchant"
        )
        self.merchant = MerchantProfile.objects.create(
            user=self.merchant_user,
            shop_name="Coord Market",
            address="Market Street",
            latitude=Decimal("31.949934"),
            longitude=Decimal("35.213710"),
            is_open=True,
        )
        self.product = Product.objects.create(
            merchant=self.merchant, name="Water", price=Decimal("3.50"), available=True,
            quantity=50
        )
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def store_payload(self, **overrides):
        payload = {
            "merchant": self.merchant.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "dropoff_address": "Home",
            "dropoff_latitude": RAW_LAT,
            "dropoff_longitude": RAW_LNG,
            "delivery_fee": "10.00",
            "order_type": "store",
        }
        payload.update(overrides)
        return payload

    def ride_payload(self, **overrides):
        payload = {
            "pickup_address": "Pickup",
            "dropoff_address": "Destination",
            "pickup_latitude": RAW_LAT,
            "pickup_longitude": RAW_LNG,
            "dropoff_latitude": 31.96000012345678,
            "dropoff_longitude": 35.22000098765432,
            "delivery_fee": "15.00",
        }
        payload.update(overrides)
        return payload

    def test_store_order_rounds_raw_float_coordinates_to_six_decimals(self):
        response = self.client.post("/api/orders/", self.store_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.dropoff_latitude, Decimal("31.949934"))
        self.assertEqual(order.dropoff_longitude, Decimal("35.213710"))
        self.assertEqual(order.pickup_latitude, self.merchant.latitude)
        self.assertEqual(order.pickup_longitude, self.merchant.longitude)

    def test_store_order_rounds_string_coordinates_to_six_decimals(self):
        response = self.client.post(
            "/api/orders/",
            self.store_payload(dropoff_latitude="31.94993417521601", dropoff_longitude="35.21370999999999"),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.dropoff_latitude, Decimal("31.949934"))
        self.assertEqual(order.dropoff_longitude, Decimal("35.213710"))

    def test_store_order_accepts_negative_coordinates(self):
        response = self.client.post(
            "/api/orders/",
            self.store_payload(dropoff_latitude=-33.868819758, dropoff_longitude=-70.6692655),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.dropoff_latitude, Decimal("-33.868820"))
        self.assertEqual(order.dropoff_longitude, Decimal("-70.669266"))

    def test_six_decimal_coordinates_are_preserved(self):
        response = self.client.post(
            "/api/orders/",
            self.store_payload(dropoff_latitude="31.123456", dropoff_longitude="-35.654321"),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.dropoff_latitude, Decimal("31.123456"))
        self.assertEqual(order.dropoff_longitude, Decimal("-35.654321"))

    def test_store_order_accepts_geographic_bounds(self):
        for latitude, longitude in ((90, 180), (-90, -180), (0, 0)):
            response = self.client.post(
                "/api/orders/",
                self.store_payload(
                    dropoff_address=f"{latitude},{longitude}",
                    dropoff_latitude=latitude,
                    dropoff_longitude=longitude,
                ),
                format="json",
            )
            self.assertEqual(response.status_code, 201, (latitude, longitude, response.data))

    def test_store_order_rejects_coordinates_outside_bounds(self):
        cases = (
            {"dropoff_latitude": 90.000001},
            {"dropoff_latitude": -90.5},
            {"dropoff_longitude": 180.000001},
            {"dropoff_longitude": -181},
        )
        for overrides in cases:
            response = self.client.post("/api/orders/", self.store_payload(**overrides), format="json")
            field = next(iter(overrides))
            self.assertEqual(response.status_code, 400, (overrides, response.data))
            self.assertIn(field, response.data)
        self.assertFalse(Order.objects.exists())

    def test_store_order_rejects_non_finite_coordinates(self):
        for value in ("nan", "inf", "-inf"):
            response = self.client.post(
                "/api/orders/", self.store_payload(dropoff_latitude=value), format="json"
            )
            self.assertEqual(response.status_code, 400, (value, response.data))
        self.assertFalse(Order.objects.exists())

    def test_store_order_requires_both_dropoff_coordinates(self):
        response = self.client.post(
            "/api/orders/", self.store_payload(dropoff_longitude=""), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("location", response.data)
        self.assertFalse(Order.objects.exists())

    def test_ride_order_rounds_coordinates_and_creates(self):
        response = self.client.post("/api/orders/ride/", self.ride_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.order_type, "ride")
        self.assertEqual(order.pickup_latitude, Decimal("31.949934"))
        self.assertEqual(order.pickup_longitude, Decimal("35.213710"))
        self.assertEqual(order.dropoff_latitude, Decimal("31.960000"))
        self.assertEqual(order.dropoff_longitude, Decimal("35.220001"))
        self.assertGreater(order.distance_km, 0)

    def test_ride_order_accepts_negative_coordinates(self):
        response = self.client.post(
            "/api/orders/ride/",
            self.ride_payload(
                pickup_latitude=-33.868819758,
                pickup_longitude=-70.6692655,
                dropoff_latitude=-34.0,
                dropoff_longitude=-70.5,
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["id"])
        self.assertEqual(order.pickup_latitude, Decimal("-33.868820"))
        self.assertEqual(order.pickup_longitude, Decimal("-70.669266"))
        self.assertEqual(order.dropoff_latitude, Decimal("-34.000000"))
        self.assertEqual(order.dropoff_longitude, Decimal("-70.500000"))

    def test_ride_order_accepts_geographic_bounds(self):
        response = self.client.post(
            "/api/orders/ride/",
            self.ride_payload(
                pickup_latitude=90,
                pickup_longitude=180,
                dropoff_latitude=-90,
                dropoff_longitude=-180,
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_ride_order_rejects_out_of_range_coordinates(self):
        for overrides in (
            {"pickup_latitude": 91},
            {"dropoff_longitude": -181},
            {"pickup_latitude": "nan"},
            {"dropoff_latitude": "inf"},
        ):
            response = self.client.post("/api/orders/ride/", self.ride_payload(**overrides), format="json")
            self.assertEqual(response.status_code, 400, (overrides, response.data))
            self.assertIn("location", response.data)
        self.assertFalse(Order.objects.exists())

    def test_merchant_profile_rounds_raw_float_coordinates(self):
        client = APIClient()
        client.force_authenticate(self.merchant_user)
        response = client.patch(
            "/api/merchant/profile/",
            {"latitude": RAW_LAT, "longitude": RAW_LNG},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.latitude, Decimal("31.949934"))
        self.assertEqual(self.merchant.longitude, Decimal("35.213710"))

    def test_merchant_profile_rejects_out_of_range_coordinates(self):
        client = APIClient()
        client.force_authenticate(self.merchant_user)
        response = client.patch(
            "/api/merchant/profile/", {"latitude": 95, "longitude": 35}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("latitude", response.data)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.latitude, Decimal("31.949934"))
