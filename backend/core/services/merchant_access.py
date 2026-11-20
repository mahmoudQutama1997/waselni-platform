"""Merchant ownership, staff roles and permission checks.

Every merchant-facing API resolves the caller through ``merchant_access`` so a
staff member can never read another merchant's data and each role only gets the
permissions the owner granted.  Buttons hidden in React are never the control:
these checks run server-side on every request.
"""
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from ..models import MerchantStaff, StoreClosure

ALL_PERMISSIONS = {"orders", "preparation", "inventory", "prices", "reports", "staff"}
ROLE_PERMISSIONS = {
    "manager": ALL_PERMISSIONS,
    "orders": {"orders"},
    "preparation": {"orders", "preparation"},
    "inventory": {"inventory", "prices"},
    "reports": {"reports"},
}
PERMISSION_LABELS = {
    "orders": "Manage orders and delivery status",
    "preparation": "Move orders through preparation",
    "inventory": "Adjust stock and products",
    "prices": "Change prices and promotions",
    "reports": "View reports and settlements",
    "staff": "Manage store staff",
}


class MerchantAccess:
    """Result of resolving a user to a merchant and its permissions."""

    def __init__(self, merchant, permissions, role, is_owner, staff=None):
        self.merchant = merchant
        self.permissions = set(permissions)
        self.role = role
        self.is_owner = is_owner
        self.staff = staff

    def can(self, permission):
        return permission in self.permissions


def merchant_access(user):
    """Return the merchant context for ``user`` or ``None``.

    Merchant owners get every permission; active staff get the permissions of
    their assigned role.  Unrelated users (customers, captains, admins) get None
    even when ``user.role == "merchant"`` but no profile exists.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if user.role == "merchant":
        try:
            profile = user.merchant_profile
        except ObjectDoesNotExist:
            profile = None
        if profile is not None:
            return MerchantAccess(profile, ALL_PERMISSIONS, "owner", True)
    staff = (
        MerchantStaff.objects.select_related("merchant")
        .filter(user=user, is_active=True)
        .first()
    )
    if staff is None:
        return None
    permissions = ROLE_PERMISSIONS.get(staff.role, set())
    return MerchantAccess(staff.merchant, permissions, staff.role, False, staff)


def _minutes(value):
    return value.hour * 60 + value.minute


def store_open_state(merchant, now=None):
    """Decide whether the store accepts new orders right now.

    Returns ``(ok, reason)``.  A store without configured weekly hours keeps its
    legacy behaviour (only ``is_open``/``temporarily_closed`` matter).
    """
    now = now or timezone.localtime()
    if not merchant.accepts_orders:
        return False, "store_closed"
    if StoreClosure.objects.filter(
        merchant=merchant, branch__isnull=True, date=now.date()
    ).exists():
        return False, "store_closed"
    hours = [row for row in merchant.business_hours.all() if row.branch_id is None]
    if not hours:
        return True, None
    row = next((item for item in hours if item.weekday == now.weekday()), None)
    if row is None or row.is_closed:
        return False, "store_closed"
    if row.opens_at and row.closes_at:
        current = _minutes(now.time())
        if not _minutes(row.opens_at) <= current <= _minutes(row.closes_at):
            return False, "outside_hours"
    return True, None


def require_merchant(user, permission=None):
    """Return the merchant access or raise PermissionError-style None.

    Views convert ``None`` into a 403 with a clear message; returning None keeps
    this helper free of DRF imports for reuse from services and tests.
    """
    access = merchant_access(user)
    if access is None:
        return None
    if permission and not access.can(permission):
        return None
    return access
