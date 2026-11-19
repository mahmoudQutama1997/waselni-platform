"""Admin control center: services, regions, providers, branches, staff, settings.

Every endpoint re-checks the admin role server-side; hiding a tab in React is
never the control. Mutations write an AuditLog row inside the same transaction
as the change so an action and its audit trail cannot diverge.
"""
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    SERVICE_CODES, AuditLog, BusinessCategory, CaptainServiceEligibility, MerchantBranch,
    MerchantProfile, Order, PlatformService, PlatformSettings, Product, ServiceRegion, User,
)
from .services.admin_control import (
    ADMIN_ROLE_LABELS, PERMISSION_ROLES, admin_role, has_permission, permissions_for, record_audit,
)

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def guard(request, permission):
    if not has_permission(request.user, permission):
        raise PermissionDenied("Your admin role does not allow this action.")


def as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def decimal_or_none(value, field):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "Enter a valid amount."})
    if parsed < 0:
        raise ValidationError({field: "The value cannot be negative."})
    return parsed


def small_int(value, default=100):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError({"sort_order": "Enter a whole number."})
    if parsed < 0 or parsed > 10000:
        raise ValidationError({"sort_order": "Enter a number between 0 and 10000."})
    return parsed


def coordinate_or_none(value, field):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "Enter a valid coordinate."})
    if parsed < -180 or parsed > 180:
        raise ValidationError({field: "Enter a valid coordinate."})
    return parsed


def service_payload(service, request=None):
    image = None
    if service.image:
        try:
            image = request.build_absolute_uri(service.image.url) if request else service.image.url
        except ValueError:
            image = None
    return {
        "id": service.id,
        "code": service.code,
        "name_ar": service.name_ar,
        "name_en": service.name_en,
        "name_he": service.name_he,
        "description_ar": service.description_ar,
        "description_en": service.description_en,
        "category": service.category,
        "business_type": service.business_type,
        "workflow": service.workflow,
        "pricing_mode": service.pricing_mode,
        "requires_merchant": service.requires_merchant,
        "requires_captain": service.requires_captain,
        "requires_specialist": service.requires_specialist,
        "requires_booking": service.requires_booking,
        "is_operational": service.is_operational,
        "is_active": service.is_active,
        "icon": service.icon,
        "image": image,
        "provider_requirements": service.provider_requirements,
        "order_flow": service.order_flow,
        "working_hours": service.working_hours,
        "regions": [{"id": r.id, "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en} for r in service.regions.all()],
        "sort_order": service.sort_order,
        "updated_at": service.updated_at.isoformat() if service.updated_at else None,
    }


def business_category_payload(category):
    service = category.service
    return {
        "id": category.id,
        "code": category.code,
        "name_ar": category.name_ar,
        "name_en": category.name_en,
        "service": {
            "id": service.id, "code": service.code,
            "name_ar": service.name_ar, "name_en": service.name_en,
            "is_active": service.is_active, "is_operational": service.is_operational,
        } if service else None,
        "service_id": category.service_id,
        "requires_license": category.requires_license,
        "is_active": category.is_active,
        "sort_order": category.sort_order,
        "merchants_count": getattr(category, "merchants_count", None),
    }


def region_payload(region):
    return {
        "id": region.id,
        "code": region.code,
        "name_ar": region.name_ar,
        "name_en": region.name_en,
        "center_latitude": float(region.center_latitude) if region.center_latitude is not None else None,
        "center_longitude": float(region.center_longitude) if region.center_longitude is not None else None,
        "radius_km": region.radius_km,
        "is_active": region.is_active,
        "branches_count": getattr(region, "branches_count", None),
    }


def _apply_choice(data, key, choices):
    if key in data:
        value = str(data[key]).strip()
        if value not in dict(choices):
            raise ValidationError({key: "Choose a supported value."})
        return value
    return None


class AdminControlMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = admin_role(request.user)
        if not role:
            raise PermissionDenied("Admin access only.")
        return Response({
            "username": request.user.username,
            "name": request.user.get_full_name() or request.user.username,
            "role": role,
            "role_label": ADMIN_ROLE_LABELS.get(role, role),
            "permissions": permissions_for(request.user),
            "permission_roles": {key: sorted(value) for key, value in PERMISSION_ROLES.items()},
            "role_labels": ADMIN_ROLE_LABELS,
            "roles": [{"code": code, "label": label} for code, label in User.ADMIN_ROLES],
            "services": list(SERVICE_CODES),
        })


class ServiceCatalogView(APIView):
    """The customer-facing service directory: only active, wired services."""

    permission_classes = [AllowAny]

    def get(self, request):
        lang = (request.query_params.get("lang") or "ar").lower()
        rows = (PlatformService.objects.filter(is_active=True, is_operational=True)
                .prefetch_related("regions").order_by("sort_order", "id"))
        countries = []
        for service in rows:
            name = service.name_ar if lang == "ar" else (service.name_he if lang == "he" and service.name_he else service.name_en)
            description = service.description_ar if lang == "ar" else service.description_en
            countries.append({
                "id": service.id,
                "code": service.code,
                "name": name or service.name_en,
                "name_ar": service.name_ar,
                "name_en": service.name_en,
                "description": description,
                "category": service.category,
                "icon": service.icon,
                "workflow": service.workflow,
                "pricing_mode": service.pricing_mode,
                "regions": [region.code for region in service.regions.all() if region.is_active],
            })
        return Response(countries)


class AdminPharmacyProductsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "providers")
        rows = Product.objects.select_related("merchant").filter(
            merchant__category="pharmacy",
        ).order_by("pharmacy_review_status", "name")
        return Response([{
            "id": product.id,
            "name": product.name,
            "category": product.category,
            "price": str(product.price),
            "merchant_id": product.merchant_id,
            "merchant_name": product.merchant.shop_name,
            "prescription_required": product.prescription_required,
            "controlled_substance": product.controlled_substance,
            "review_status": product.pharmacy_review_status,
        } for product in rows])

    def patch(self, request, product_id):
        guard(request, "providers")
        status = str(request.data.get("status", ""))
        if status not in ("approved", "rejected"):
            raise ValidationError({"status": "Choose approved or rejected."})
        with transaction.atomic():
            product = Product.objects.select_for_update().select_related("merchant").filter(
                pk=product_id, merchant__category="pharmacy",
            ).first()
            if product is None:
                raise NotFound("Pharmacy product not found.")
            if status == "approved" and (product.prescription_required or product.controlled_substance):
                raise ValidationError("Prescription-required and controlled products cannot be listed for online ordering.")
            previous = product.pharmacy_review_status
            product.pharmacy_review_status = status
            product.save(update_fields=["pharmacy_review_status"])
            record_audit(
                request.user, "pharmacy_product.review", "product", product.id,
                f"Set pharmacy product {product.name} to {status}",
                before={"review_status": previous}, after={"review_status": status},
            )
        return Response({
            "id": product.id,
            "review_status": product.pharmacy_review_status,
        })


class AdminServicesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "services")
        query = (request.query_params.get("q") or "").strip().lower()
        category = request.query_params.get("category") or ""
        active = request.query_params.get("active")
        qs = PlatformService.objects.prefetch_related("regions").all()
        if query:
            qs = qs.filter(Q(code__icontains=query) | Q(name_ar__icontains=query) | Q(name_en__icontains=query))
        if category:
            qs = qs.filter(category=category)
        if active in ("0", "1"):
            qs = qs.filter(is_active=active == "1")
        services = list(qs)

        approved_captains = dict(
            CaptainServiceEligibility.objects.filter(status="approved", service__isnull=False)
            .values_list("service").annotate(total=Count("id"))
        )
        merchant_counts = dict(
            PlatformService.objects.filter(merchants__isnull=False)
            .values_list("code").annotate(total=Count("merchants"))
        )
        branch_counts = dict(
            PlatformService.objects.filter(branches__isnull=False)
            .values_list("code").annotate(total=Count("branches"))
        )
        active_orders = dict(
            Order.objects.exclude(status__in=["completed", "cancelled"])
            .values_list("service_type").annotate(total=Count("id"))
        )
        rows = []
        for service in services:
            row = service_payload(service, request)
            row["captains_count"] = approved_captains.get(service.code, 0)
            row["merchants_count"] = merchant_counts.get(service.code, 0)
            row["branches_count"] = branch_counts.get(service.code, 0)
            row["active_orders"] = active_orders.get(service.code, 0)
            row["implemented"] = service.code in SERVICE_CODES
            rows.append(row)
        return Response({
            "services": rows,
            "categories": [{"code": code, "label": label} for code, label in PlatformService.CATEGORIES],
            "workflows": [{"code": code, "label": label} for code, label in PlatformService.WORKFLOWS],
            "business_types": [{"code": code, "label": label} for code, label in PlatformService.BUSINESS_TYPES],
            "pricing_modes": [{"code": code, "label": label} for code, label in PlatformService.PRICING_MODES],
            "regions": [region_payload(r) for r in ServiceRegion.objects.annotate(branches_count=Count("branches"))],
            "operational_codes": list(SERVICE_CODES),
        })

    def post(self, request):
        guard(request, "services")
        data = request.data
        code = str(data.get("code", "")).strip().lower()
        if not CODE_RE.match(code):
            raise ValidationError({"code": "Use a lowercase code such as 'flowers' (2-40 characters, a-z, 0-9, _)."})
        if PlatformService.objects.filter(code=code).exists():
            raise ValidationError({"code": "A service with this code already exists."})
        name_ar = str(data.get("name_ar", "")).strip()
        name_en = str(data.get("name_en", "")).strip()
        if not name_ar or not name_en:
            raise ValidationError("Arabic and English names are required.")
        is_operational = code in SERVICE_CODES
        is_active = as_bool(data.get("is_active")) and is_operational
        try:
            sort_order = max(0, int(data.get("sort_order") or 100))
        except (TypeError, ValueError):
            raise ValidationError({"sort_order": "Enter a whole number."})
        with transaction.atomic():
            service = PlatformService.objects.create(
                code=code,
                name_ar=name_ar[:120],
                name_en=name_en[:120],
                name_he=str(data.get("name_he", "")).strip()[:120],
                description_ar=str(data.get("description_ar", "")).strip(),
                description_en=str(data.get("description_en", "")).strip(),
                category=_apply_choice(data, "category", PlatformService.CATEGORIES) or "other",
                business_type=_apply_choice(data, "business_type", PlatformService.BUSINESS_TYPES) or "merchant",
                workflow=_apply_choice(data, "workflow", PlatformService.WORKFLOWS) or "merchant_accept",
                pricing_mode=_apply_choice(data, "pricing_mode", PlatformService.PRICING_MODES) or "fixed",
                requires_merchant=as_bool(data.get("requires_merchant", True)),
                requires_captain=as_bool(data.get("requires_captain", True)),
                requires_specialist=as_bool(data.get("requires_specialist", False)),
                requires_booking=as_bool(data.get("requires_booking", False)),
                is_operational=is_operational,
                is_active=is_active,
                icon=str(data.get("icon", "")).strip()[:40],
                provider_requirements=str(data.get("provider_requirements", "")).strip(),
                order_flow=[str(x)[:24] for x in data.get("order_flow", []) if str(x).strip()][:20],
                working_hours=data.get("working_hours", []) if isinstance(data.get("working_hours"), list) else [],
                sort_order=sort_order,
            )
            if request.FILES.get("image"):
                service.image = request.FILES["image"]
                service.save(update_fields=["image"])
            region_ids = data.get("regions", [])
            if isinstance(region_ids, list):
                service.regions.set(ServiceRegion.objects.filter(id__in=region_ids))
            record_audit(request.user, "service.create", "service", service.id,
                         f"Created service {service.code}", after=service_payload(service, request))
        return Response(service_payload(service, request), status=201)


class AdminServiceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, service_id):
        service = PlatformService.objects.prefetch_related("regions").filter(pk=service_id).first()
        if service is None:
            raise NotFound("Service not found.")
        return service

    def patch(self, request, service_id):
        guard(request, "services")
        data = request.data
        with transaction.atomic():
            service = PlatformService.objects.select_for_update().prefetch_related("regions").filter(pk=service_id).first()
            if service is None:
                raise NotFound("Service not found.")
            before = service_payload(service, request)
            for field in ("name_ar", "name_en", "name_he", "description_ar", "description_en", "provider_requirements", "icon"):
                if field in data:
                    setattr(service, field, str(data[field]).strip())
            for field, choices in (
                ("category", PlatformService.CATEGORIES),
                ("business_type", PlatformService.BUSINESS_TYPES),
                ("workflow", PlatformService.WORKFLOWS),
                ("pricing_mode", PlatformService.PRICING_MODES),
            ):
                value = _apply_choice(data, field, choices)
                if value:
                    setattr(service, field, value)
            for field in ("requires_merchant", "requires_captain", "requires_specialist", "requires_booking"):
                if field in data:
                    setattr(service, field, as_bool(data[field]))
            if "sort_order" in data:
                try:
                    service.sort_order = max(0, int(data.get("sort_order") or 0))
                except (TypeError, ValueError):
                    raise ValidationError({"sort_order": "Enter a whole number."})
            if "order_flow" in data:
                if not isinstance(data["order_flow"], list) or len(data["order_flow"]) > 20:
                    raise ValidationError({"order_flow": "Send at most 20 flow stages."})
                service.order_flow = [str(x)[:24] for x in data["order_flow"] if str(x).strip()]
            if "working_hours" in data:
                if not isinstance(data["working_hours"], list) or len(data["working_hours"]) > 21:
                    raise ValidationError({"working_hours": "Send at most 21 weekly rows."})
                service.working_hours = data["working_hours"]
            if "is_active" in data:
                wanted = as_bool(data["is_active"])
                if wanted and not service.is_operational:
                    raise ValidationError({"is_active": "This service has no implemented order flow yet, so it cannot be offered to customers."})
                service.is_active = wanted
            service.save()
            if "regions" in data:
                ids = data["regions"] if isinstance(data["regions"], list) else []
                service.regions.set(ServiceRegion.objects.filter(id__in=ids))
            if request.FILES.get("image"):
                service.image = request.FILES["image"]
                service.save(update_fields=["image"])
            after = service_payload(service, request)
            record_audit(request.user, "service.update", "service", service.id,
                         f"Updated service {service.code}", before=before, after=after)
        return Response(after)


class AdminRegionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "regions")
        rows = ServiceRegion.objects.annotate(branches_count=Count("branches")).order_by("name_en")
        return Response([region_payload(r) for r in rows])

    def post(self, request):
        guard(request, "regions")
        data = request.data
        code = str(data.get("code", "")).strip().lower()
        if not CODE_RE.match(code):
            raise ValidationError({"code": "Use a lowercase region code such as 'ramallah'."})
        if ServiceRegion.objects.filter(code=code).exists():
            raise ValidationError({"code": "This region code already exists."})
        name_ar = str(data.get("name_ar", "")).strip()
        name_en = str(data.get("name_en", "")).strip()
        if not name_ar or not name_en:
            raise ValidationError("Arabic and English names are required.")
        try:
            radius = int(data.get("radius_km") or 15)
        except (TypeError, ValueError):
            raise ValidationError({"radius_km": "Enter a whole number of kilometres."})
        region = ServiceRegion.objects.create(
            code=code, name_ar=name_ar[:80], name_en=name_en[:80],
            center_latitude=coordinate_or_none(data.get("center_latitude"), "center_latitude"),
            center_longitude=coordinate_or_none(data.get("center_longitude"), "center_longitude"),
            radius_km=max(1, min(radius, 300)),
            is_active=as_bool(data.get("is_active", True)),
        )
        record_audit(request.user, "region.create", "region", region.id, f"Created region {region.code}",
                     after=region_payload(region))
        return Response(region_payload(region), status=201)


class AdminRegionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, region_id):
        guard(request, "regions")
        region = ServiceRegion.objects.filter(pk=region_id).first()
        if region is None:
            raise NotFound("Region not found.")
        data = request.data
        before = region_payload(region)
        for field in ("name_ar", "name_en"):
            if field in data:
                setattr(region, field, str(data[field]).strip())
        if "radius_km" in data:
            try:
                region.radius_km = max(1, min(int(data["radius_km"]), 300))
            except (TypeError, ValueError):
                raise ValidationError({"radius_km": "Enter a whole number of kilometres."})
        if "center_latitude" in data:
            region.center_latitude = coordinate_or_none(data["center_latitude"], "center_latitude")
        if "center_longitude" in data:
            region.center_longitude = coordinate_or_none(data["center_longitude"], "center_longitude")
        if "is_active" in data:
            region.is_active = as_bool(data["is_active"])
        region.save()
        record_audit(request.user, "region.update", "region", region.id, f"Updated region {region.code}",
                     before=before, after=region_payload(region))
        return Response(region_payload(region))


class AdminProvidersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "providers")
        status = request.query_params.get("status") or ""
        query = (request.query_params.get("q") or "").strip().lower()
        qs = (MerchantProfile.objects.select_related("user", "business_category__service")
              .prefetch_related("services", "branches").order_by("-created_at"))
        if status in dict(MerchantProfile.APPROVAL_STATES):
            qs = qs.filter(approval_status=status)
        if query:
            qs = qs.filter(Q(shop_name__icontains=query) | Q(user__username__icontains=query) | Q(address__icontains=query))
        stores = list(qs[:300])
        totals = {
            row["merchant_id"]: row for row in
            Order.objects.filter(merchant__in=stores, status="completed")
            .values("merchant_id").annotate(orders=Count("id"), sales=Sum("total"))
        }
        rows = []
        for store in stores:
            total = totals.get(store.id, {})
            rows.append({
                "id": store.id,
                "user_id": store.user_id,
                "username": store.user.username,
                "owner_name": store.user.get_full_name() or store.user.username,
                "phone": store.user.phone,
                "shop_name": store.shop_name,
                "category": store.category,
                "business_category": business_category_payload(store.business_category) if store.business_category_id else None,
                "service_type": store.service_type,
                "address": store.address,
                "latitude": float(store.latitude) if store.latitude is not None else None,
                "longitude": float(store.longitude) if store.longitude is not None else None,
                "approval_status": store.approval_status,
                "rejection_reason": store.rejection_reason,
                "is_open": store.is_open,
                "temporarily_closed": store.temporarily_closed,
                "is_active_account": store.user.is_active,
                "created_at": store.created_at.isoformat(),
                "branch_count": store.branches.count(),
                "services": [s.code for s in store.services.all()],
                "orders_completed": total.get("orders", 0),
                "sales": str(total.get("sales") or Decimal("0.00")),
            })
        return Response({
            "providers": rows,
            "counts": dict(
                MerchantProfile.objects.values_list("approval_status").annotate(total=Count("id"))
            ),
            "business_categories": [
                business_category_payload(category) for category in
                BusinessCategory.objects.select_related("service").filter(is_active=True)
            ],
        })

    def patch(self, request, store_id):
        guard(request, "providers")
        with transaction.atomic():
            store = MerchantProfile.objects.select_for_update().select_related("user").filter(pk=store_id).first()
            if store is None:
                raise NotFound("Provider not found.")
            before = {"approval_status": store.approval_status, "is_open": store.is_open,
                      "category": store.category, "rejection_reason": store.rejection_reason,
                      "business_category": store.business_category_id}
            data = request.data
            if "approval_status" in data:
                status = str(data["approval_status"]).strip()
                if status not in dict(MerchantProfile.APPROVAL_STATES):
                    raise ValidationError({"approval_status": "Choose pending, approved, suspended or rejected."})
                reason = str(data.get("reason", "")).strip()
                if status in ("rejected", "suspended") and not reason:
                    raise ValidationError({"reason": "A reason is required when rejecting or suspending a provider."})
                store.approval_status = status
                store.rejection_reason = reason[:500]
                store.reviewed_at = timezone.now()
                store.reviewed_by = request.user
                if status == "approved" and not store.is_open:
                    store.is_open = True
                # Approving a store must put it in the service of its activity.
                if status == "approved" and store.business_category_id and not store.services.exists():
                    service = store.business_category.service
                    if service is not None:
                        store.services.add(service)
                if status in ("rejected", "suspended"):
                    store.is_open = False
            for field in ("shop_name", "category", "address", "opening_hours"):
                if field in data:
                    setattr(store, field, str(data[field]).strip())
            if "business_category" in data:
                raw = data["business_category"]
                if raw in (None, "", "0"):
                    store.business_category = None
                else:
                    category = BusinessCategory.objects.filter(pk=raw).first() if str(raw).isdigit() else BusinessCategory.objects.filter(code=str(raw).strip()).first()
                    if category is None:
                        raise ValidationError({"business_category": "Choose a valid business activity."})
                    store.business_category = category
                    store.category = category.code
            if "is_open" in data:
                store.is_open = as_bool(data["is_open"]) and store.approval_status == "approved"
            if "temporarily_closed" in data:
                store.temporarily_closed = as_bool(data["temporarily_closed"])
            store.save()
            if "services" in data and isinstance(data["services"], list):
                store.services.set(PlatformService.objects.filter(id__in=data["services"]))
            after = {"approval_status": store.approval_status, "is_open": store.is_open,
                     "category": store.category, "rejection_reason": store.rejection_reason,
                     "business_category": store.business_category_id,
                     "services": [s.code for s in store.services.all()]}
            record_audit(request.user, "provider.review", "merchant", store.id,
                         f"{store.shop_name}: {store.approval_status}", before=before, after=after)
        return Response({"ok": True, **after})


class AdminBranchesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "branches")
        query = (request.query_params.get("q") or "").strip().lower()
        region = request.query_params.get("region") or ""
        qs = MerchantBranch.objects.select_related("merchant", "region").prefetch_related("services").order_by("id")
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(merchant__shop_name__icontains=query) | Q(address__icontains=query))
        if region:
            qs = qs.filter(region__code=region)
        branches = list(qs[:400])
        order_counts = dict(
            Order.objects.filter(branch__in=branches).values_list("branch_id").annotate(total=Count("id"))
        )
        return Response({
            "branches": [{
                "id": b.id,
                "merchant_id": b.merchant_id,
                "merchant": b.merchant.shop_name,
                "name": b.name,
                "address": b.address,
                "phone": b.phone,
                "latitude": float(b.latitude) if b.latitude is not None else None,
                "longitude": float(b.longitude) if b.longitude is not None else None,
                "opening_hours": b.opening_hours,
                "is_active": b.is_active,
                "region": {"id": b.region.id, "code": b.region.code, "name_en": b.region.name_en, "name_ar": b.region.name_ar} if b.region else None,
                "services": [s.code for s in b.services.all()],
                "orders_count": order_counts.get(b.id, 0),
            } for b in branches],
            "regions": [region_payload(r) for r in ServiceRegion.objects.annotate(branches_count=Count("branches"))],
        })

    def patch(self, request, branch_id):
        guard(request, "branches")
        branch = MerchantBranch.objects.select_related("merchant").filter(pk=branch_id).first()
        if branch is None:
            raise NotFound("Branch not found.")
        data = request.data
        before = {"name": branch.name, "is_active": branch.is_active,
                  "region": branch.region_id, "services": [s.code for s in branch.services.all()]}
        for field in ("name", "address", "phone", "opening_hours"):
            if field in data:
                setattr(branch, field, str(data[field]).strip())
        if "latitude" in data:
            branch.latitude = coordinate_or_none(data["latitude"], "latitude")
        if "longitude" in data:
            branch.longitude = coordinate_or_none(data["longitude"], "longitude")
        if "is_active" in data:
            branch.is_active = as_bool(data["is_active"])
        if "region" in data:
            region = ServiceRegion.objects.filter(pk=data["region"]).first() if data["region"] else None
            branch.region = region
        branch.save()
        if "services" in data and isinstance(data["services"], list):
            branch.services.set(PlatformService.objects.filter(id__in=data["services"]))
        after = {"name": branch.name, "is_active": branch.is_active,
                 "region": branch.region_id, "services": [s.code for s in branch.services.all()]}
        record_audit(request.user, "branch.update", "branch", branch.id,
                     f"{branch.merchant.shop_name} · {branch.name}", before=before, after=after)
        return Response({"ok": True, **after})


class AdminStaffView(APIView):
    permission_classes = [IsAuthenticated]

    def _rows(self):
        rows = []
        for user in User.objects.filter(Q(role="admin") | Q(is_superuser=True)).order_by("id"):
            rows.append({
                "id": user.id,
                "username": user.username,
                "name": user.get_full_name() or user.username,
                "phone": user.phone,
                "admin_role": admin_role(user),
                "role_label": ADMIN_ROLE_LABELS.get(admin_role(user), admin_role(user)),
                "permissions": permissions_for(user),
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            })
        return rows

    def get(self, request):
        guard(request, "staff")
        return Response({"staff": self._rows(),
                         "roles": [{"code": code, "label": label} for code, label in User.ADMIN_ROLES],
                         "permission_roles": {key: sorted(value) for key, value in PERMISSION_ROLES.items()}})

    def post(self, request):
        guard(request, "staff")
        data = request.data
        identity = str(data.get("identity_number", "")).strip()
        first = str(data.get("first_name", "")).strip()
        phone = str(data.get("phone", "")).strip()
        role = str(data.get("admin_role", "")).strip()
        if not identity or not first or not phone:
            raise ValidationError("Identity number, first name and phone are required.")
        if role not in dict(User.ADMIN_ROLES):
            raise ValidationError({"admin_role": "Choose a valid admin role."})
        if User.objects.filter(Q(identity_number=identity) | Q(username=identity)).exists():
            raise ValidationError({"identity_number": "An account already exists for this identity number."})
        password = str(data.get("password", "")).strip()
        if password and len(password) < 8:
            raise ValidationError({"password": "Temporary password must contain at least 8 characters."})
        import secrets
        password = password or secrets.token_urlsafe(9)
        with transaction.atomic():
            user = User.objects.create_user(
                username=identity, password=password, first_name=first,
                last_name=str(data.get("last_name", "")).strip(), phone=phone,
                identity_number=identity, role="admin", admin_role=role,
                must_change_password=True,
            )
            record_audit(request.user, "staff.create", "admin_user", user.id,
                         f"Created admin staff {identity} ({role})", after={"admin_role": role})
        return Response({"id": user.id, "username": user.username, "temporary_password": password,
                         "admin_role": role}, status=201)

    def patch(self, request, user_id):
        guard(request, "staff")
        target = User.objects.filter(pk=user_id).filter(Q(role="admin") | Q(is_superuser=True)).first()
        if target is None:
            raise NotFound("Admin account not found.")
        if target.pk == request.user.pk:
            raise ValidationError("You cannot change your own admin role or status.")
        data = request.data
        before = {"admin_role": admin_role(target), "is_active": target.is_active}
        if "admin_role" in data:
            role = str(data["admin_role"]).strip()
            if role not in dict(User.ADMIN_ROLES):
                raise ValidationError({"admin_role": "Choose a valid admin role."})
            if target.is_superuser and role != "super_admin":
                raise ValidationError("A superuser account cannot be demoted here.")
            target.admin_role = role
        if "is_active" in data:
            target.is_active = as_bool(data["is_active"])
        target.save()
        record_audit(request.user, "staff.update", "admin_user", target.id,
                     f"Updated admin staff {target.username}", before=before,
                     after={"admin_role": admin_role(target), "is_active": target.is_active})
        return Response({"ok": True, "admin_role": admin_role(target), "is_active": target.is_active})


class AdminPlatformSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "settings")
        settings_row = PlatformSettings.load()
        return Response({
            "default_delivery_fee": str(settings_row.default_delivery_fee),
            "default_commission_percent": str(settings_row.default_commission_percent)
            if settings_row.default_commission_percent is not None else None,
            "commission_configured": settings_row.commission_configured,
            "currency": settings_row.currency,
            "support_email": settings_row.support_email,
            "updated_at": settings_row.updated_at.isoformat() if settings_row.updated_at else None,
        })

    def patch(self, request):
        guard(request, "settings")
        data = request.data
        settings_row = PlatformSettings.load()
        before = {"delivery_fee": str(settings_row.default_delivery_fee),
                  "commission": str(settings_row.default_commission_percent)
                  if settings_row.default_commission_percent is not None else None}
        if "default_delivery_fee" in data:
            value = decimal_or_none(data["default_delivery_fee"], "default_delivery_fee")
            settings_row.default_delivery_fee = value if value is not None else Decimal("0.00")
        if "default_commission_percent" in data:
            value = decimal_or_none(data["default_commission_percent"], "default_commission_percent")
            if value is not None and value > 100:
                raise ValidationError({"default_commission_percent": "A commission cannot exceed 100%."})
            settings_row.default_commission_percent = value
        for field in ("currency", "support_email"):
            if field in data:
                setattr(settings_row, field, str(data[field]).strip())
        settings_row.save()
        record_audit(request.user, "settings.update", "settings", 1, "Updated platform settings",
                     before=before, after={"delivery_fee": str(settings_row.default_delivery_fee),
                                           "commission": str(settings_row.default_commission_percent)
                                           if settings_row.default_commission_percent is not None else None})
        return self.get(request)


class BusinessCategoryListView(APIView):
    """Active business activities for merchant, admin and customer selectors."""

    permission_classes = [AllowAny]

    def get(self, request):
        rows = (BusinessCategory.objects.filter(is_active=True)
                .select_related("service").order_by("sort_order", "code"))
        return Response({"categories": [business_category_payload(row) for row in rows]})


class AdminBusinessCategoriesView(APIView):
    """Administrator-managed business activities and their service link."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "services")
        rows = (BusinessCategory.objects.select_related("service")
                .annotate(merchants_count=Count("merchants")).order_by("sort_order", "code"))
        return Response({
            "categories": [business_category_payload(row) for row in rows],
            "services": [
                {"id": service.id, "code": service.code, "name_ar": service.name_ar,
                 "name_en": service.name_en, "is_operational": service.is_operational}
                for service in PlatformService.objects.order_by("sort_order", "code")
            ],
            "requires_license": True,
        })

    def _service(self, data):
        raw = data.get("service") if "service" in data else data.get("service_id")
        if raw in (None, "", 0, "0"):
            return None
        service = PlatformService.objects.filter(pk=raw).first() if str(raw).isdigit() else None
        if service is None:
            raise ValidationError({"service": "Choose a valid platform service."})
        return service

    def post(self, request):
        guard(request, "services")
        data = request.data
        code = str(data.get("code", "")).strip().lower()
        if not CODE_RE.match(code):
            raise ValidationError({"code": "Use lowercase letters, numbers and underscores."})
        if BusinessCategory.objects.filter(code=code).exists():
            raise ValidationError({"code": "This activity code already exists."})
        name_ar = str(data.get("name_ar", "")).strip()
        name_en = str(data.get("name_en", "")).strip()
        if not name_ar or not name_en:
            raise ValidationError("Arabic and English names are required.")
        with transaction.atomic():
            category = BusinessCategory.objects.create(
                code=code,
                name_ar=name_ar[:80],
                name_en=name_en[:80],
                service=self._service(data),
                requires_license=as_bool(data.get("requires_license", False)),
                is_active=as_bool(data.get("is_active", True)),
                sort_order=small_int(data.get("sort_order")),
            )
            record_audit(request.user, "business_category.create", "business_category", category.id,
                         f"Created business activity {category.name_en}",
                         after={"code": category.code, "service": category.service_id})
        return Response(business_category_payload(category), status=201)


class AdminBusinessCategoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, category_id):
        guard(request, "services")
        with transaction.atomic():
            category = BusinessCategory.objects.select_for_update().select_related("service").filter(pk=category_id).first()
            if category is None:
                raise NotFound("Business activity not found.")
            before = {"name_ar": category.name_ar, "name_en": category.name_en,
                      "service": category.service_id, "is_active": category.is_active,
                      "requires_license": category.requires_license}
            data = request.data
            for field in ("name_ar", "name_en"):
                if field in data:
                    value = str(data[field]).strip()
                    if not value:
                        raise ValidationError({field: "This name is required."})
                    setattr(category, field, value[:80])
            if "service" in data or "service_id" in data:
                category.service = self.service_or_none(data)
            if "requires_license" in data:
                category.requires_license = as_bool(data["requires_license"])
            if "is_active" in data:
                category.is_active = as_bool(data["is_active"])
            if "sort_order" in data:
                category.sort_order = small_int(data["sort_order"])
            category.save()
            # Existing stores follow their activity's service when they had none.
            if category.service_id:
                for store in category.merchants.all():
                    if not store.services.exists():
                        store.services.add(category.service)
            record_audit(request.user, "business_category.update", "business_category", category.id,
                         f"Updated business activity {category.name_en}", before=before,
                         after={"name_ar": category.name_ar, "name_en": category.name_en,
                                "service": category.service_id, "is_active": category.is_active,
                                "requires_license": category.requires_license})
        return Response(business_category_payload(category))

    @staticmethod
    def service_or_none(data):
        raw = data.get("service") if "service" in data else data.get("service_id")
        if raw in (None, "", 0, "0"):
            return None
        service = PlatformService.objects.filter(pk=raw).first() if str(raw).isdigit() else None
        if service is None:
            raise ValidationError({"service": "Choose a valid platform service."})
        return service
