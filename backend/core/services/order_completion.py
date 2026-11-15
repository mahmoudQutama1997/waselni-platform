from datetime import timedelta
import uuid

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from core.models import CashSettlement, Order, SupportTicket


CONFIRMATION_GRACE_PERIOD = timedelta(hours=12)


def complete_order(order, *, completed_by, method, completed_at=None):
    """Record completion once, independently of any later cash collection."""
    if order.status != "awaiting_confirmation":
        return False

    completed_at = completed_at or timezone.now()
    order.status = "completed"
    order.completed_at = completed_at
    order.completed_by = completed_by
    order.completed_by_name = (
        completed_by.get_full_name() or completed_by.username
        if completed_by else "Automatic"
    )
    order.completion_method = method
    order.save(update_fields=[
        "status", "completed_at", "completed_by", "completed_by_name",
        "completion_method", "updated_at",
    ])

    if (
        order.order_type == "store"
        and order.payment_method == "cash"
        and order.merchant_id
        and order.captain_id
    ):
        CashSettlement.objects.get_or_create(
            order=order,
            defaults={
                "merchant": order.merchant,
                "captain": order.captain,
                "amount": order.subtotal,
                "reference": uuid.uuid4().hex[:12].upper(),
            },
        )
    return True


def complete_expired_order_confirmations(now=None):
    """Complete due orders unless an unresolved order-linked support ticket exists."""
    now = now or timezone.now()
    cutoff = now - CONFIRMATION_GRACE_PERIOD
    unresolved_tickets = SupportTicket.objects.filter(
        order_id=OuterRef("pk"),
        status__in=("open", "in_review"),
    )
    completed = 0
    with transaction.atomic():
        orders = (
            Order.objects.select_for_update(of=("self",))
            .filter(status="awaiting_confirmation", captain_delivered_at__lte=cutoff)
            .annotate(has_unresolved_ticket=Exists(unresolved_tickets))
            .filter(has_unresolved_ticket=False)
            .select_related("merchant", "captain")
            .order_by("id")
        )
        for order in orders:
            if complete_order(order, completed_by=None, method="automatic", completed_at=now):
                completed += 1
    return completed
