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


# Store rows that never received an activity (the merchant-account form creates
# them with ``category="general"``) have no service relation at all. The console
# and the merchant API still report such a store as a food store, because
# ``MerchantProfile.service_type`` falls back to the generic store flow. The
# catalogue has to resolve them the same way: otherwise an approved, open
# restaurant is listed under Food in administration but is missing from the
# customer app. The fallback only covers these "no activity chosen" values, so a
# store parked on a real activity is never mixed into another service.
UNRESOLVED_STORE_CATEGORIES = ("", "general", "general_store", "other")
FALLBACK_SERVICE = "food"


def legacy_categories_for(service):
    """Legacy free-text category values that map to ``service``."""
    return [category for category, code in MERCHANT_CATEGORY_SERVICE.items() if code == service]


def unresolved_store_q(prefix=""):
    """Stores with no activity, no explicit service and no declared trade."""
    return (
        Q(**{f"{prefix}business_category__isnull": True})
        & Q(**{f"{prefix}services__isnull": True})
        & Q(**{f"{prefix}category__in": UNRESOLVED_STORE_CATEGORIES})
    )


def merchant_service_q(service):
    """A ``MerchantProfile`` filter matching every real link to ``service``."""
    query = (
        Q(business_category__service__code=service)
        | Q(business_category__service__fulfilment_service__code=service)
        | Q(services__code=service)
        | Q(services__fulfilment_service__code=service)
        | Q(category__in=legacy_categories_for(service))
    )
    if service == FALLBACK_SERVICE:
        query |= unresolved_store_q()
    return query


def product_service_q(service):
    """The same rule expressed from a ``Product`` queryset."""
    query = (
        Q(merchant__business_category__service__code=service)
        | Q(merchant__business_category__service__fulfilment_service__code=service)
        | Q(merchant__services__code=service)
        | Q(merchant__services__fulfilment_service__code=service)
        | Q(merchant__category__in=legacy_categories_for(service))
    )
    if service == FALLBACK_SERVICE:
        query |= unresolved_store_q("merchant__")
    return query


def is_pharmacy_merchant(merchant):
    """True when the store trades as a pharmacy, whatever linked it."""
    if merchant is None:
        return False
    if merchant.business_category_id:
        activity = merchant.business_category
        service = activity.service if activity is not None else None
        if service is not None and service.effective_code == "pharmacy":
            return True
    if merchant.pk and merchant.services.filter(
        Q(code="pharmacy") | Q(fulfilment_service__code="pharmacy")
    ).exists():
        return True
    return (merchant.category or "").strip().lower() == "pharmacy"
