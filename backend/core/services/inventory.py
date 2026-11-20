"""Stock ledger helpers.

``record_movement`` is the single place that writes ``InventoryMovement`` rows.
Callers must already hold the product row (or use the conditional update in
``reserve_stock``) so the before/after values are accurate under concurrency.
"""
from django.db import IntegrityError, transaction

from ..models import InventoryMovement


def record_movement(product, delta, reason, *, actor=None, order=None, before=None, after=None, note=""):
    """Append one stock movement, tolerating a retried order reservation.

    The partial unique constraint ``uniq_order_stock_deduction`` guarantees the
    same order can never deduct the same product twice; a duplicate insert is
    ignored instead of failing the whole request.
    """
    try:
        with transaction.atomic():
            return InventoryMovement.objects.create(
                product=product,
                order=order,
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                delta=delta,
                quantity_before=before,
                quantity_after=after,
                reason=reason,
                note=(note or "")[:255],
            )
    except IntegrityError:
        if reason == "order":
            return None
        raise
