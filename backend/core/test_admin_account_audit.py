from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AdminAccountAudit, CaptainProfile

User = get_user_model()


class AdminAccountAuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="audit-admin", password="safe-password-123", role="admin"
        )
        self.customer = User.objects.create_user(
            username="audit-customer", password="safe-password-123", role="customer"
        )
        self.captain = User.objects.create_user(
            username="audit-captain", password="safe-password-123", role="captain"
        )
        self.profile = CaptainProfile.objects.create(user=self.captain)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_account_status_requires_reason_and_persists_immutable_audit_row(self):
        url = f"/api/admin/users/{self.customer.id}/"
        missing_reason = self.client.patch(url, {"is_active": False}, format="json")
        self.assertEqual(missing_reason.status_code, 400)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
        self.assertFalse(AdminAccountAudit.objects.exists())

        updated = self.client.patch(
            url, {"is_active": False, "reason": "Confirmed account abuse"}, format="json"
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        audit = AdminAccountAudit.objects.get()
        self.assertEqual(audit.target, self.customer)
        self.assertEqual(audit.changed_by, self.admin)
        self.assertEqual(audit.action, "account_status")
        self.assertEqual((audit.previous_value, audit.new_value), ("active", "disabled"))
        self.assertEqual(audit.reason, "Confirmed account abuse")

        self.assertEqual(self.client.get("/api/admin/account-audit/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/admin/account-audit/{audit.id}/", {}, format="json").status_code, 404)

    def test_captain_approval_requires_reason_and_records_decision(self):
        url = f"/api/admin/captains/{self.profile.id}/approval/"
        missing_reason = self.client.post(url, {"status": "rejected"}, format="json")
        self.assertEqual(missing_reason.status_code, 400)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.rejected)
        self.assertFalse(AdminAccountAudit.objects.exists())

        updated = self.client.post(
            url,
            {"status": "rejected", "reason": "Identity document could not be verified"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        audit = AdminAccountAudit.objects.get()
        self.assertEqual(audit.target, self.captain)
        self.assertEqual(audit.action, "captain_approval")
        self.assertEqual((audit.previous_value, audit.new_value), ("pending", "rejected"))

    def test_non_admin_cannot_change_or_read_audit_data(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/admin/account-audit/").status_code, 403)
        self.assertEqual(
            self.client.patch(
                f"/api/admin/users/{self.customer.id}/",
                {"is_active": False, "reason": "Unauthorized"},
                format="json",
            ).status_code,
            403,
        )
