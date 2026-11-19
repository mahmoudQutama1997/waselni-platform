"""Resolve which platform service a store actually trades under.

A store is linked to a service through three real sources, in order of
authority:

* ``business_category.service`` - the administrator-managed activity (the
  relation introduced in migration 0021),
* the explicit ``services`` many-to-many assignment,
* the legacy free-text ``category`` value used before those relations existed.

The public catalogue, the product shelf and the admin console must all apply
the same rule. Otherwise an approved store can disappear from the customer app
while the administration still lists it under its service, or a pharmacy page
can expose prescription-only medicine because it resolved the store wrongly.
"""
from django.db.models import Q

from ..models import MERCHANT_CATEGORY_SERVICE


def legacy_categories_for(service):
    """Legacy free-text category values that map to ``service``."""
    return [category for category, code in MERCHANT_CATEGORY_SERVICE.items() if code == service]


def merchant_service_q(service):
    """A ``MerchantProfile`` filter matching every real link to ``service``."""
    return (
        Q(business_category__service__code=service)
        | Q(services__code=service)
        | Q(category__in=legacy_categories_for(service))
    )


def product_service_q(service):
    """The same rule expressed from a ``Product`` queryset."""
    return (
        Q(merchant__business_category__service__code=service)
        | Q(merchant__services__code=service)
        | Q(merchant__category__in=legacy_categories_for(service))
    )


def is_pharmacy_merchant(merchant):
    """True when the store trades as a pharmacy, whatever linked it."""
    if merchant is None:
        return False
    if merchant.business_category_id:
        activity = merchant.business_category
        service = activity.service if activity is not None else None
        if service is not None and service.code == "pharmacy":
            return True
    if merchant.pk and merchant.services.filter(code="pharmacy").exists():
        return True
    return (merchant.category or "").strip().lower() == "pharmacy"
