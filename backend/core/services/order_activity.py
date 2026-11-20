from core.models import OrderActivity


def record_order_activity(order, event, *, actor=None, from_status="", to_status=None):
    actor_name = (
        (actor.get_full_name() or actor.get_username())
        if actor is not None
        else "Automatic"
    )
    return OrderActivity.objects.create(
        order=order,
        event=event,
        from_status=from_status or "",
        to_status=to_status if to_status is not None else order.status,
        actor=actor,
        actor_name=actor_name,
    )
