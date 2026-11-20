"""Merchant management system endpoints.

Every view resolves the caller through ``merchant_access`` so staff only see
their own store and only the actions their role permits.  Store data is never
filtered by a client-supplied merchant id.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    CashSettlement, MerchantBranch, MerchantHours, MerchantStaff, Order, PriceChange,
    Product, StoreClosure,
)
from .serializers import (
    InventoryMovementSerializer, MerchantBranchSerializer, MerchantHoursSerializer,
    MerchantStaffSerializer, PriceChangeSerializer, StoreClosureSerializer,
)
from .services.merchant_access import PERMISSION_LABELS, ROLE_PERMISSIONS, merchant_access


def merchant_or_403(user, permission=None):
    access = merchant_access(user)
    if access is None:
        raise PermissionDenied("Merchant account required.")
    if permission and not access.can(permission):
        raise PermissionDenied("Your staff role does not allow this action.")
    return access


def settlement_rows(merchant):
    rows = []
    settlements = CashSettlement.objects.filter(
        merchant=merchant, order__status="completed", order__payment_method="cash",
        order__order_type="store",
    ).select_related("captain__user", "order").prefetch_related("allocations").order_by("-created_at")
    for settlement in settlements:
        allocated = sum((row.amount for row in settlement.allocations.all()), Decimal("0.00"))
        settled = min(settlement.amount, max(allocated, settlement.amount if settlement.closed else Decimal("0.00")))
        rows.append({
            "id": settlement.id, "order_number": settlement.order.ensure_order_number(),
            "captain_name": settlement.captain.user.get_full_name() or settlement.captain.user.username,
            "amount": str(settlement.amount), "settled_amount": str(settled),
            "outstanding_amount": str(max(settlement.amount - settled, Decimal("0.00"))),
            "status": "settled" if settled >= settlement.amount else "partial" if settled > 0 else "outstanding",
            "created_at": settlement.created_at.isoformat(),
        })
    return rows


class MerchantDashboardView(APIView):
    """Every figure is computed from the merchant's own orders and products."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = merchant_or_403(request.user)
        merchant = access.merchant
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        orders = Order.objects.filter(merchant=merchant)
        status_counts = {
            row["status"]: row["count"]
            for row in orders.values("status").annotate(count=models.Count("id"))
        }

        def sales(start):
            rows = orders.filter(
                status="completed", completed_at__date__gte=start, completed_at__date__lte=today
            )
            return {
                "orders": rows.count(),
                "gross": str(rows.aggregate(value=models.Sum("total"))["value"] or Decimal("0.00")),
                "products": str(rows.aggregate(value=models.Sum("subtotal"))["value"] or Decimal("0.00")),
                "delivery": str(rows.aggregate(value=models.Sum("delivery_fee"))["value"] or Decimal("0.00")),
            }

        products = Product.objects.filter(merchant=merchant)
        low_stock = products.filter(
            quantity__isnull=False, quantity__gt=0, quantity__lte=models.F("low_stock_threshold")
        )
        out_of_stock = products.filter(quantity__isnull=False, quantity__lte=0)
        settled = settlement_rows(merchant)
        due = sum((Decimal(row["outstanding_amount"]) for row in settled), Decimal("0.00"))
        alerts = []
        for product in low_stock.order_by("quantity")[:5]:
            alerts.append({"type": "stock.low", "product_id": product.id, "name": product.name, "quantity": product.quantity})
        for product in out_of_stock[:5]:
            alerts.append({"type": "stock.out", "product_id": product.id, "name": product.name, "quantity": product.quantity})
        if merchant.temporarily_closed:
            alerts.append({"type": "store.paused", "message": "The store is paused for new orders."})
        return Response({
            "store": {
                "id": merchant.id, "shop_name": merchant.shop_name, "category": merchant.category,
                "service_type": merchant.service_type, "is_open": merchant.is_open,
                "temporarily_closed": merchant.temporarily_closed,
                "accepts_orders": merchant.accepts_orders, "prep_minutes": merchant.prep_minutes,
                "rating": str(merchant.rating),
            },
            "role": access.role, "permissions": sorted(access.permissions),
            "orders": {
                "new": status_counts.get("new", 0), "accepted": status_counts.get("accepted", 0),
                "preparing": status_counts.get("preparing", 0), "ready": status_counts.get("ready", 0),
                "assigned": status_counts.get("assigned", 0), "picked_up": status_counts.get("picked_up", 0),
                "delivering": status_counts.get("delivering", 0),
                "awaiting_confirmation": status_counts.get("awaiting_confirmation", 0),
                "completed": status_counts.get("completed", 0), "cancelled": status_counts.get("cancelled", 0),
            },
            "sales": {"today": sales(today), "week": sales(week_start), "month": sales(month_start)},
            "products": {
                "active": products.filter(available=True).count(), "total": products.count(),
                "low_stock": low_stock.count(), "out_of_stock": out_of_stock.count(),
            },
            "settlements": {"outstanding": str(due), "rows": settled[:50]},
            "alerts": alerts,
        })


class MerchantAnalyticsView(APIView):
    """Product and order analytics for owners, managers and report staff."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = merchant_or_403(request.user, "reports")
        merchant = access.merchant
        since = timezone.now() - timedelta(days=90)
        orders = Order.objects.filter(merchant=merchant).select_related("captain__user")
        completed = orders.filter(status="completed", completed_at__gte=since)
        totals = {}
        for order in completed.only("items"):
            for row in order.items or []:
                key = str(row.get("name") or row.get("product_id"))
                entry = totals.setdefault(key, {"name": key, "quantity": 0, "revenue": Decimal("0.00")})
                entry["quantity"] += int(row.get("quantity") or 0)
                try:
                    entry["revenue"] += Decimal(str(row.get("line_total") or 0))
                except InvalidOperation:
                    pass
        ranked = sorted(totals.values(), key=lambda row: row["quantity"], reverse=True)
        products = Product.objects.filter(merchant=merchant)
        inventory = [{
            "id": product.id, "name": product.name, "quantity": product.quantity,
            "low_stock_threshold": product.low_stock_threshold, "stock_status": product.stock_status,
            "price": str(product.price), "effective_price": str(product.effective_price),
        } for product in products.order_by("quantity", "name")]
        cancelled = [{
            "id": order.id, "order_number": order.ensure_order_number(),
            "reason": order.cancellation_reason, "total": str(order.total),
            "created_at": order.created_at.isoformat(),
            "customer": order.customer.get_full_name() or order.customer.username,
        } for order in orders.filter(status="cancelled").order_by("-created_at")[:100]]
        monthly = []
        today = timezone.localdate()
        for offset in range(5, -1, -1):
            month = (today.replace(day=1) - timedelta(days=offset * 28)).replace(day=1)
            next_month = (month + timedelta(days=32)).replace(day=1)
            rows = orders.filter(
                status="completed", completed_at__date__gte=month, completed_at__date__lt=next_month
            )
            monthly.append({
                "month": month.isoformat()[:7],
                "orders": rows.count(),
                "gross": str(rows.aggregate(value=models.Sum("total"))["value"] or Decimal("0.00")),
                "products": str(rows.aggregate(value=models.Sum("subtotal"))["value"] or Decimal("0.00")),
            })
        settled = settlement_rows(merchant)
        return Response({
            "top_products": [
                {"name": row["name"], "quantity": row["quantity"], "revenue": str(row["revenue"])}
                for row in ranked[:10]
            ],
            "slow_products": [
                {"name": row["name"], "quantity": row["quantity"], "revenue": str(row["revenue"])}
                for row in ranked[-10:]
            ][::-1],
            "inventory": inventory,
            "cancelled_orders": cancelled,
            "monthly": monthly,
            "settlements": settled[:100],
            "outstanding_total": str(sum((Decimal(row["outstanding_amount"]) for row in settled), Decimal("0.00"))),
            "fee_note": "Sales value, product revenue and delivery fees are reported separately; no commission rule is configured.",
        })


class MerchantBranchesView(APIView):
    """Branches of the authenticated merchant; another store's branch is invisible."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = merchant_or_403(request.user)
        branches = access.merchant.branches.all()
        return Response(MerchantBranchSerializer(branches, many=True).data)

    def post(self, request):
        access = merchant_or_403(request.user, "staff")
        serializer = MerchantBranchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = serializer.save(merchant=access.merchant)
        return Response(MerchantBranchSerializer(branch).data, status=201)


class MerchantBranchDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _branch(self, request, permission, branch_id):
        access = merchant_or_403(request.user, permission)
        branch = access.merchant.branches.filter(pk=branch_id).first()
        if branch is None:
            raise NotFound("Branch not found.")
        return branch

    def patch(self, request, branch_id):
        branch = self._branch(request, "staff", branch_id)
        serializer = MerchantBranchSerializer(branch, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, branch_id):
        branch = self._branch(request, "staff", branch_id)
        if branch.orders.exists():
            raise ValidationError({"detail": "This branch has orders; deactivate it instead of deleting it."})
        branch.delete()
        return Response(status=204)


class MerchantStaffView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = merchant_or_403(request.user)
        rows = access.merchant.staff.select_related("user").all()
        return Response({
            "staff": MerchantStaffSerializer(rows, many=True).data,
            "roles": [{"role": code, "label": label, "permissions": sorted(ROLE_PERMISSIONS.get(code, set()))}
                      for code, label in MerchantStaff.ROLES],
            "permissions": PERMISSION_LABELS,
            "can_manage": access.can("staff"),
        })

    def post(self, request):
        access = merchant_or_403(request.user, "staff")
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        role = str(request.data.get("role", "orders")).strip()
        first_name = str(request.data.get("first_name", "")).strip()
        phone = str(request.data.get("phone", "")).strip()
        if role not in dict(MerchantStaff.ROLES):
            raise ValidationError({"role": "Choose a valid staff role."})
        if not username or len(username) < 3:
            raise ValidationError({"username": "Enter a login username of at least 3 characters."})
        if len(password) < 8:
            raise ValidationError({"password": "Use a password of at least 8 characters."})
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError({"username": "This username is already in use."})
        if not first_name:
            raise ValidationError({"first_name": "Enter the staff member's name."})
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, password=password, first_name=first_name,
                last_name=str(request.data.get("last_name", "")).strip(),
                phone=phone, role="merchant", subscription_required=False,
                must_change_password=True,
            )
            staff = MerchantStaff.objects.create(
                merchant=access.merchant, user=user, role=role, created_by=request.user,
            )
        return Response(MerchantStaffSerializer(staff).data, status=201)


class MerchantStaffDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _staff(self, request, staff_id):
        access = merchant_or_403(request.user, "staff")
        staff = access.merchant.staff.select_related("user").filter(pk=staff_id).first()
        if staff is None:
            raise NotFound("Staff member not found.")
        return staff

    def patch(self, request, staff_id):
        staff = self._staff(request, staff_id)
        if "role" in request.data:
            role = str(request.data["role"]).strip()
            if role not in dict(MerchantStaff.ROLES):
                raise ValidationError({"role": "Choose a valid staff role."})
            staff.role = role
        if "is_active" in request.data:
            staff.is_active = str(request.data["is_active"]).lower() in ("1", "true", "yes", "on")
            staff.user.is_active = staff.is_active
            staff.user.save(update_fields=["is_active"])
        staff.save()
        return Response(MerchantStaffSerializer(staff).data)

    def delete(self, request, staff_id):
        staff = self._staff(request, staff_id)
        staff.user.is_active = False
        staff.user.save(update_fields=["is_active"])
        staff.delete()
        return Response(status=204)


class MerchantHoursView(APIView):
    """Weekly opening hours; a closed day blocks new orders."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = merchant_or_403(request.user)
        scope = access.merchant.business_hours.select_related("branch").all()
        branch_id = request.query_params.get("branch")
        if branch_id:
            scope = scope.filter(branch_id=branch_id)
        return Response({
            "hours": MerchantHoursSerializer(scope, many=True).data,
            "closures": StoreClosureSerializer(
                access.merchant.closures.order_by("date")[:60], many=True
            ).data,
        })

    def put(self, request):
        access = merchant_or_403(request.user, "staff")
        rows = request.data.get("hours")
        if not isinstance(rows, list) or len(rows) > 21:
            raise ValidationError({"hours": "Send at most 21 weekly rows."})
        branch_id = request.data.get("branch")
        if branch_id is not None:
            if not access.merchant.branches.filter(pk=branch_id).exists():
                raise NotFound("Branch not found.")
        serializer = MerchantHoursSerializer(data=rows, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            MerchantHours.objects.filter(
                merchant=access.merchant, branch_id=branch_id,
            ).delete()
            objects = []
            for item in serializer.validated_data:
                objects.append(MerchantHours(
                    merchant=access.merchant, branch_id=branch_id,
                    weekday=item["weekday"],
                    opens_at=item.get("opens_at"),
                    closes_at=item.get("closes_at"),
                    is_closed=item.get("is_closed", False),
                ))
            MerchantHours.objects.bulk_create(objects)
        return self.get(request)


class MerchantClosuresView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        access = merchant_or_403(request.user, "staff")
        serializer = StoreClosureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = serializer.validated_data.get("branch")
        if branch is not None and branch.merchant_id != access.merchant.id:
            raise PermissionDenied("This branch belongs to another store.")
        existing = StoreClosure.objects.filter(
            merchant=access.merchant,
            branch=branch,
            date=serializer.validated_data["date"],
        ).first()
        if existing is not None:
            return Response(StoreClosureSerializer(existing).data, status=200)
        closure = StoreClosure.objects.create(
            merchant=access.merchant,
            branch=branch,
            date=serializer.validated_data["date"],
            reason=serializer.validated_data.get("reason", "")[:200],
        )
        return Response(StoreClosureSerializer(closure).data, status=201)

    def delete(self, request):
        access = merchant_or_403(request.user, "staff")
        closure_id = request.query_params.get("id")
        closure = access.merchant.closures.filter(pk=closure_id).first()
        if closure is None:
            raise NotFound("Closure not found.")
        closure.delete()
        return Response(status=204)


class MerchantStoreStatusView(APIView):
    """Pause new orders, reopen, and set the default preparation time."""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        access = merchant_or_403(request.user, "staff")
        merchant = access.merchant
        if "temporarily_closed" in request.data:
            merchant.temporarily_closed = str(request.data["temporarily_closed"]).lower() in ("1", "true", "yes", "on")
        if "is_open" in request.data:
            merchant.is_open = str(request.data["is_open"]).lower() in ("1", "true", "yes", "on")
        if "prep_minutes" in request.data:
            try:
                minutes = int(request.data["prep_minutes"])
            except (TypeError, ValueError):
                raise ValidationError({"prep_minutes": "Enter whole minutes."})
            if not 5 <= minutes <= 120:
                raise ValidationError({"prep_minutes": "Choose between 5 and 120 minutes."})
            merchant.prep_minutes = minutes
        merchant.save()
        return Response({
            "is_open": merchant.is_open, "temporarily_closed": merchant.temporarily_closed,
            "accepts_orders": merchant.accepts_orders, "prep_minutes": merchant.prep_minutes,
        })


class MerchantPriceHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = merchant_or_403(request.user, "prices")
        rows = PriceChange.objects.filter(product__merchant=access.merchant).select_related(
            "product", "changed_by"
        )[:200]
        return Response(PriceChangeSerializer(rows, many=True).data)


class MerchantInventoryLedgerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        access = merchant_or_403(request.user)
        from .models import InventoryMovement
        qs = InventoryMovement.objects.select_related("product", "order", "actor").filter(
            product__merchant=access.merchant
        )
        product_id = request.query_params.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)
        reason = request.query_params.get("reason")
        if reason:
            qs = qs.filter(reason=reason)
        return Response(InventoryMovementSerializer(qs[:300], many=True).data)
