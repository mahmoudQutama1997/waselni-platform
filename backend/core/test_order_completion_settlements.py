from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    CashSettlement,
    CashSettlementAllocation,
    CashSettlementReceipt,
    CaptainProfile,
    MerchantProfile,
    Order,
    SupportTicket,
)
from .services.order_completion import complete_expired_order_confirmations


class OrderCompletionAndCashLedgerTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.customer = user_model.objects.create_user(username="lifecycle-customer", password="password-123")
        self.merchant_user = user_model.objects.create_user(
            username="lifecycle-merchant", password="password-123", role="merchant"
        )
        self.captain_user = user_model.objects.create_user(
            username="lifecycle-captain", password="password-123", role="captain"
        )
        self.admin = user_model.objects.create_user(
            username="lifecycle-admin", password="password-123", role="admin"
        )
        self.merchant = MerchantProfile.objects.create(user=self.merchant_user, shop_name="Lifecycle Store")
        self.captain = CaptainProfile.objects.create(user=self.captain_user, approved=True)
        self.client = APIClient()

    def make_order(self, *, status="delivering", order_type="store", payment_method="cash", subtotal="40.00"):
        return Order.objects.create(
            customer=self.customer,
            merchant=self.merchant if order_type == "store" else None,
            captain=self.captain,
            order_type=order_type,
            status=status,
            payment_method=payment_method,
            subtotal=Decimal(subtotal),
            delivery_fee=Decimal("10.00"),
            total=Decimal(subtotal) + Decimal("10.00"),
        )

    def make_settlement(self, order):
        return CashSettlement.objects.create(
            order=order,
            merchant=self.merchant,
            captain=self.captain,
            amount=order.subtotal,
            reference=f"ORDER-{order.id}",
        )

    def test_captain_delivery_then_customer_confirmation_completes_once(self):
        order = self.make_order()
        self.client.force_authenticate(self.captain_user)
        delivered = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "awaiting_confirmation"},
            format="json",
        )
        self.assertEqual(delivered.status_code, 200, delivered.data)
        order.refresh_from_db()
        self.assertEqual(order.status, "awaiting_confirmation")
        self.assertIsNotNone(order.captain_delivered_at)
        self.assertFalse(CashSettlement.objects.filter(order=order).exists())

        self.client.force_authenticate(self.customer)
        confirmed = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        order.refresh_from_db()
        self.assertEqual(order.status, "completed")
        self.assertEqual(order.completed_by_id, self.customer.id)
        self.assertEqual(order.completed_by_name, self.customer.get_username())
        self.assertEqual(order.completion_method, "customer")
        self.assertIsNotNone(order.completed_at)
        self.assertTrue(CashSettlement.objects.filter(order=order, amount=Decimal("40.00")).exists())

        duplicate = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(CashSettlement.objects.filter(order=order).count(), 1)

    def test_captain_cannot_skip_customer_confirmation(self):
        order = self.make_order()
        self.client.force_authenticate(self.captain_user)
        response = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "delivering")

    def test_merchant_accepts_then_starts_preparation_before_ready(self):
        order = self.make_order(status="new")
        self.client.force_authenticate(self.merchant_user)
        accepted = self.client.post(
            f"/api/orders/{order.id}/accept/",
            {"prep_minutes": 15},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data["status"], "accepted")
        skipped = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "ready"},
            format="json",
        )
        self.assertEqual(skipped.status_code, 400)
        preparing = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "preparing"},
            format="json",
        )
        self.assertEqual(preparing.status_code, 200, preparing.data)
        ready = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "ready"},
            format="json",
        )
        self.assertEqual(ready.status_code, 200, ready.data)

    def test_unassigned_captain_cannot_update_another_captains_order(self):
        other_user = get_user_model().objects.create_user(
            username="other-captain", password="password-123", role="captain"
        )
        CaptainProfile.objects.create(user=other_user)
        order = self.make_order()
        self.client.force_authenticate(other_user)
        response = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "awaiting_confirmation"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, "delivering")

    def test_auto_completion_waits_twelve_hours_and_skips_open_disputes(self):
        now = timezone.now()
        order = self.make_order(status="awaiting_confirmation")
        order.captain_delivered_at = now - timedelta(hours=12)
        order.save(update_fields=["captain_delivered_at"])
        ticket = SupportTicket.objects.create(
            order=order, user=self.customer, subject="Delivery issue", message="Please review this order."
        )

        self.assertEqual(complete_expired_order_confirmations(now), 0)
        order.refresh_from_db()
        self.assertEqual(order.status, "awaiting_confirmation")
        ticket.status = "resolved"
        ticket.save(update_fields=["status"])
        self.assertEqual(complete_expired_order_confirmations(now), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, "completed")
        self.assertEqual(order.completion_method, "automatic")
        self.assertIsNone(order.completed_by_id)
        self.assertEqual(order.completed_by_name, "Automatic")
        self.assertEqual(order.completed_at, now)
        self.assertEqual(complete_expired_order_confirmations(now), 0)
        self.assertEqual(CashSettlement.objects.filter(order=order).count(), 1)

    def test_auto_completion_does_not_run_before_twelve_hours(self):
        order = self.make_order(status="awaiting_confirmation")
        order.captain_delivered_at = timezone.now() - timedelta(hours=11, minutes=59)
        order.save(update_fields=["captain_delivered_at"])
        self.assertEqual(complete_expired_order_confirmations(), 0)
        order.refresh_from_db()
        self.assertEqual(order.status, "awaiting_confirmation")

    def test_online_and_ride_completions_create_no_merchant_receivable(self):
        for order_type, payment_method in (("store", "online"), ("ride", "cash")):
            order = self.make_order(
                status="awaiting_confirmation",
                order_type=order_type,
                payment_method=payment_method,
            )
            self.client.force_authenticate(self.customer)
            response = self.client.post(
                f"/api/orders/{order.id}/status/",
                {"status": "completed"},
                format="json",
            )
            self.assertEqual(response.status_code, 200, response.data)
            self.assertFalse(CashSettlement.objects.filter(order=order).exists())

    def test_customer_cancellation_does_not_create_cash_receivable(self):
        order = self.make_order(status="new")
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            f"/api/orders/{order.id}/status/",
            {"status": "cancelled"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(CashSettlement.objects.filter(order=order).exists())

    def test_admin_can_record_partial_receipts_and_continue_the_remaining_balance(self):
        order = self.make_order(status="completed")
        settlement = self.make_settlement(order)
        self.client.force_authenticate(self.admin)
        first_payload = {
            "captain_id": self.captain.id,
            "order_ids": [order.id],
            "amount": "10.00",
            "reference": "BANK-001",
            "notes": "First installment",
        }
        precision_error = self.client.post(
            "/api/settlements/receipts/",
            {**first_payload, "amount": "1.001", "reference": "BANK-PRECISION"},
            format="json",
        )
        self.assertEqual(precision_error.status_code, 400)
        self.assertFalse(CashSettlementReceipt.objects.exists())
        first = self.client.post("/api/settlements/receipts/", first_payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["recorded_by"], self.admin.username)
        self.assertEqual(first.data["allocations"][0]["amount"], "10.00")
        allocated = CashSettlementAllocation.objects.filter(settlement=settlement).aggregate(total=Sum("amount"))["total"]
        self.assertEqual(allocated, Decimal("10.00"))

        retry = self.client.post("/api/settlements/receipts/", first_payload, format="json")
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(CashSettlementReceipt.objects.filter(reference="BANK-001").count(), 1)

        remaining = self.client.post(
            "/api/settlements/receipts/",
            {
                **first_payload,
                "amount": "20.00",
                "reference": "BANK-002",
                "notes": "Second installment",
            },
            format="json",
        )
        self.assertEqual(remaining.status_code, 201, remaining.data)
        overpayment = self.client.post(
            "/api/settlements/receipts/",
            {
                **first_payload,
                "amount": "10.01",
                "reference": "BANK-003",
            },
            format="json",
        )
        self.assertEqual(overpayment.status_code, 400)
        last = self.client.post(
            "/api/settlements/receipts/",
            {
                **first_payload,
                "amount": "10.00",
                "reference": "BANK-004",
                "notes": "Final installment",
            },
            format="json",
        )
        self.assertEqual(last.status_code, 201, last.data)
        self.assertEqual(
            sum(row.amount for row in CashSettlementAllocation.objects.filter(settlement=settlement)),
            Decimal("40.00"),
        )
        ledger = self.client.get("/api/settlements/ledger/")
        self.assertEqual(ledger.status_code, 200)
        self.assertEqual(ledger.data["outstanding"], "0.00")
        self.assertEqual(ledger.data["orders"][0]["status"], "settled")

    def test_only_finance_staff_can_record_receipts(self):
        order = self.make_order(status="completed")
        self.make_settlement(order)
        self.client.force_authenticate(self.captain_user)
        response = self.client.post(
            "/api/settlements/receipts/",
            {
                "captain_id": self.captain.id,
                "order_ids": [order.id],
                "amount": "1.00",
                "reference": "CAPTAIN-SELF-RECEIPT",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CashSettlementReceipt.objects.exists())

    def test_admin_can_grant_and_revoke_finance_staff_access(self):
        employee = get_user_model().objects.create_user(
            username="finance-employee", password="password-123", role="customer"
        )
        order = self.make_order(status="completed")
        self.make_settlement(order)
        self.client.force_authenticate(self.admin)
        updated = self.client.patch(
            f"/api/admin/users/{employee.id}/",
            {"is_finance_staff": True},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        employee.refresh_from_db()
        self.assertTrue(employee.is_finance_staff)
        self.assertFalse(employee.is_staff)
        self.client.force_authenticate(employee)
        ledger = self.client.get("/api/settlements/ledger/")
        self.assertEqual(ledger.status_code, 200, ledger.data)
        receipt = self.client.post(
            "/api/settlements/receipts/",
            {
                "captain_id": self.captain.id,
                "order_ids": [order.id],
                "amount": "5.00",
                "reference": "STAFF-001",
            },
            format="json",
        )
        self.assertEqual(receipt.status_code, 201, receipt.data)
        self.client.force_authenticate(self.admin)
        revoked = self.client.patch(
            f"/api/admin/users/{employee.id}/",
            {"is_finance_staff": False},
            format="json",
        )
        self.assertEqual(revoked.status_code, 200, revoked.data)
        employee.refresh_from_db()
        self.assertFalse(employee.is_finance_staff)
        audit = self.client.get("/api/admin/finance-audit/")
        self.assertEqual(audit.status_code, 200)
        self.assertEqual([row["granted"] for row in audit.data[:2]], [False, True])
        self.assertEqual(audit.data[0]["changed_by"], self.admin.username)
        self.client.force_authenticate(employee)
        self.assertEqual(self.client.get("/api/admin/finance-audit/").status_code, 403)

    def test_merchant_report_tracks_outstanding_product_funds(self):
        order = self.make_order(status="completed")
        self.make_settlement(order)
        self.client.force_authenticate(self.merchant_user)
        response = self.client.get("/api/merchant/reports/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cash_products_due"], "40.00")
        self.assertEqual(response.data["cash_settlements"][0]["outstanding_amount"], "40.00")

    def test_admin_dashboard_counts_customer_confirmation_as_active(self):
        self.make_order(status="awaiting_confirmation")
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/dashboard/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["active_orders"], 1)
