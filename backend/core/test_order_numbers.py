from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import MerchantProfile, Order, OrderNumberSequence, Product
from .serializers import OrderSerializer


class OrderNumberTests(TestCase):
    def setUp(self):
        self.customer = get_user_model().objects.create_user(
            username="number-customer", password="customer-password-123", role="customer"
        )

    def test_orders_receive_unique_stable_business_numbers_through_cancellation(self):
        first = Order.objects.create(customer=self.customer)
        first_number = first.order_number
        second = Order.objects.create(customer=self.customer)

        self.assertRegex(first_number, r"^WAS-\d{4}-\d{6}$")
        self.assertNotEqual(first_number, second.order_number)

        first.status = "cancelled"
        first.save(update_fields=["status"])
        first.refresh_from_db()
        third = Order.objects.create(customer=self.customer)

        self.assertEqual(first.order_number, first_number)
        self.assertNotIn(third.order_number, {first_number, second.order_number})

    def test_missing_counter_reinitializes_above_existing_numbers(self):
        first = Order.objects.create(customer=self.customer)
        OrderNumberSequence.objects.filter(pk=1).delete()

        second = Order.objects.create(customer=self.customer)

        self.assertNotEqual(first.order_number, second.order_number)

    def test_order_number_is_read_only_in_the_api_serializer(self):
        order = Order.objects.create(customer=self.customer)
        serializer = OrderSerializer(
            order, data={"order_number": "WAS-2099-999999"}, partial=True
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.order_number, order.order_number)

    def test_api_assigns_a_number_to_orders_created_during_rolling_deployment(self):
        order = Order.objects.create(customer=self.customer)
        Order.objects.filter(pk=order.pk).update(order_number=None)
        order.refresh_from_db()

        data = OrderSerializer(order).data

        self.assertRegex(data["order_number"], r"^WAS-\d{4}-\d{6}$")
        self.assertEqual(Order.objects.get(pk=order.pk).order_number, data["order_number"])

    def test_search_uses_business_number_and_is_limited_to_the_customer_orders(self):
        order = Order.objects.create(customer=self.customer)
        client = APIClient()
        client.force_authenticate(self.customer)

        response = client.get("/api/orders/", {"search": order.order_number})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["order_number"] for row in response.data], [order.order_number])

        other_customer = get_user_model().objects.create_user(
            username="another-customer", password="customer-password-123", role="customer"
        )
        client.force_authenticate(other_customer)
        denied = client.get("/api/orders/", {"search": order.order_number})
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(denied.data, [])

    def test_store_order_creation_and_idempotent_retry_return_the_same_business_number(self):
        merchant_user = get_user_model().objects.create_user(
            username="number-merchant", password="merchant-password-123", role="merchant"
        )
        merchant = MerchantProfile.objects.create(
            user=merchant_user,
            shop_name="Number Market",
            latitude=Decimal("31.950000"),
            longitude=Decimal("35.210000"),
        )
        product = Product.objects.create(
            merchant=merchant, name="Test item", price=Decimal("3.50"), quantity=10
        )
        client = APIClient()
        client.force_authenticate(self.customer)
        payload = {
            "merchant": merchant.pk,
            "items": [{"product_id": product.pk, "quantity": 1}],
            "dropoff_address": "Test destination",
            "dropoff_latitude": "31.960000",
            "dropoff_longitude": "35.220000",
            "delivery_fee": "5.00",
        }

        created = client.post(
            "/api/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY="number-test-key"
        )
        repeated = client.post(
            "/api/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY="number-test-key"
        )

        self.assertEqual(created.status_code, 201, created.data)
        self.assertRegex(created.data["order_number"], r"^WAS-\d{4}-\d{6}$")
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data["id"], created.data["id"])
        self.assertEqual(repeated.data["order_number"], created.data["order_number"])
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 1)

    def test_admin_can_search_by_internal_id_without_changing_display_number(self):
        order = Order.objects.create(id=7654321, customer=self.customer)
        admin = get_user_model().objects.create_user(
            username="number-admin", password="admin-password-123", role="admin"
        )
        client = APIClient()
        client.force_authenticate(admin)

        response = client.get("/api/orders/", {"search": str(order.pk)})

        self.assertEqual(response.status_code, 200)
        matching = [row for row in response.data if row["id"] == order.pk]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["order_number"], order.order_number)


class OrderNumberMigrationTests(TransactionTestCase):
    migrate_from = ("core", "0016_adminaccountaudit")
    migrate_to = ("core", "0017_order_business_number")

    def test_existing_orders_are_backfilled_and_sequence_continues(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        HistoricalUser = old_apps.get_model("core", "User")
        HistoricalOrder = old_apps.get_model("core", "Order")

        customer = HistoricalUser.objects.create(
            username="legacy-number-customer", password="!", role="customer"
        )
        older = HistoricalOrder.objects.create(
            customer_id=customer.pk, status="cancelled", total=Decimal("4.25")
        )
        newer = HistoricalOrder.objects.create(
            customer_id=customer.pk, status="completed", total=Decimal("9.50")
        )
        HistoricalOrder.objects.filter(pk=older.pk).update(
            created_at=timezone.make_aware(datetime(2024, 2, 1, 12))
        )
        HistoricalOrder.objects.filter(pk=newer.pk).update(
            created_at=timezone.make_aware(datetime(2025, 3, 1, 12))
        )

        try:
            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to])
            new_apps = executor.loader.project_state([self.migrate_to]).apps
            OrderAfterMigration = new_apps.get_model("core", "Order")
            SequenceAfterMigration = new_apps.get_model("core", "OrderNumberSequence")

            older_after = OrderAfterMigration.objects.get(pk=older.pk)
            newer_after = OrderAfterMigration.objects.get(pk=newer.pk)
            self.assertTrue(older_after.order_number.startswith("WAS-2024-"))
            self.assertTrue(newer_after.order_number.startswith("WAS-2025-"))
            self.assertNotEqual(older_after.order_number, newer_after.order_number)
            self.assertEqual(older_after.status, "cancelled")
            self.assertEqual(older_after.total, Decimal("4.25"))
            self.assertEqual(SequenceAfterMigration.objects.get(pk=1).last_number, 2)
        finally:
            MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


@skipUnless(connection.vendor in ("postgresql", "sqlite"), "concurrency test requires a transactional database")
class ConcurrentOrderNumberTests(TransactionTestCase):
    reset_sequences = True

    def test_parallel_allocations_are_unique(self):
        def allocate_number(_):
            close_old_connections()
            try:
                return Order._next_order_number()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=8) as executor:
            numbers = list(executor.map(allocate_number, range(16)))

        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual(OrderNumberSequence.objects.get(pk=1).last_number, len(numbers))
