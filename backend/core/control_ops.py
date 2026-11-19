"""Admin operations, live map, analytics, finance, support and audit endpoints."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    MERCHANT_CATEGORY_SERVICE, AuditLog, CaptainProfile, CaptainServiceEligibility, CashSettlement, CashSettlementReceipt,
    DelayReport, InventoryMovement, MerchantBranch, MerchantProfile, Order, OrderActivity,
    PlatformService, PlatformSettings, Product, Rating, ServiceRegion, Subscription,
    SubscriptionPayment, SupportTicket, User,
)
from .services.admin_control import record_audit
from .control_views import guard

ACTIVE_STATUSES = ["new", "accepted", "preparing", "ready", "assigned", "picked_up", "delivering", "awaiting_confirmation"]
LATE_MINUTES = 60


def service_filter(service):
    """Match an order's service, including legacy store orders without one."""
    categories = [category for category, code in MERCHANT_CATEGORY_SERVICE.items() if code == service]
    # business_category is the real relation; the legacy category list keeps
    # historical orders (created before the link existed) visible.
    return (
        Q(service_type=service)
        | Q(merchant__business_category__service__code=service)
        | Q(merchant__services__code=service)
        | Q(merchant__category__in=categories)
    )


def order_row(order):
    region = order.branch.region if order.branch_id and order.branch.region_id else None
    return {
        "id": order.id,
        "order_number": order.order_number or order.ensure_order_number(),
        "status": order.status,
        "order_type": order.order_type,
        "service_type": order.resolved_service(),
        "customer": order.customer.username,
        "customer_name": order.customer.get_full_name() or order.customer.username,
        "merchant_id": order.merchant_id,
        "merchant": order.merchant.shop_name if order.merchant_id else None,
        "branch_id": order.branch_id,
        "branch": order.branch.name if order.branch_id else None,
        "region": {"code": region.code, "name_en": region.name_en, "name_ar": region.name_ar} if region else None,
        "captain_id": order.captain_id,
        "captain": order.captain.user.username if order.captain_id else None,
        "captain_name": (order.captain.user.get_full_name() or order.captain.user.username) if order.captain_id else None,
        "total": str(order.total),
        "subtotal": str(order.subtotal),
        "delivery_fee": str(order.delivery_fee),
        "payment_method": order.payment_method,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "pickup_address": order.pickup_address,
        "dropoff_address": order.dropoff_address,
        "pickup_latitude": float(order.pickup_latitude) if order.pickup_latitude is not None else None,
        "pickup_longitude": float(order.pickup_longitude) if order.pickup_longitude is not None else None,
        "dropoff_latitude": float(order.dropoff_latitude) if order.dropoff_latitude is not None else None,
        "dropoff_longitude": float(order.dropoff_longitude) if order.dropoff_longitude is not None else None,
        "captain_latitude": float(order.captain.current_latitude) if order.captain_id and order.captain.current_latitude is not None else None,
        "captain_longitude": float(order.captain.current_longitude) if order.captain_id and order.captain.current_longitude is not None else None,
        "captain_location_updated_at": order.captain.current_location_updated_at.isoformat()
        if order.captain_id and order.captain.current_location_updated_at else None,
        "cancellation_reason": order.cancellation_reason,
    }


class AdminOperationsCenterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "operations")
        params = request.query_params
        status = params.get("status") or "all"
        service = params.get("service") or ""
        region = params.get("region") or ""
        query = (params.get("q") or "").strip().lower()
        date_from = params.get("from") or ""
        date_to = params.get("to") or ""
        try:
            limit = min(max(int(params.get("limit") or 200), 1), 400)
        except (TypeError, ValueError):
            limit = 200

        now = timezone.now()
        base = Order.objects.select_related("customer", "merchant", "captain__user", "branch__region")
        filtered = base
        if service:
            filtered = filtered.filter(service_filter(service))
        if region:
            filtered = filtered.filter(branch__region__code=region)
        if query:
            filtered = filtered.filter(
                Q(order_number__icontains=query) | Q(customer__username__icontains=query)
                | Q(customer__first_name__icontains=query) | Q(merchant__shop_name__icontains=query)
                | Q(captain__user__username__icontains=query) | Q(dropoff_address__icontains=query)
            )
        if date_from:
            filtered = filtered.filter(created_at__date__gte=date_from)
        if date_to:
            filtered = filtered.filter(created_at__date__lte=date_to)

        if status == "active":
            filtered = filtered.filter(status__in=ACTIVE_STATUSES)
        elif status == "late":
            filtered = filtered.filter(status__in=ACTIVE_STATUSES, created_at__lt=now - timedelta(minutes=LATE_MINUTES))
        elif status == "needs_attention":
            filtered = filtered.filter(Q(supportticket__status="open") | Q(delay_reports__reviewed=False)).distinct()
        elif status in ACTIVE_STATUSES + ["completed", "cancelled"]:
            filtered = filtered.filter(status=status)

        counts = {
            "all": base.count(),
            "active": base.filter(status__in=ACTIVE_STATUSES).count(),
            "late": base.filter(status__in=ACTIVE_STATUSES, created_at__lt=now - timedelta(minutes=LATE_MINUTES)).count(),
            "needs_attention": base.filter(Q(supportticket__status="open") | Q(delay_reports__reviewed=False)).distinct().count(),
            "completed": base.filter(status="completed").count(),
            "cancelled": base.filter(status="cancelled").count(),
        }
        rows = [order_row(order) for order in filtered.order_by("-created_at")[:limit]]
        return Response({
            "orders": rows,
            "counts": counts,
            "services": list(PlatformService.objects.filter(is_active=True).values("code", "name_ar", "name_en")),
            "regions": list(ServiceRegion.objects.filter(is_active=True).values("code", "name_ar", "name_en")),
            "late_minutes": LATE_MINUTES,
        })


class AdminOrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        guard(request, "operations")
        order = (Order.objects.select_related("customer", "merchant", "captain__user", "branch__region")
                 .filter(pk=order_id).first())
        if order is None:
            raise NotFound("Order not found.")
        activities = [{
            "id": row.id,
            "event": row.event,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "actor": row.actor_name,
            "created_at": row.created_at.isoformat(),
        } for row in order.activities.all()[:200]]
        tickets = [{
            "id": ticket.id, "subject": ticket.subject, "status": ticket.status,
            "priority": ticket.priority, "category": ticket.category,
            "assigned_to": ticket.assigned_to.get_full_name() or ticket.assigned_to.username if ticket.assigned_to_id else None,
            "created_at": ticket.created_at.isoformat(),
        } for ticket in order.supportticket_set.all()[:50]]
        settlement = None
        if hasattr(order, "settlement"):
            row = order.settlement
            allocated = row.allocations.aggregate(value=Sum("amount"))["value"] or Decimal("0.00")
            settlement = {
                "id": row.id, "amount": str(row.amount), "allocated": str(allocated),
                "outstanding": str(max(row.amount - allocated, Decimal("0.00"))),
                "closed": row.closed, "reference": row.reference,
            }
        return Response({
            "order": order_row(order),
            "activities": activities,
            "tickets": tickets,
            "settlement": settlement,
            "proofs": [{"kind": proof.kind, "otp_verified": proof.otp_verified,
                        "captured_at": proof.captured_at.isoformat()} for proof in order.proofs.all()],
            "items": order.items,
            "distance_km": str(order.distance_km),
            "prep_minutes": order.prep_minutes,
        })


class AdminMapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "map")
        service = request.query_params.get("service") or ""
        region = request.query_params.get("region") or ""
        branches = MerchantBranch.objects.select_related("merchant", "region").filter(is_active=True)
        if region:
            branches = branches.filter(region__code=region)
        branch_rows = [{
            "id": b.id, "kind": "branch", "label": b.merchant.shop_name, "sublabel": b.name,
            "merchant_id": b.merchant_id, "is_open": b.merchant.is_open,
            "latitude": float(b.latitude) if b.latitude is not None else None,
            "longitude": float(b.longitude) if b.longitude is not None else None,
            "region": b.region.code if b.region_id else None,
            "services": [item.code for item in b.services.all()],
        } for b in branches]

        captains = CaptainProfile.objects.select_related("user").filter(
            Q(online=True) | Q(orders__status__in=ACTIVE_STATUSES)
        ).distinct()
        if service:
            approved_ids = CaptainServiceEligibility.objects.filter(service=service, status="approved").values_list("captain_id", flat=True)
            captains = captains.filter(id__in=approved_ids)
        captain_rows = [{
            "id": c.id, "kind": "captain", "label": c.user.get_full_name() or c.user.username,
            "sublabel": c.vehicle_type, "online": c.online, "rating": str(c.rating),
            "latitude": float(c.current_latitude) if c.current_latitude is not None else None,
            "longitude": float(c.current_longitude) if c.current_longitude is not None else None,
            "location_updated_at": c.current_location_updated_at.isoformat() if c.current_location_updated_at else None,
        } for c in captains]

        orders = Order.objects.select_related("merchant", "captain__user", "branch__region").filter(status__in=ACTIVE_STATUSES)
        if service:
            orders = orders.filter(service_filter(service))
        if region:
            orders = orders.filter(branch__region__code=region)
        order_rows = [{
            "id": o.id, "kind": "order", "label": o.order_number or o.ensure_order_number(),
            "sublabel": o.merchant.shop_name if o.merchant_id else o.order_type,
            "status": o.status, "service_type": o.resolved_service(),
            "pickup": [float(o.pickup_latitude), float(o.pickup_longitude)]
            if o.pickup_latitude is not None and o.pickup_longitude is not None else None,
            "dropoff": [float(o.dropoff_latitude), float(o.dropoff_longitude)]
            if o.dropoff_latitude is not None and o.dropoff_longitude is not None else None,
        } for o in orders[:300]]

        regions = [{
            "code": r.code, "name_ar": r.name_ar, "name_en": r.name_en,
            "latitude": float(r.center_latitude) if r.center_latitude is not None else None,
            "longitude": float(r.center_longitude) if r.center_longitude is not None else None,
            "radius_km": r.radius_km,
        } for r in ServiceRegion.objects.filter(is_active=True)]
        return Response({
            "branches": branch_rows,
            "captains": captain_rows,
            "orders": order_rows,
            "regions": regions,
            "services": list(PlatformService.objects.filter(is_active=True).values("code", "name_ar", "name_en")),
            "server_time": timezone.now().isoformat(),
        })


class AdminAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "analytics")
        try:
            days = min(max(int(request.query_params.get("days") or 30), 1), 365)
        except (TypeError, ValueError):
            days = 30
        start = timezone.now() - timedelta(days=days)
        orders = Order.objects.filter(created_at__gte=start)
        completed = orders.filter(status="completed")

        totals = completed.aggregate(
            sales=Sum("total"), products=Sum("subtotal"), delivery=Sum("delivery_fee"),
        )
        sales = totals["sales"] or Decimal("0.00")
        products = totals["products"] or Decimal("0.00")
        delivery = totals["delivery"] or Decimal("0.00")
        cancelled = orders.filter(status="cancelled").count()
        total_count = orders.count()

        settings_row = PlatformSettings.load()
        commission = None
        if settings_row.commission_configured:
            commission = (sales * settings_row.default_commission_percent / Decimal("100")).quantize(Decimal("0.01"))

        by_status = list(orders.values("status").annotate(total=Count("id")).order_by("-total"))
        by_service = list(
            orders.values("service_type").annotate(
                total=Count("id"),
                revenue=Sum("total", filter=Q(status="completed")),
                cancelled=Count("id", filter=Q(status="cancelled")),
            ).order_by("-total")
        )
        by_region = list(
            orders.values("branch__region__code", "branch__region__name_ar", "branch__region__name_en")
            .annotate(total=Count("id"), revenue=Sum("total", filter=Q(status="completed")))
            .order_by("-total")
        )
        daily = {}
        for row in orders.values("created_at__date").annotate(total=Count("id"), revenue=Sum("total", filter=Q(status="completed"))):
            daily[row["created_at__date"].isoformat()] = row
        series = []
        for offset in range(days - 1, -1, -1):
            day = (timezone.localdate() - timedelta(days=offset)).isoformat()
            bucket = daily.get(day)
            series.append({"date": day, "orders": bucket["total"] if bucket else 0,
                           "revenue": str(bucket["revenue"] or 0) if bucket else "0"})

        durations = [
            (row[1] - row[0]).total_seconds() / 60
            for row in completed.filter(completed_at__isnull=False)
            .values_list("created_at", "completed_at")[:1000] if row[1] and row[0]
        ]

        settlements = CashSettlement.objects.filter(order__status="completed")
        settlement_total = settlements.aggregate(value=Sum("amount"))["value"] or Decimal("0.00")
        allocated_total = CashSettlementReceipt.objects.aggregate(value=Sum("allocations__amount"))["value"] or Decimal("0.00")
        receipt_total = CashSettlementReceipt.objects.aggregate(value=Sum("amount"))["value"] or Decimal("0.00")

        return Response({
            "range_days": days,
            "start": start.isoformat(),
            "orders": {
                "total": total_count,
                "active": Order.objects.filter(status__in=ACTIVE_STATUSES).count(),
                "completed": completed.count(),
                "cancelled": cancelled,
                "today": Order.objects.filter(created_at__date=timezone.localdate()).count(),
                "week": Order.objects.filter(created_at__gte=timezone.now() - timedelta(days=7)).count(),
                "month": Order.objects.filter(created_at__gte=timezone.now() - timedelta(days=30)).count(),
                "cancellation_rate": round(cancelled / total_count * 100, 1) if total_count else 0,
                "average_completion_minutes": round(sum(durations) / len(durations), 1) if durations else None,
            },
            "money": {
                "sales": str(sales),
                "product_revenue": str(products),
                "delivery_revenue": str(delivery),
                "captain_earnings": str(delivery),
                "commission": str(commission) if commission is not None else None,
                "commission_configured": settings_row.commission_configured,
                "merchant_settlements": str(settlement_total),
                "settlements_allocated": str(allocated_total),
                "settlements_outstanding": str(max(settlement_total - allocated_total, Decimal("0.00"))),
                "cash_receipts": str(receipt_total),
                "currency": settings_row.currency,
            },
            "people": {
                "customers": Order.objects.values("customer_id").distinct().count(),
                "merchants": MerchantProfile.objects.count(),
                "approved_merchants": MerchantProfile.objects.filter(approval_status="approved").count(),
                "branches": MerchantBranch.objects.filter(is_active=True).count(),
                "captains": CaptainProfile.objects.count(),
                "captains_online": CaptainProfile.objects.filter(online=True).count(),
                "pending_merchants": MerchantProfile.objects.filter(approval_status="pending").count(),
                "pending_captains": CaptainProfile.objects.filter(approved=False, rejected=False).count(),
            },
            "by_status": by_status,
            "by_service": by_service,
            "by_region": by_region,
            "series": series,
        })


class AdminFinanceCenterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "finance")
        today = timezone.localdate()
        completed = Order.objects.filter(status="completed")
        sums = completed.aggregate(sales=Sum("total"), products=Sum("subtotal"), delivery=Sum("delivery_fee"))
        settlements = CashSettlement.objects.select_related("order", "merchant", "captain__user").order_by("-created_at")
        settlement_rows = []
        for row in settlements[:80]:
            allocated = row.allocations.aggregate(value=Sum("amount"))["value"] or Decimal("0.00")
            settlement_rows.append({
                "id": row.id,
                "order_number": row.order.order_number,
                "merchant": row.merchant.shop_name,
                "captain": row.captain.user.get_full_name() or row.captain.user.username,
                "amount": str(row.amount),
                "allocated": str(allocated),
                "outstanding": str(max(row.amount - allocated, Decimal("0.00"))),
                "closed": row.closed,
                "created_at": row.created_at.isoformat(),
            })
        receipts = [{
            "id": row.id,
            "captain": row.captain.user.get_full_name() or row.captain.user.username,
            "recorded_by": row.recorded_by.get_full_name() or row.recorded_by.username,
            "amount": str(row.amount),
            "reference": row.reference,
            "created_at": row.created_at.isoformat(),
        } for row in CashSettlementReceipt.objects.select_related("captain__user", "recorded_by")[:80]]
        payments = [{
            "id": row.id,
            "subscription_id": row.subscription_id,
            "user": row.subscription.user.username,
            "amount": str(row.amount),
            "method": row.method,
            "created_at": row.paid_at.isoformat(),
        } for row in SubscriptionPayment.objects.select_related("subscription__user")[:80]]
        balances = 0
        for sub in Subscription.objects.filter(status__in=["active", "pending"]).prefetch_related("payments"):
            paid = sum((payment.amount for payment in sub.payments.all()), Decimal("0.00"))
            balances += max(sub.amount * sub.months - paid, Decimal("0.00"))
        settings_row = PlatformSettings.load()
        commission = None
        if settings_row.commission_configured:
            commission = (sums["sales"] or Decimal("0.00")) * settings_row.default_commission_percent / Decimal("100")
        return Response({
            "sales": str(sums["sales"] or Decimal("0.00")),
            "product_revenue": str(sums["products"] or Decimal("0.00")),
            "delivery_revenue": str(sums["delivery"] or Decimal("0.00")),
            "captain_earnings": str(sums["delivery"] or Decimal("0.00")),
            "commission": str(commission.quantize(Decimal("0.01"))) if commission is not None else None,
            "commission_configured": settings_row.commission_configured,
            "subscription_outstanding": str(balances),
            "open_settlements": settlements.filter(closed=False).count(),
            "payment_methods": list(Order.objects.values("payment_method").annotate(
                total=Count("id"), amount=Sum("total", filter=Q(status="completed"))
            )),
            "settlements": settlement_rows,
            "receipts": receipts,
            "subscription_payments": payments,
            "currency": settings_row.currency,
            "as_of": today.isoformat(),
        })


class AdminSupportCenterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "support")
        params = request.query_params
        status = params.get("status") or ""
        priority = params.get("priority") or ""
        category = params.get("category") or ""
        assigned = params.get("assigned") or ""
        tickets = SupportTicket.objects.select_related("user", "order", "assigned_to").order_by("-created_at")
        if status in dict(SupportTicket.STATUSES):
            tickets = tickets.filter(status=status)
        if priority in dict(SupportTicket.PRIORITIES):
            tickets = tickets.filter(priority=priority)
        if category in dict(SupportTicket.CATEGORIES):
            tickets = tickets.filter(category=category)
        if assigned == "me":
            tickets = tickets.filter(assigned_to=request.user)
        elif assigned == "unassigned":
            tickets = tickets.filter(assigned_to__isnull=True)
        rows = [{
            "id": ticket.id,
            "subject": ticket.subject,
            "message": ticket.message,
            "status": ticket.status,
            "priority": ticket.priority,
            "category": ticket.category,
            "resolution": ticket.resolution,
            "user": ticket.user.username,
            "user_name": ticket.user.get_full_name() or ticket.user.username,
            "order_id": ticket.order_id,
            "order_number": ticket.order.ensure_order_number() if ticket.order_id else None,
            "assigned_to": ticket.assigned_to_id,
            "assigned_name": (ticket.assigned_to.get_full_name() or ticket.assigned_to.username) if ticket.assigned_to_id else None,
            "created_at": ticket.created_at.isoformat(),
            "updated_at": ticket.updated_at.isoformat(),
        } for ticket in tickets[:300]]
        ratings = list(Rating.objects.values("target_type").annotate(total=Count("id"), average=Avg("score")))
        recent_ratings = [{
            "id": row.id, "target_type": row.target_type, "score": row.score,
            "comment": row.comment, "created_at": row.created_at.isoformat(),
            "order_number": row.order.ensure_order_number(),
        } for row in Rating.objects.select_related("order").order_by("-created_at")[:30]]
        return Response({
            "tickets": rows,
            "counts": {
                "open": SupportTicket.objects.filter(status="open").count(),
                "in_review": SupportTicket.objects.filter(status="in_review").count(),
                "resolved": SupportTicket.objects.filter(status="resolved").count(),
            },
            "categories": [{"code": code, "label": label} for code, label in SupportTicket.CATEGORIES],
            "priorities": [{"code": code, "label": label} for code, label in SupportTicket.PRIORITIES],
            "agents": list(User.objects.filter(Q(role="admin") | Q(is_superuser=True)).values("id", "username", "first_name", "last_name")),
            "ratings": ratings,
            "recent_ratings": recent_ratings,
        })

    def patch(self, request, ticket_id):
        guard(request, "support")
        ticket = SupportTicket.objects.filter(pk=ticket_id).first()
        if ticket is None:
            raise NotFound("Ticket not found.")
        data = request.data
        before = {"status": ticket.status, "priority": ticket.priority,
                  "category": ticket.category, "assigned_to": ticket.assigned_to_id}
        if "status" in data:
            status = str(data["status"]).strip()
            if status not in dict(SupportTicket.STATUSES):
                raise ValidationError({"status": "Choose open, in_review or resolved."})
            if status == "resolved" and not str(data.get("resolution", ticket.resolution)).strip():
                raise ValidationError({"resolution": "Record the resolution before closing the ticket."})
            ticket.status = status
        for field, choices in (("priority", SupportTicket.PRIORITIES), ("category", SupportTicket.CATEGORIES)):
            if field in data and str(data[field]) in dict(choices):
                setattr(ticket, field, str(data[field]))
        if "resolution" in data:
            ticket.resolution = str(data["resolution"]).strip()
        if "assigned_to" in data:
            agent_id = data["assigned_to"]
            agent = User.objects.filter(pk=agent_id).filter(Q(role="admin") | Q(is_superuser=True)).first() if agent_id else None
            ticket.assigned_to = agent
        ticket.save()
        record_audit(request.user, "support.update", "support_ticket", ticket.id,
                     f"Ticket #{ticket.id}: {ticket.status}", before=before,
                     after={"status": ticket.status, "priority": ticket.priority,
                            "category": ticket.category, "assigned_to": ticket.assigned_to_id})
        return Response({"ok": True, "id": ticket.id, "status": ticket.status})


class AdminAuditLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "audit")
        params = request.query_params
        rows = AuditLog.objects.select_related("actor").all()
        query = (params.get("q") or "").strip()
        action = params.get("action") or ""
        target_type = params.get("target_type") or ""
        if query:
            rows = rows.filter(Q(summary__icontains=query) | Q(actor_name__icontains=query) | Q(target_id=query))
        if action:
            rows = rows.filter(action=action)
        if target_type:
            rows = rows.filter(target_type=target_type)
        return Response({
            "entries": [{
                "id": row.id,
                "actor": row.actor_name,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "summary": row.summary,
                "before": row.before,
                "after": row.after,
                "created_at": row.created_at.isoformat(),
            } for row in rows[:300]],
            "actions": list(AuditLog.objects.values_list("action", flat=True).distinct().order_by("action")),
            "target_types": list(AuditLog.objects.values_list("target_type", flat=True).distinct().order_by("target_type")),
        })


class AdminAlertsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        guard(request, "notifications")
        now = timezone.now()
        late = Order.objects.filter(status__in=ACTIVE_STATUSES, created_at__lt=now - timedelta(minutes=LATE_MINUTES))
        low_stock = Product.objects.filter(
            available=True, quantity__isnull=False, quantity__lte=F("low_stock_threshold")
        ).select_related("merchant")
        pending_merchants = MerchantProfile.objects.filter(approval_status="pending").select_related("user")
        pending_captains = CaptainProfile.objects.filter(approved=False, rejected=False).select_related("user")
        open_tickets = SupportTicket.objects.filter(status="open")
        pending_settlements = CashSettlement.objects.filter(closed=False)
        unreviewed_delays = DelayReport.objects.filter(reviewed=False).select_related("order", "captain__user")

        alerts = [
            {
                "kind": "merchant_application",
                "severity": "warning" if pending_merchants.count() else "info",
                "count": pending_merchants.count(),
                "samples": [{"id": m.id, "label": m.shop_name} for m in pending_merchants[:5]],
            },
            {
                "kind": "captain_application",
                "severity": "warning" if pending_captains.count() else "info",
                "count": pending_captains.count(),
                "samples": [{"id": c.id, "label": c.user.get_full_name() or c.user.username} for c in pending_captains[:5]],
            },
            {
                "kind": "late_order",
                "severity": "danger" if late.count() else "info",
                "count": late.count(),
                "samples": [{"id": o.id, "label": o.ensure_order_number()} for o in late.order_by("created_at")[:5]],
            },
            {
                "kind": "low_stock",
                "severity": "warning" if low_stock.count() else "info",
                "count": low_stock.count(),
                "samples": [{"id": p.id, "label": f"{p.merchant.shop_name} · {p.name}"} for p in low_stock[:5]],
            },
            {
                "kind": "open_ticket",
                "severity": "warning" if open_tickets.count() else "info",
                "count": open_tickets.count(),
                "samples": [{"id": t.id, "label": t.subject} for t in open_tickets.order_by("-created_at")[:5]],
            },
            {
                "kind": "pending_settlement",
                "severity": "warning" if pending_settlements.count() else "info",
                "count": pending_settlements.count(),
                "samples": [{"id": s.id, "label": s.order.ensure_order_number()} for s in pending_settlements[:5]],
            },
            {
                "kind": "delivery_issue",
                "severity": "warning" if unreviewed_delays.count() else "info",
                "count": unreviewed_delays.count(),
                "samples": [{"id": r.order_id, "label": r.order.ensure_order_number()} for r in unreviewed_delays[:5]],
            },
        ]
        return Response({"alerts": alerts, "generated_at": now.isoformat()})
