"""Resolve which platform service a store actually trades under.

A store is linked to a service through three real sources, in order of
authority:

* ``business_category.service`` - the administrator-managed activity (the
  relation introduced in migration 0021),
* the explicit ``services`` many-to-many assignment,
* the legacy free-text ``category`` value used before those relations existed.

``MerchantProfile.service_type`` is the platform's own classification: it is
what the administration and the merchant portal display, and it resolves an
activity's service first and falls back to the legacy category (then to the
implemented food flow). The public catalogue, the product shelf and the admin
console must apply exactly the same rule. Otherwise an approved, open
restaurant can disappear from the customer app while administration still lists
it under Food, or a pharmacy page can expose prescription-only medicine because
it resolved the store wrongly.

Two data shapes used to break that agreement:

* a store with no activity, no service row and a generic category (the
  merchant-account form creates ``category="general"``),
* a store parked on an activity whose ``service`` was never linked (or an
  activity code such as ``bakery`` that the legacy map does not know).

Both keep the platform's default flow - food - so the catalogue must keep
returning them under food instead of hiding them.
"""
from django.db.models import Q
from django.utils import timezone

from ..models import MERCHANT_CATEGORY_SERVICE


def legacy_categories_for(service):
    """Legacy free-text category values that name ``service``."""
    return [category for category, code in MERCHANT_CATEGORY_SERVICE.items() if code == service]


def other_service_categories(service):
    """Legacy category values that name a *different* service."""
    return [category for category, code in MERCHANT_CATEGORY_SERVICE.items() if code != service]


def authoritative_service_q(service, prefix=""):
    """Rows whose activity or explicit service rows resolve to ``service``."""
    return (
        Q(**{f"{prefix}business_category__service__code": service})
        | Q(**{f"{prefix}business_category__service__fulfilment_service__code": service})
        | Q(**{f"{prefix}services__code": service})
        | Q(**{f"{prefix}services__fulfilment_service__code": service})
    )


def unlinked_store_q(prefix=""):
    """Stores whose service is not stated by an activity or an explicit row."""
    return (
        (
            Q(**{f"{prefix}business_category__isnull": True})
            | Q(**{f"{prefix}business_category__service__isnull": True})
        )
        & Q(**{f"{prefix}services__isnull": True})
    )


def merchant_service_q(service):
    """A ``MerchantProfile`` filter matching every store classified as ``service``.

    The rule mirrors ``MerchantProfile.service_type``: an activity or explicit
    service relation wins; with no relation at all the legacy category decides,
    and a category that names another service keeps the store out. A category
    that names no known service (or none at all) keeps the default food flow,
    which is what stops an approved restaurant from vanishing from the app.
    """
    return authoritative_service_q(service) | (
        unlinked_store_q() & ~Q(category__in=other_service_categories(service))
    )


def product_service_q(service):
    """The same rule expressed from a ``Product`` queryset."""
    return authoritative_service_q(service, "merchant__") | (
        unlinked_store_q("merchant__")
        & ~Q(merchant__category__in=other_service_categories(service))
    )


def catalogue_visibility_reasons(store, today=None):
    """Every gate that keeps ``store`` out of the customer catalogue.

    A store is offered to customers only when its approval, open state and
    subscription all pass. The admin console shows these reasons, so a hidden
    store never turns into a silent mystery.
    """
    today = today or timezone.localdate()
    reasons = []
    if store.approval_status == "approved":
        pass
    elif store.approval_status == "pending":
        reasons.append("approval_pending")
    elif store.approval_status == "rejected":
        reasons.append("approval_rejected")
    elif store.approval_status == "suspended":
        reasons.append("suspended")
    else:
        reasons.append("approval_missing")
    if not store.is_open:
        reasons.append("closed")
    if store.temporarily_closed:
        reasons.append("temporarily_closed")
    user = store.user
    if user.subscription_required and not user.subscriptions.filter(
        status="active", starts_on__lte=today, ends_on__gte=today
    ).exists():
        reasons.append("subscription_inactive")
    return reasons


def store_catalogue_visibility(store, today=None):
    """``{"visible", "reasons", "service"}`` for one store, for the admin console."""
    reasons = catalogue_visibility_reasons(store, today)
    return {
        "visible": not reasons,
        "reasons": reasons,
        "service": store.service_type,
    }


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
