import uuid
import os
import posixpath
import secrets
import calendar
import math
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import connection, transaction
from django.db.models import Avg, Sum, Q, F
from django.http import FileResponse
from django.utils import timezone
from rest_framework import generics, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from .models import *
from .serializers import *
from .services.eligibility import (
    subscription_state, classify_subscription, evaluate_captain, legacy_fields, enforce_online_invariant,
    eligible_captain_user_ids, order_compatibility_reasons, set_approval, APPROVAL_STATUSES,
    approval_status, active_task_count, service_eligibility, is_within_working_hours,
)
from .validators import validate_document_upload, validate_image_upload
from .services.order_completion import complete_order
from .services.order_activity import record_order_activity
from .services.merchant_access import ALL_PERMISSIONS, PERMISSION_LABELS, merchant_access, require_merchant
from .services.inventory import record_movement
from .services.proofs import proof_policy, proof_complete
from .services.admin_control import has_permission
from .storage import WaselniMediaStorage, is_captain_document, is_private_document


def as_bool(value):
    """JSON booleans pass through; form strings such as "false" are not truthy."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def require_admin_permission(request, permission):
    """Backend gate for every admin-only endpoint; the React tabs are cosmetic."""
    if not has_permission(request.user, permission):
        raise PermissionDenied("Your admin role does not allow this action.")


def publish_order_event(order, event="order.updated"):
    """Send a small event; clients fetch authorized order data through REST."""
    layer = get_channel_layer()
    if not layer:
        return
    payload = {
        "type": event, "order_id": order.id, "order_number": order.order_number,
        "status": order.status, "updated_at": order.updated_at.isoformat(),
    }
    groups = {"role_admin"}
    if order.customer_id:
        groups.add(f"user_{order.customer_id}")
    if order.merchant_id and order.merchant:
        groups.add(f"user_{order.merchant.user_id}")
    if order.captain_id and order.captain:
        groups.add(f"user_{order.captain.user_id}")
    # Captains are targeted individually, and only if the shared eligibility
    # service says they may receive this order right now.
    dispatchable = not order.captain_id and (
        (order.order_type == "ride" and order.status == "new") or
        (order.order_type != "ride" and order.status == "ready"))
    if dispatchable:
        captain_ids = eligible_captain_user_ids(order)
    elif order.status in ("assigned", "cancelled"):
        captain_ids = eligible_captain_user_ids()  # refresh stale available-order lists
    else:
        captain_ids = []
    groups.update(f"user_{uid}" for uid in captain_ids)
    for group in groups:
        async_to_sync(layer.group_send)(group, {"type": "order_event", "payload": payload})


def publish_stock_events(before, after, reason, order=None):
    """Push the exact post-change count to the merchant and admins.

    Screens apply this value immediately and then refetch through REST, so a
    sale never leaves a stale number waiting for the next poll. The payload
    carries the committed quantity, not a client-side guess.
    """
    layer = get_channel_layer()
    if not layer:
        return
    for product in after:
        if product.quantity is None:
            continue
        merchant_user = getattr(product.merchant, "user_id", None)
        if not merchant_user:
            continue
        previous = before.get(product.id)
        payload = {
            "type": "stock.updated",
            "product_id": product.id,
            "name": product.name,
            "quantity": product.quantity,
            "previous": previous if previous is not None else 0,
            "delta": product.quantity - (previous if previous is not None else 0),
            "stock_status": product.stock_status,
            "reason": reason,
            "order_id": order.id if order is not None else None,
            "order_number": order.order_number if order is not None else None,
        }
        for group in {f"user_{merchant_user}", "role_admin"}:
            async_to_sync(layer.group_send)(group, {"type": "order_event", "payload": payload})


def publish_captain_eligibility(user):
    """Push the fresh eligibility snapshot to one captain's open sockets."""
    layer = get_channel_layer()
    if not layer or user.role != "captain":
        return
    try:
        profile = user.captain_profile
    except CaptainProfile.DoesNotExist:
        return
    elig = enforce_online_invariant(profile)
    async_to_sync(layer.group_send)(f"user_{user.id}", {"type": "order_event",
        "payload": {"type": "captain.eligibility", "eligibility": elig}})


def admin_user_ids():
    return list(User.objects.filter(Q(role="admin") | Q(is_superuser=True)).values_list("id", flat=True))


def notify_user_ids(user_ids, event, order=None, payload=None):
    """Persist one notification per user and push it over the same private socket."""
    user_ids = sorted({int(uid) for uid in user_ids if uid})
    if not user_ids:
        return []
    payload = payload or {}
    order_id = order.id if order is not None else None
    layer = get_channel_layer()
    created = []
    for uid in user_ids:
        row = Notification.objects.create(user_id=uid, event=event, order=order, payload=payload)
        created.append(row)
        if layer:
            data = {
                "id": row.id, "event": row.event, "order": order_id,
                "order_number": order.order_number if order is not None else None,
                "payload": row.payload,
                    "is_read": False, "created_at": row.created_at.isoformat()}
            async_to_sync(layer.group_send)(f"user_{uid}", {"type": "order_event",
                "payload": {"type": "notification.created", "notification": data}})
    return created


def order_audience(order, exclude=()):
    ids = set()
    if order.customer_id:
        ids.add(order.customer_id)
    if order.merchant_id:
        merchant_user = getattr(order.merchant, "user_id", None)
        if merchant_user:
            ids.add(merchant_user)
    if order.captain_id:
        captain_user = getattr(order.captain, "user_id", None)
        if captain_user:
            ids.add(captain_user)
    return ids - {int(uid) for uid in exclude if uid}


def notify_order_event(order, event, exclude=(), payload=None, extra_users=()):
    return notify_user_ids(order_audience(order, exclude) | {int(uid) for uid in extra_users if uid},
                           event, order=order, payload=payload)


def notify_order_created(order):
    if order.merchant_id:
        notify_order_event(order, "order.created", exclude={order.customer_id}, payload={
            "customer_name": order.customer.get_full_name() or order.customer.username,
            "total": str(order.total), "items_count": len(order.items or []),
            "order_type": order.order_type,
        }, extra_users=admin_user_ids())
    if order.order_type == "ride":
        notify_user_ids(eligible_captain_user_ids(order), "order.available", order=order,
                        payload={"status": "new", "order_type": "ride"})


class StockUnavailable(Exception):
    def __init__(self, shortfalls):
        self.shortfalls = shortfalls


def reserve_stock(items, order=None, actor=None):
    """Reserve every requested line with conditional updates (safe under concurrency).

    A row is decremented only while the stored count still covers it, so two
    concurrent orders cannot both take the last unit. A product without a stock
    count cannot be sold at all: an unset count must never mean "sell anything",
    otherwise the merchant's stock ceiling is not real. Raises StockUnavailable
    so the caller's transaction rolls back earlier rows of the same order.
    Every accepted line also writes one InventoryMovement row.
    """
    shortfalls = []
    for row in items or []:
        try:
            product_id, quantity = int(row.get("product_id")), int(row.get("quantity", 0))
        except (TypeError, ValueError):
            raise ValidationError({"items": "Invalid order item."})
        if quantity <= 0:
            raise ValidationError({"items": "Quantity must be at least 1."})
        updated = Product.objects.filter(
            pk=product_id, quantity__isnull=False, quantity__gte=quantity
        ).update(quantity=F("quantity") - quantity)
        if not updated:
            product = Product.objects.filter(pk=product_id).only("name", "quantity").first()
            shortfalls.append({
                "product_id": product_id,
                "name": row.get("name") or (product.name if product else ""),
                "available": product.quantity if product and product.quantity is not None else 0,
                "requested": quantity,
                "reason": "untracked" if product and product.quantity is None else "shortage",
            })
            continue
        product = Product.objects.filter(pk=product_id).only("id", "name", "quantity").first()
        if product is not None:
            record_movement(
                product, -quantity, "order", actor=actor, order=order,
                before=(product.quantity or 0) + quantity, after=product.quantity,
            )
    if shortfalls:
        raise StockUnavailable(shortfalls)


def restore_order_stock(order):
    """Return reserved stock exactly once. Caller holds a row lock on the order."""
    if order.stock_restored_at or order.order_type != "store":
        return False
    restored = {}
    for row in order.items or []:
        if not row.get("stock_tracked"):
            continue
        try:
            product_id, quantity = int(row.get("product_id")), int(row.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        restored[product_id] = restored.get(product_id, 0) + quantity
    before = {
        p.id: p.quantity
        for p in Product.objects.filter(pk__in=restored).only("id", "quantity")
    }
    for product_id, quantity in restored.items():
        Product.objects.filter(pk=product_id).update(quantity=F("quantity") + quantity)
        product = Product.objects.filter(pk=product_id).only("id", "name", "quantity").first()
        if product is not None:
            record_movement(
                product, quantity, "cancel", order=order,
                before=(product.quantity or 0) - quantity, after=product.quantity,
            )
    order.stock_restored_at = timezone.now()
    if restored:
        after = list(Product.objects.select_related("merchant").filter(pk__in=restored))
        transaction.on_commit(lambda: publish_stock_events(before, after, "cancel", order))
    return True


def notify_stock_changes(before, after):
    """Notify merchants only when a count crosses the low or zero boundary."""
    for product in after:
        previous = before.get(product.id)
        if previous is None or product.quantity is None:
            continue
        merchant_user = getattr(product.merchant, "user_id", None)
        if not merchant_user:
            continue
        payload = {"product_id": product.id, "name": product.name, "quantity": product.quantity}
        if product.quantity <= 0 < previous:
            notify_user_ids({merchant_user} | set(admin_user_ids()), "stock.out", payload=payload)
        elif previous > product.low_stock_threshold >= product.quantity > 0:
            notify_user_ids({merchant_user}, "stock.low", payload=payload)


class RegisterView(APIView):
    """Public self-registration is restricted to customer accounts.

    Merchant, captain and administrator identities are provisioned by the
    authenticated platform administration workflow.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        role = str(data.get("role", "customer")).strip().lower()
        if role != "customer":
            raise ValidationError({"role": "Public registration is for customers only. Merchant and captain accounts must be created by an administrator."})
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        first_name = str(data.get("first_name", "")).strip()
        last_name = str(data.get("last_name", "")).strip()
        phone = str(data.get("phone", "")).strip()
        if not username or not first_name or not phone or len(password) < 8:
            raise ValidationError({"detail": "Username, first name, phone and a password of at least 8 characters are required."})
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError({"username": "This username is already in use."})
        if role == "merchant" and not str(data.get("shop_name", "")).strip():
            raise ValidationError({"shop_name": "Store name is required."})
        if role == "captain":
            if data.get("vehicle_type", "motorcycle") not in dict(CaptainProfile.VEHICLES):
                raise ValidationError({"vehicle_type": "Choose a valid vehicle type."})
            if data.get("permit_type", "west_bank") not in dict(CaptainProfile.PERMITS):
                raise ValidationError({"permit_type": "Choose a valid permit type."})
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(password)
        except Exception as exc:
            raise ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))})
        for field in ("profile_image", "store_image", "cover_image"):
            validate_image_upload(request.FILES.get(field), field=field)
        for field in ("identity_document", "driving_license_document", "insurance_document"):
            validate_document_upload(request.FILES.get(field), field=field)
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, password=password, email=str(data.get("email", "")).strip(),
                first_name=first_name, last_name=last_name, phone=phone, role=role,
                language=data.get("language", "ar") if data.get("language", "ar") in ("ar", "en", "he") else "ar",
                subscription_required=role in ("merchant", "captain"),
            )
            if request.FILES.get("profile_image"):
                user.profile_image = request.FILES["profile_image"]
                user.save(update_fields=["profile_image"])
            if role == "merchant":
                MerchantProfile.objects.create(
                    user=user, shop_name=str(data.get("shop_name", "")).strip(),
                    category=str(data.get("category", "general")).strip()[:40] or "general",
                    description=str(data.get("description", "")).strip(),
                    address=str(data.get("address", "")).strip(),
                    image=request.FILES.get("store_image"), cover_image=request.FILES.get("cover_image"),
                    is_open=False,
                )
            elif role == "captain":
                undertaking = as_bool(data.get("digital_undertaking"))
                if not undertaking:
                    raise ValidationError({"digital_undertaking": "You must accept the digital undertaking."})
                CaptainProfile.objects.create(
                    user=user, identity_document=request.FILES.get("identity_document"),
                    driving_license_document=request.FILES.get("driving_license_document"),
                    insurance_document=request.FILES.get("insurance_document"),
                    digital_undertaking_signed_at=timezone.now(),
                    vehicle_type=data.get("vehicle_type", "motorcycle"),
                    vehicle_model=str(data.get("vehicle_model", "")).strip()[:100],
                    plate_number=str(data.get("plate_number", "")).strip()[:30],
                    permit_type=data.get("permit_type", "west_bank"),
                    approved=False, rejected=False, online=False,
                )
        return Response({
            "id": user.id, "username": user.username, "role": user.role,
            "message": "Registration completed. Merchant stores and captain accounts require administrator review/activation.",
            "approval_status": "pending" if role == "captain" else None,
            "store_status": "pending_activation" if role == "merchant" else None,
        }, status=201)

class MeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)


STADIA_ROLE_ENV = {
    "customer": "STADIA_KEY_CUSTOMER",
    "captain": "STADIA_KEY_CAPTAIN",
    "merchant": "STADIA_KEY_MERCHANT",
}


class MapConfigView(APIView):
    """Serve the Stadia key that belongs to the authenticated account role.

    The role is read from the database user, never from request data. Admin
    accounts have no native app key. The response must never be cached or logged.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        env_name = STADIA_ROLE_ENV.get(request.user.role)
        if not env_name:
            raise PermissionDenied("No native map key is available for this account.")
        api_key = os.getenv(env_name, "").strip()
        if not api_key:
            return Response({"detail": "Map service is not configured."}, status=503)
        response = Response({
            "provider": "stadia",
            "role": request.user.role,
            "api_key": api_key,
            "tile_url": "https://tiles.stadiamaps.com/tiles/alidade_bright/{z}/{x}/{y}{r}.png",
            "attribution": "&copy; Stadia Maps &copy; OpenStreetMap contributors",
        })
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return Response({"status": "error", "database": "unavailable"}, status=503)
        commit = (os.getenv("RENDER_GIT_COMMIT") or "")[:7]
        return Response({"status": "ok", "database": "ok", "time": timezone.now().isoformat(), "commit": commit})


CAPTAIN_DOCUMENT_FIELDS = {
    "identity": "identity_document",
    "license": "driving_license_document",
    "insurance": "insurance_document",
}


def _captain_document_is_private(document):
    """Return True only when the stored name points at a captain document.

    Remote ImageKit names carry the upload prefix, so the check is segment
    based; a local name must still resolve inside MEDIA_ROOT/captain_documents.
    """
    name = str(document.name or "")
    if not is_captain_document(name):
        return False
    storage = document.storage
    if isinstance(storage, WaselniMediaStorage) and storage.is_remote_captain_document(name):
        return True
    try:
        storage_path = document.path
    except NotImplementedError:
        # Remote storage has no local path; the name check above still applies.
        return True
    except (OSError, ValueError, SuspiciousFileOperation):
        return False
    try:
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        private_root = os.path.realpath(os.path.join(media_root, "captain_documents"))
        target = os.path.realpath(storage_path)
        return os.path.commonpath([target, private_root]) == private_root
    except (OSError, ValueError):
        return False


class CaptainDocumentView(APIView):
    """Stream one captain document to its owner or an admin.

    Documents live on ImageKit as private files; the backend fetches them with
    a fresh signed URL that is never exposed to the client. Legacy local files
    are streamed from disk. /media/captain_documents/ is blocked, and knowing a
    file name is not enough because this view requires an authorised user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, profile_id, field):
        field_name = CAPTAIN_DOCUMENT_FIELDS.get(field)
        if not field_name:
            raise NotFound("Document not found.")
        try:
            profile = CaptainProfile.objects.select_related("user").get(pk=profile_id)
        except CaptainProfile.DoesNotExist:
            raise NotFound("Document not found.")
        is_admin = request.user.role == "admin"
        is_owner = request.user.role == "captain" and profile.user_id == request.user.id
        if not (is_admin or is_owner):
            raise PermissionDenied("You are not allowed to access this document.")
        document = getattr(profile, field_name)
        if not document:
            raise NotFound("Document not found.")
        if not _captain_document_is_private(document):
            raise NotFound("Document not found.")
        storage = document.storage
        try:
            if isinstance(storage, WaselniMediaStorage) and storage.is_remote_captain_document(document.name):
                handle = storage.private_document_handle(document.name)
            else:
                handle = document.open("rb")
        except (FileNotFoundError, OSError, ValueError, SuspiciousFileOperation):
            raise NotFound("Document not found.")
        response = FileResponse(handle, as_attachment=False, filename=os.path.basename(document.name))
        response["Cache-Control"] = "private, no-store"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class AccountProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        user = request.user
        previous = user.profile_image.name if user.profile_image else ""
        if "profile_image" in request.FILES:
            user.profile_image = validate_image_upload(request.FILES["profile_image"], field="profile_image")
        if request.data.get("remove_profile_image") == "true":
            user.profile_image = None
        user.save()
        current = user.profile_image.name if user.profile_image else ""
        if previous and previous != current:
            # Delete only after the new upload is safely stored, so a failed
            # upload never destroys the current avatar.
            user._meta.get_field("profile_image").storage.delete(previous)
        return Response(UserSerializer(user, context={"request": request}).data)

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        current = str(request.data.get("current_password", ""))
        new_password = str(request.data.get("new_password", ""))
        if not request.user.check_password(current):
            raise ValidationError({"current_password": "Current password is incorrect."})
        if len(new_password) < 8:
            raise ValidationError({"new_password": "New password must contain at least 8 characters."})
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(new_password, request.user)
        except Exception as exc:
            raise ValidationError({"new_password": list(getattr(exc, "messages", [str(exc)]))})
        request.user.set_password(new_password)
        request.user.must_change_password = False
        request.user.save(update_fields=["password", "must_change_password"])
        return Response({"ok": True, "message": "Password changed successfully."})


class MerchantProfileSelfView(APIView):
    permission_classes = [IsAuthenticated]

    def get_profile(self, request):
        if request.user.role != "merchant":
            raise PermissionDenied("Merchant account required.")
        try:
            return MerchantProfile.objects.get(user=request.user)
        except MerchantProfile.DoesNotExist:
            raise NotFound("Store profile has not been created for this account.")

    def get(self, request):
        profile = self.get_profile(request)
        return Response(MerchantProfileSerializer(profile, context={"request": request}).data)

    def patch(self, request):
        profile = self.get_profile(request)
        # Merchants may prepare/edit their draft store before subscription activation.
        # Public visibility remains gated by MerchantViewSet and subscription state.
        serializer = MerchantProfileSerializer(profile, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MerchantViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MerchantPublicSerializer
    permission_classes = [IsAuthenticated]
    queryset = MerchantProfile.objects.all()
    def get_queryset(self):
        today = timezone.localdate()
        qs = self.queryset.filter(approval_status="approved", is_open=True, temporarily_closed=False).filter(
            Q(user__subscription_required=False) |
            Q(user__subscriptions__status="active", user__subscriptions__starts_on__lte=today, user__subscriptions__ends_on__gte=today)
        )
        service = self.request.query_params.get("service", "").strip()
        if service:
            categories = {
                "food": ("food", "restaurant"),
                "grocery": ("grocery", "supermarket"),
                "pharmacy": ("pharmacy",),
            }
            if service not in categories:
                return qs.none()
            qs = qs.filter(
                Q(services__code=service) | Q(category__in=categories[service])
            )
        return qs.distinct().order_by("shop_name")

def subscription_access_error(user):
    """Enforce the same subscription state exposed to captain and admin APIs."""
    state = subscription_state(user)
    if state["active"]:
        return None
    if user.role == "captain":
        CaptainProfile.objects.filter(user=user, online=True).update(online=False)
    elif user.role == "merchant":
        MerchantProfile.objects.filter(user=user, is_open=True).update(is_open=False)
    return "Your subscription is not active. Please contact Waselni administration to renew it."


def add_months(source, months):
    month = source.month - 1 + months
    year = source.year + month // 12
    month = month % 12 + 1
    day = min(source.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class AdminUsersView(APIView):
    permission_classes = [IsAuthenticated]

    def check_admin(self, request):
        require_admin_permission(request, "staff")

    def get(self, request):
        self.check_admin(request)
        rows = []
        users = (User.objects.exclude(role="admin").select_related("captain_profile")
                 .prefetch_related("subscriptions__payments").order_by("-date_joined"))
        for user in users:
            state = subscription_state(user)
            latest = max(user.subscriptions.all(), key=lambda x: (x.starts_on, x.id), default=None)
            current = state["subscription"]
            rows.append({
                "id": user.id, "username": user.username, "identity_number": user.identity_number or "",
                "first_name": user.first_name, "last_name": user.last_name, "name": user.get_full_name() or user.username,
                "phone": user.phone, "role": user.role, "is_active": user.is_active,
                "is_finance_staff": user.is_finance_staff,
                "subscription_required": state["required"],
                "subscription_active": state["active"],
                "subscription_status": state["status"],
                "subscription": current,
                "last_subscription": ({"id": latest.id, "amount": str(latest.amount), "ends_on": latest.ends_on.isoformat(), "status": latest.status} if latest else None),
                "captain_profile_id": getattr(getattr(user, "captain_profile", None), "id", None) if user.role == "captain" else None,
                "eligibility": evaluate_captain(user) if user.role == "captain" else None,
            })
        return Response(rows)

    def post(self, request):
        self.check_admin(request)
        data = request.data
        role = data.get("role")
        if role not in ("customer", "merchant", "captain"):
            raise ValidationError({"role": "Choose customer, merchant or captain. Admin accounts are not created here."})
        identity = str(data.get("identity_number", "")).strip()
        first = str(data.get("first_name", "")).strip()
        last = str(data.get("last_name", "")).strip()
        phone = str(data.get("phone", "")).strip()
        if not identity or not first or not phone:
            raise ValidationError("Identity number, first name and phone are required.")
        if User.objects.filter(identity_number=identity).exists() or User.objects.filter(username=identity).exists():
            raise ValidationError({"identity_number": "An account already exists for this identity number."})
        shop_name = str(data.get("shop_name", "")).strip()
        if role == "merchant" and not shop_name:
            raise ValidationError({"shop_name": "Store name is required for a merchant account."})
        raw_password = str(data.get("password", "")).strip() or secrets.token_urlsafe(9)
        if len(raw_password) < 8:
            raise ValidationError({"password": "Temporary password must contain at least 8 characters."})
        with transaction.atomic():
            user = User.objects.create_user(username=identity, password=raw_password, first_name=first, last_name=last,
                phone=phone, identity_number=identity, role=role, language=data.get("language", "ar"),
                subscription_required=bool(data.get("subscription_required", role in ("merchant", "captain"))),
                must_change_password=True)
            if role == "merchant":
                MerchantProfile.objects.create(
                    user=user, shop_name=shop_name, category="general", is_open=False,
                    approval_status="pending",
                )
            elif role == "captain":
                vehicle_type = data.get("vehicle_type", "motorcycle")
                permit_type = data.get("permit_type", "west_bank")
                if vehicle_type not in dict(CaptainProfile.VEHICLES):
                    raise ValidationError({"vehicle_type": "Choose a valid vehicle type."})
                if permit_type not in dict(CaptainProfile.PERMITS):
                    raise ValidationError({"permit_type": "Choose a valid permit type."})
                CaptainProfile.objects.create(
                    user=user, approved=False, online=False,
                    vehicle_type=vehicle_type,
                    vehicle_model=str(data.get("vehicle_model", "")).strip()[:100],
                    plate_number=str(data.get("plate_number", "")).strip()[:30],
                    permit_type=permit_type,
                    checkpoint_badge=bool(data.get("checkpoint_badge", False)),
                    license_verified=False, insurance_verified=False,
                )
                # Every service starts pending: the administrator must approve
                # each one independently before the captain can execute it.
                CaptainServiceEligibility.objects.bulk_create([
                    CaptainServiceEligibility(captain=profile, service=code, status="pending")
                    for code in SERVICE_CODES
                ])
        return Response({"id": user.id, "username": user.username, "identity_number": identity,
                         "temporary_password": raw_password, "role": user.role,
                         "subscription_required": user.subscription_required,
                         "message": "Account created. Share the temporary password securely with the user."}, status=201)


class AdminSubscriptionsView(APIView):
    """Central subscription ledger used only by the in-app React admin console."""
    permission_classes = [IsAuthenticated]

    def check_admin(self, request):
        require_admin_permission(request, "finance")

    def get(self, request):
        self.check_admin(request)
        today = timezone.localdate()
        rows = []
        qs = Subscription.objects.select_related("user").prefetch_related("payments").order_by("-created_at")
        for sub in qs:
            paid = sum((payment.amount for payment in sub.payments.all()), Decimal("0.00"))
            due = sub.amount * sub.months
            effective = classify_subscription(sub, today)
            is_current = effective == "active"
            rows.append({
                "id": sub.id, "user_id": sub.user_id, "username": sub.user.username,
                "name": sub.user.get_full_name() or sub.user.username, "role": sub.user.role,
                "account_active": sub.user.is_active, "required": sub.user.subscription_required,
                "amount": str(sub.amount), "currency": sub.currency, "months": sub.months,
                "total_due": str(due), "paid_total": str(paid), "remaining": str(max(due - paid, Decimal("0.00"))),
                "starts_on": sub.starts_on.isoformat(), "ends_on": sub.ends_on.isoformat(),
                "status": sub.status, "effective_status": effective, "is_current": is_current, "notes": sub.notes,
            })
        return Response(rows)

    def patch(self, request, subscription_id):
        self.check_admin(request)
        try:
            sub = Subscription.objects.select_related("user").get(pk=subscription_id)
        except Subscription.DoesNotExist:
            return Response({"detail": "Subscription not found."}, status=404)
        status = request.data.get("status")
        if status not in dict(Subscription.STATUS_CHOICES):
            raise ValidationError({"status": "Choose active, pending, expired or cancelled."})
        sub.status = status
        sub.save(update_fields=["status"])
        sub.user.subscription_required = True
        sub.user.save(update_fields=["subscription_required"])
        publish_captain_eligibility(sub.user)  # also forces the captain offline if no longer eligible
        state = subscription_state(sub.user)
        return Response({"ok": True, "subscription_id": sub.id, "status": sub.status,
                         "subscription_active": state["active"], "subscription_status": state["status"], "user_id": sub.user_id})


class AdminUserDetailView(APIView):
    permission_classes = [IsAuthenticated]
    def check_admin(self, request):
        require_admin_permission(request, "staff")
    def patch(self, request, user_id):
        self.check_admin(request)
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=user_id)
                if "is_active" in request.data:
                    new_active = as_bool(request.data["is_active"])
                    if user.is_active != new_active:
                        reason = str(request.data.get("reason", "")).strip()
                        if not reason:
                            raise ValidationError({"reason": "A reason is required when changing account status."})
                        if len(reason) > 1000:
                            raise ValidationError({"reason": "The reason must be 1000 characters or fewer."})
                        AdminAccountAudit.objects.create(
                            target=user,
                            changed_by=request.user,
                            action="account_status",
                            previous_value="active" if user.is_active else "disabled",
                            new_value="active" if new_active else "disabled",
                            reason=reason,
                        )
                    user.is_active = new_active
                if "is_finance_staff" in request.data:
                    granted = as_bool(request.data["is_finance_staff"])
                    if user.is_finance_staff != granted:
                        user.is_finance_staff = granted
                        FinanceAccessAudit.objects.create(user=user, changed_by=request.user, granted=granted)
                if "subscription_required" in request.data:
                    user.subscription_required = as_bool(request.data["subscription_required"])
                if "phone" in request.data:
                    user.phone = str(request.data["phone"]).strip()
                user.save()
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)
        publish_captain_eligibility(user)
        return Response({
            "ok": True,
            "is_active": user.is_active,
            "is_finance_staff": user.is_finance_staff,
            "subscription_required": user.subscription_required,
        })


class FinanceAccessAuditView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        require_admin_permission(request, "audit")
        rows = FinanceAccessAudit.objects.select_related("user", "changed_by")[:200]
        return Response([{
            "id": row.id,
            "user": row.user.get_full_name() or row.user.username,
            "changed_by": row.changed_by.get_full_name() or row.changed_by.username,
            "granted": row.granted,
            "created_at": row.created_at.isoformat(),
        } for row in rows])


class AdminAccountAuditView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        require_admin_permission(request, "audit")
        rows = AdminAccountAudit.objects.select_related("target", "changed_by")[:200]
        return Response([{
            "id": row.id,
            "target": row.target.get_full_name() or row.target.username,
            "changed_by": row.changed_by.get_full_name() or row.changed_by.username,
            "action": row.action,
            "previous_value": row.previous_value,
            "new_value": row.new_value,
            "reason": row.reason,
            "created_at": row.created_at.isoformat(),
        } for row in rows])


class AdminUserSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, user_id):
        require_admin_permission(request, "finance")
        try: user = User.objects.get(pk=user_id)
        except User.DoesNotExist: return Response({"detail": "User not found."}, status=404)
        try:
            amount = Decimal(str(request.data.get("amount", "")))
            months = int(request.data.get("months", 1))
            starts_on = date.fromisoformat(str(request.data.get("starts_on") or timezone.localdate().isoformat()))
        except Exception:
            raise ValidationError("Enter a valid amount, start date and duration.")
        if amount <= 0 or months < 1 or months > 24:
            raise ValidationError("Monthly amount must be greater than zero and duration must be 1–24 months.")
        ends_on = add_months(starts_on, months) - timedelta(days=1)
        status = request.data.get("status", "active")
        if status not in ("active", "pending"):
            raise ValidationError({"status": "New subscriptions can be active or pending."})
        with transaction.atomic():
            user.subscription_required = True
            user.save(update_fields=["subscription_required"])
            sub = Subscription.objects.create(user=user, amount=amount, months=months, currency="ILS", starts_on=starts_on,
                ends_on=ends_on, status=status, notes=str(request.data.get("notes", ""))[:500], created_by=request.user)
        publish_captain_eligibility(user)
        return Response({"id": sub.id, "amount": str(sub.amount), "months": sub.months, "total_due": str(sub.amount * sub.months), "starts_on": sub.starts_on.isoformat(),
                         "ends_on": sub.ends_on.isoformat(), "status": sub.status}, status=201)


class AdminSubscriptionPaymentView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, subscription_id):
        require_admin_permission(request, "finance")
        try: sub = Subscription.objects.get(pk=subscription_id)
        except Subscription.DoesNotExist: return Response({"detail": "Subscription not found."}, status=404)
        try: amount = Decimal(str(request.data.get("amount", "")))
        except Exception: raise ValidationError({"amount": "Enter a valid payment amount."})
        if amount <= 0: raise ValidationError({"amount": "Payment must be greater than zero."})
        paid = sum((p.amount for p in sub.payments.all()), Decimal("0.00"))
        remaining = (sub.amount * sub.months) - paid
        if amount > remaining: raise ValidationError({"amount": f"Payment exceeds the remaining balance ({remaining})."})
        payment = SubscriptionPayment.objects.create(subscription=sub, amount=amount,
            method=request.data.get("method", "cash"), reference=str(request.data.get("reference", ""))[:100],
            notes=str(request.data.get("notes", ""))[:500], recorded_by=request.user)
        return Response({"id": payment.id, "amount": str(payment.amount), "paid_at": payment.paid_at.isoformat()}, status=201)


def captain_status_row(profile, elig):
    """One payload shape for the captain dashboard AND the admin dashboard.

    Both IDs are explicit: ``user_id`` is the account, ``captain_profile_id`` is
    the CaptainProfile row.  ``id`` is kept only as a deprecated alias of the
    profile id for old clients.  Every status field is derived from ``elig``.
    """
    user = profile.user
    return {
        "id": profile.id, "captain_profile_id": profile.id, "user_id": user.id,
        "username": user.username, "name": user.get_full_name() or user.username,
        "rating": str(profile.rating),
        "vehicle_type": profile.vehicle_type, "vehicle_model": profile.vehicle_model,
        "plate_number": profile.plate_number, "permit_type": profile.permit_type,
        "checkpoint_badge": profile.checkpoint_badge,
        "license_verified": profile.license_verified, "insurance_verified": profile.insurance_verified,
        "documents": {"identity_uploaded": bool(profile.identity_document),
                      "license_uploaded": bool(profile.driving_license_document),
                      "insurance_uploaded": bool(profile.insurance_document),
                      "undertaking_signed": bool(profile.digital_undertaking_signed_at)},
        "current_latitude": profile.current_latitude, "current_longitude": profile.current_longitude,
        "current_location_updated_at": profile.current_location_updated_at,
        "approval_status": elig["approval"]["status"],
        "eligibility": elig,
        **legacy_fields(elig),
    }


def captain_metrics(profile):
    """Derived performance figures and earnings for one captain.

    Earnings are the order delivery fee recorded on each completed order. The
    platform has no configured commission rate, so no commission is invented;
    cash collected is the product value the captain actually settled.
    """
    from django.db.models import Count
    orders = Order.objects.filter(captain=profile)
    completed = orders.filter(status="completed")
    assigned_total = orders.exclude(captain_accepted_at__isnull=True).count()
    progressed = orders.filter(status__in=("picked_up", "delivering", "awaiting_confirmation", "completed")).count()
    cancelled = orders.filter(status="cancelled").count()
    finished = completed.count()
    durations = [
        (row.completed_at - row.captain_accepted_at).total_seconds() / 60
        for row in completed.filter(captain_accepted_at__isnull=False, completed_at__isnull=False)
        .only("completed_at", "captain_accepted_at")
    ]
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def earnings(since=None, until=None):
        qs = completed
        if since:
            qs = qs.filter(completed_at__date__gte=since)
        if until:
            qs = qs.filter(completed_at__date__lte=until)
        total = qs.aggregate(value=Sum("delivery_fee"))["value"] or Decimal("0.00")
        return {"amount": str(total), "tasks": qs.count()}

    settlements = CashSettlement.objects.filter(captain=profile, order__status="completed")
    cash_collected = settlements.aggregate(value=Sum("amount"))["value"] or Decimal("0.00")
    return {
        "completed_tasks": finished,
        "cancelled_tasks": cancelled,
        "cancellation_rate": round(cancelled / (finished + cancelled) * 100, 1) if (finished + cancelled) else 0,
        "acceptance_rate": round(progressed / assigned_total * 100, 1) if assigned_total else 0,
        "average_completion_minutes": round(sum(durations) / len(durations), 1) if durations else None,
        "earnings": {
            "today": earnings(today, today),
            "week": earnings(week_start, today),
            "month": earnings(month_start, today),
            "cash_collected": str(cash_collected),
            "note": "Earnings are the delivery fee of completed tasks; no commission rule is configured.",
        },
        "max_active_tasks": profile.max_active_tasks,
        "active_tasks": active_task_count(profile),
    }


class CaptainSelfView(APIView):
    permission_classes = [IsAuthenticated]

    def get_profile(self, request):
        if request.user.role != "captain":
            raise PermissionDenied("Captain account required.")
        try:
            return request.user.captain_profile
        except CaptainProfile.DoesNotExist:
            raise PermissionDenied("Captain profile has not been created by an administrator.")

    def get(self, request):
        p = self.get_profile(request)
        elig = enforce_online_invariant(p)
        data = captain_status_row(p, elig)
        data.update(captain_metrics(p))
        data["working_windows"] = CaptainWorkingWindowSerializer(
            p.working_windows.all(), many=True
        ).data
        data["service_options"] = [
            {"service": code, "label": label, "status": row.status if row else "none",
             "accepting": row.accepting if row else False, "active": row.is_active if row else False,
             "regions": row.regions if row else []}
            for code, label in SERVICE_CHOICES
            for row in [next((r for r in p.service_eligibilities.all() if r.service == code), None)]
        ]
        return Response(data)

    def patch(self, request):
        p = self.get_profile(request)
        elig = enforce_online_invariant(p)
        if "online" in request.data:
            if as_bool(request.data["online"]):
                if not elig["can_go_online"]:
                    return Response({"detail": elig["message"], "reason": elig["reason"], "eligibility": elig}, status=403)
                p.online = True
            else:
                p.online = False
        replaced_documents = []
        for field in ("identity_document", "driving_license_document", "insurance_document"):
            upload = request.FILES.get(field)
            if upload:
                current = getattr(p, field)
                if current:
                    replaced_documents.append((field, current.name))
                setattr(p, field, validate_document_upload(upload, field=field))
        location_fields = ("current_latitude", "current_longitude")
        supplied_location = any(field in request.data for field in location_fields)
        if supplied_location:
            if not all(field in request.data for field in location_fields):
                raise ValidationError({"location": "Send both latitude and longitude together."})
            try:
                latitude = Decimal(str(request.data.get("current_latitude")))
                longitude = Decimal(str(request.data.get("current_longitude")))
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({"location": "GPS coordinates must be valid numbers."})
            if not Decimal("-90") <= latitude <= Decimal("90") or not Decimal("-180") <= longitude <= Decimal("180"):
                raise ValidationError({"location": "GPS coordinates are outside valid ranges."})
            p.current_latitude = latitude.quantize(Decimal("0.000001"))
            p.current_longitude = longitude.quantize(Decimal("0.000001"))
            p.current_location_updated_at = timezone.now()
        p.save()
        for field, old_name in replaced_documents:
            if old_name != getattr(p, field).name:
                p._meta.get_field(field).storage.delete(old_name)
        if supplied_location:
            active_orders = Order.objects.filter(captain=p, status__in=("assigned", "picked_up", "delivering"))
            for order in active_orders:
                publish_order_event(order, "captain.location")
        return self.get(request)


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    queryset = Product.objects.select_related("merchant").all()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == "merchant":
            access = merchant_access(user)
            if access is None:
                return qs.none()
            return qs.filter(merchant=access.merchant)
        today = timezone.localdate()
        qs = qs.filter(
            available=True,
            merchant__approval_status="approved",
            merchant__is_open=True,
            merchant__temporarily_closed=False,
        ).filter(
            Q(merchant__user__subscription_required=False) |
            Q(merchant__user__subscriptions__status="active",
              merchant__user__subscriptions__starts_on__lte=today,
              merchant__user__subscriptions__ends_on__gte=today)
        )
        merchant_id = self.request.query_params.get("merchant")
        if merchant_id:
            qs = qs.filter(merchant_id=merchant_id)
        service = self.request.query_params.get("service", "").strip()
        if service:
            if service not in ("food", "grocery", "pharmacy"):
                return qs.none()
            qs = qs.filter(Q(merchant__services__code=service) | Q(merchant__category__in={
                "food": ("food", "restaurant"),
                "grocery": ("grocery", "supermarket"),
                "pharmacy": ("pharmacy",),
            }[service]))
        if service == "pharmacy" or (merchant_id and MerchantProfile.objects.filter(pk=merchant_id, category="pharmacy").exists()):
            qs = qs.filter(
                pharmacy_review_status="approved",
                prescription_required=False,
                controlled_substance=False,
            )
        return qs.distinct()

    def _require(self, permission):
        access = merchant_access(self.request.user)
        if access is None or not access.can(permission):
            raise PermissionDenied("Your staff role does not allow this action.")
        return access

    def perform_create(self, serializer):
        access = self._require("inventory")
        product = serializer.save(merchant=access.merchant)
        quantity = product.quantity or 0
        if quantity:
            record_movement(product, quantity, "restock", actor=self.request.user,
                            before=0, after=quantity, note="Initial stock")

    def perform_update(self, serializer):
        access = self._require("inventory")
        data = self.request.data
        if ("price" in data or "discount_price" in data) and not access.can("prices"):
            raise PermissionDenied("Your staff role cannot change prices.")
        instance = serializer.instance
        old_price, old_discount, previous_quantity = instance.price, instance.discount_price, instance.quantity
        product = serializer.save()
        pharmacy_product = (
            instance.merchant.category == "pharmacy"
            or instance.merchant.services.filter(code="pharmacy").exists()
        )
        review_fields = {"name", "category", "description", "prescription_required", "controlled_substance"}
        if pharmacy_product and review_fields.intersection(data.keys()):
            product.pharmacy_review_status = "pending"
            product.save(update_fields=["pharmacy_review_status"])
        if product.price != old_price or product.discount_price != old_discount:
            PriceChange.objects.create(
                product=product, changed_by=self.request.user,
                old_price=old_price, new_price=product.price,
                old_discount=old_discount, new_discount=product.discount_price,
                reason=str(data.get("price_reason", ""))[:200],
            )
        if product.quantity != previous_quantity:
            before = 0 if previous_quantity is None else previous_quantity
            after = 0 if product.quantity is None else product.quantity
            record_movement(product, after - before, "manual", actor=self.request.user,
                            before=before, after=after, note="Product edit")
            publish_stock_events({product.id: previous_quantity}, [product], "manual")

    def perform_destroy(self, instance):
        self._require("inventory")
        instance.delete()

    @action(detail=True, methods=["post"])
    def stock(self, request, pk=None):
        """Adjust tracked stock by a delta under a row lock so taps cannot be lost."""
        access = self._require("inventory")
        try:
            delta = int(request.data.get("delta"))
        except (TypeError, ValueError):
            return Response({"detail": "delta must be an integer."}, status=400)
        if delta == 0:
            return Response({"detail": "delta must not be zero."}, status=400)
        reason = str(request.data.get("reason", "manual"))
        if reason not in ("manual", "restock", "correction"):
            reason = "manual"
        note = str(request.data.get("note", ""))[:255]
        with transaction.atomic():
            product = (Product.objects.select_for_update().select_related("merchant")
                       .filter(pk=pk, merchant=access.merchant).first())
            if product is None:
                raise NotFound("Product not found.")
            # An unset count starts at zero: the first tap turns tracking on
            # instead of failing, so legacy rows can be stocked from the portal.
            previous = 0 if product.quantity is None else product.quantity
            product.quantity = max(0, min(previous + delta, 1000000))
            product.save(update_fields=["quantity"])
            record_movement(product, product.quantity - previous, reason,
                            actor=request.user, before=previous, after=product.quantity, note=note)
        notify_stock_changes({product.id: previous}, [product])
        publish_stock_events({product.id: previous}, [product], reason)
        return Response(self.get_serializer(product).data)

    @action(detail=False, methods=["get"], url_path="movements")
    def movements(self, request):
        """Immutable stock ledger for the merchant, newest first."""
        access = merchant_access(request.user)
        if access is None:
            raise PermissionDenied("Merchant account required.")
        qs = InventoryMovement.objects.select_related("product", "order", "actor").filter(
            product__merchant=access.merchant
        )
        product_id = request.query_params.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)
        return Response(InventoryMovementSerializer(qs[:200], many=True).data)

class CustomerDeliveryRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def _coordinate(self, data, name, minimum, maximum):
        try:
            value = Decimal(str(data.get(name)))
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError({name: "Select a valid location."})
        if not value.is_finite() or value < minimum or value > maximum:
            raise ValidationError({name: "Location is outside the valid range."})
        return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _distance(self, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng):
        radius = 6371.0
        lat1, lat2 = math.radians(float(pickup_lat)), math.radians(float(dropoff_lat))
        dlat = lat2 - lat1
        dlng = math.radians(float(dropoff_lng - pickup_lng))
        haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        return max(0.5, 2 * radius * math.asin(min(1, math.sqrt(haversine))) * 1.25)

    def _base_data(self, request, service):
        if request.user.role != "customer":
            raise PermissionDenied("Only customers can request this service.")
        error = subscription_access_error(request.user)
        if error:
            raise PermissionDenied(error)
        if not PlatformService.is_offered(service):
            raise PermissionDenied("This service is paused by Waselni administration.")
        data = request.data
        pickup = str(data.get("pickup_address", "")).strip()[:255]
        dropoff = str(data.get("dropoff_address", "")).strip()[:255]
        if not pickup or not dropoff:
            raise ValidationError({"addresses": "Enter both pickup and destination addresses."})
        plat = self._coordinate(data, "pickup_latitude", Decimal("-90"), Decimal("90"))
        plon = self._coordinate(data, "pickup_longitude", Decimal("-180"), Decimal("180"))
        dlat = self._coordinate(data, "dropoff_latitude", Decimal("-90"), Decimal("90"))
        dlon = self._coordinate(data, "dropoff_longitude", Decimal("-180"), Decimal("180"))
        distance = Decimal(str(self._distance(plat, plon, dlat, dlon))).quantize(Decimal("0.01"))
        return data, pickup, dropoff, plat, plon, dlat, dlon, distance

    def post(self, request, service):
        if service not in ("parcel", "logistics"):
            raise NotFound("Delivery service not found.")
        data, pickup, dropoff, plat, plon, dlat, dlon, distance = self._base_data(request, service)
        details = {
            "service": service,
            "package_type": str(data.get("package_type", "parcel")).strip()[:40],
            "weight_kg": str(data.get("weight_kg", "")).strip()[:20],
            "dimensions": str(data.get("dimensions", "")).strip()[:80],
            "notes": str(data.get("notes", "")).strip()[:1000],
        }
        try:
            weight = Decimal(details["weight_kg"] or "0")
        except InvalidOperation:
            raise ValidationError({"weight_kg": "Enter a valid weight."})
        if not weight.is_finite() or weight < 0 or weight > 1000:
            raise ValidationError({"weight_kg": "Weight must be between 0 and 1000 kg."})
        details["weight_kg"] = str(weight)
        request_key = request.headers.get("Idempotency-Key", "").strip()[:64]
        if service == "parcel":
            recipient_name = str(data.get("recipient_name", "")).strip()[:150]
            recipient_phone = str(data.get("recipient_phone", "")).strip()[:30]
            if not recipient_name or not recipient_phone:
                raise ValidationError({"recipient": "Recipient name and phone are required."})
            base = Decimal(os.getenv("PARCEL_BASE_FARE", "5.00"))
            per_km = Decimal(os.getenv("PARCEL_PRICE_PER_KM", "2.00"))
            per_kg = Decimal(os.getenv("PARCEL_PRICE_PER_KG", "0.50"))
            fee = (base + distance * per_km + weight * per_kg).quantize(Decimal("0.01"))
            if fee > Decimal("500.00"):
                raise ValidationError({"weight_kg": "This shipment requires a special quote."})
            details.update({
                "recipient_name": recipient_name,
                "recipient_phone": recipient_phone,
                "quote_status": "not_required",
            })
            status = "ready"
        else:
            try:
                piece_count = int(data.get("piece_count") or 1)
            except (TypeError, ValueError):
                raise ValidationError({"piece_count": "Enter a whole number."})
            details.update({
                "sender_name": str(data.get("sender_name", "")).strip()[:150],
                "sender_phone": str(data.get("sender_phone", "")).strip()[:30],
                "recipient_name": str(data.get("recipient_name", "")).strip()[:150],
                "recipient_phone": str(data.get("recipient_phone", "")).strip()[:30],
                "piece_count": max(1, min(100, piece_count)),
                "quote_status": "requested",
            })
            if not all(details[key] for key in ("sender_name", "sender_phone", "recipient_name", "recipient_phone")):
                raise ValidationError({"contacts": "Sender and recipient names and phone numbers are required."})
            fee = Decimal("0.00")
            status = "new"
        defaults = dict(
            order_type="parcel", service_type=service, status=status,
            pickup_address=pickup, dropoff_address=dropoff,
            pickup_latitude=plat, pickup_longitude=plon,
            dropoff_latitude=dlat, dropoff_longitude=dlon,
            distance_km=distance, delivery_fee=fee, total=fee,
            items=[], service_details=details,
        )
        with transaction.atomic():
            if request_key:
                order, created = Order.objects.get_or_create(
                    customer=request.user, request_key=request_key, defaults=defaults,
                )
            else:
                order = Order.objects.create(customer=request.user, **defaults)
                created = True
            if created:
                if service == "parcel":
                    order.ensure_delivery_otp()
                record_order_activity(order, "created", actor=request.user, to_status=order.status)
        if created:
            publish_order_event(order, "order.created")
            if service == "parcel":
                notify_user_ids(eligible_captain_user_ids(order), "order.available", order=order,
                                payload={"status": "ready", "order_type": "parcel"})
            else:
                notify_user_ids(admin_user_ids(), "order.created", order=order,
                                payload={"status": "new", "order_type": "parcel", "service_type": "logistics"})
        return Response(OrderSerializer(order, context={"request": request}).data, status=201 if created else 200)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.select_related("customer", "merchant__user", "captain__user").prefetch_related(
        "activities", "ratings"
    )
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        if u.role == "admin":
            queryset = self.queryset
        elif u.role == "merchant":
            access = merchant_access(u)
            queryset = self.queryset.filter(merchant=access.merchant) if access else self.queryset.none()
        elif u.role == "captain":
            queryset = self.queryset.filter(captain__user=u)
        else:
            queryset = self.queryset.filter(customer=u)
        search = self.request.query_params.get("search", "").strip()
        if self.action == "list" and search:
            criteria = Q(order_number__icontains=search)
            if u.role == "admin" or u.is_superuser:
                try:
                    criteria |= Q(pk=int(search))
                except ValueError:
                    pass
            queryset = queryset.filter(criteria)
        return queryset

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        error = subscription_access_error(request.user)
        if error:
            raise PermissionDenied(error)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_key = request.headers.get("Idempotency-Key", "").strip()[:64]
        if request_key:
            existing = Order.objects.filter(customer=request.user, request_key=request_key).first()
            if existing:
                return Response(self.get_serializer(existing).data, status=200)
        items = serializer.validated_data.get("items") or []
        tracked_ids = [row["product_id"] for row in items if row.get("stock_tracked")]
        before = {p.id: p.quantity for p in Product.objects.filter(pk__in=tracked_ids).only("id", "quantity")}
        duplicate = None
        try:
            with transaction.atomic():
                if request_key:
                    duplicate = Order.objects.filter(customer=request.user, request_key=request_key).first()
                    if duplicate:
                        transaction.set_rollback(True)
                if not duplicate:
                    if request_key:
                        order, created = Order.objects.get_or_create(
                            customer=request.user, request_key=request_key,
                            defaults=serializer.validated_data,
                        )
                        if not created:
                            duplicate = order
                            transaction.set_rollback(True)
                    else:
                        order = serializer.save(customer=request.user)
                        created = True
                    if created:
                        # Reservation and its ledger rows share the order
                        # transaction, so a shortage rolls both back together.
                        reserve_stock(items, order=order, actor=request.user)
                        if proof_policy(order)["otp_required"]:
                            order.ensure_delivery_otp()
                        record_order_activity(
                            order, "created", actor=request.user, to_status=order.status,
                        )
        except StockUnavailable as exc:
            names = ", ".join(f"{row['name']} ({row['available']})" for row in exc.shortfalls)
            notify_user_ids({request.user.id}, "stock.out", payload={
                "products": exc.shortfalls, "message": names,
            })
            first = exc.shortfalls[0]
            if first.get("reason") == "untracked":
                message = f"{first['name']} has no stock count yet and cannot be sold."
            else:
                message = f"Only {first['available']} of {first['name']} are available."
            # The structured list lets the storefront show the product names in
            # the customer's own language instead of the English API sentence.
            raise ValidationError({"items": message, "stock": exc.shortfalls})
        if duplicate:
            return Response(self.get_serializer(duplicate).data, status=200)
        if created:
            publish_order_event(order, "order.created")
            notify_order_created(order)
            if tracked_ids:
                after = list(Product.objects.select_related("merchant").filter(pk__in=tracked_ids))
                notify_stock_changes(before, after)
                publish_stock_events(before, after, "order", order)
        return Response(self.get_serializer(order).data, status=201 if created else 200)

    @action(detail=False, methods=["get"])
    def available(self, request):
        if request.user.role != "captain":
            raise PermissionDenied("Captain account required.")
        try:
            captain = request.user.captain_profile
        except CaptainProfile.DoesNotExist:
            return Response([])
        # Prefetch the dispatch rules once instead of per candidate order.
        captain = CaptainProfile.objects.prefetch_related(
            "service_eligibilities", "working_windows"
        ).get(pk=captain.pk)
        # Ineligible or offline captains see no dispatchable orders; the captain
        # dashboard shows the exact reason from the same eligibility result.
        # Orders already assigned to the captain stay visible so an in-progress
        # trip can always be finished.
        own_orders = self.queryset.filter(captain=captain)
        if not enforce_online_invariant(captain)["can_receive_orders"]:
            return Response(self.get_serializer(own_orders, many=True).data)
        qs = self.queryset.filter(Q(status="ready", captain__isnull=True) | Q(status="new", order_type="ride", captain__isnull=True) | Q(captain=captain))
        orders = [o for o in qs if o.captain_id == captain.id or not order_compatibility_reasons(captain, o)]
        return Response(self.get_serializer(orders, many=True).data)

    @action(detail=False, methods=["post"], url_path="ride")
    def ride(self, request):
        if request.user.role != "customer":
            raise PermissionDenied("Only customers can request a ride.")
        error = subscription_access_error(request.user)
        if error:
            raise PermissionDenied(error)
        if not PlatformService.is_offered("ride"):
            raise PermissionDenied("Ride booking is paused by Waselni administration.")
        data = request.data
        pickup = str(data.get("pickup_address", "")).strip()
        dropoff = str(data.get("dropoff_address", "")).strip()
        if not pickup or not dropoff:
            raise ValidationError({"addresses": "Enter both pickup and destination addresses."})
        try:
            plat = Decimal(str(data.get("pickup_latitude")))
            plon = Decimal(str(data.get("pickup_longitude")))
            dlat = Decimal(str(data.get("dropoff_latitude")))
            dlon = Decimal(str(data.get("dropoff_longitude")))
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError({"location": "Select both locations using the location controls."})
        if not all(value.is_finite() for value in (plat, plon, dlat, dlon)):
            raise ValidationError({"location": "Coordinates are outside valid ranges."})
        if not (Decimal("-90") <= plat <= Decimal("90") and Decimal("-90") <= dlat <= Decimal("90")
                and Decimal("-180") <= plon <= Decimal("180") and Decimal("-180") <= dlon <= Decimal("180")):
            raise ValidationError({"location": "Coordinates are outside valid ranges."})
        # Map components send full float precision; store the same 6 decimals as every
        # other coordinate field so pickup and dropoff stay consistent across the system.
        plat, plon, dlat, dlon = (
            value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            for value in (plat, plon, dlat, dlon)
        )
        fplat, fplon, fdlat, fdlon = map(float, (plat, plon, dlat, dlon))
        # Road distance is calculated by the map in the client; the customer proposes
        # the delivery fare and a captain explicitly accepts that exact fare.
        radius = 6371.0
        a1, a2 = math.radians(fplat), math.radians(fdlat)
        da, do = math.radians(fdlat - fplat), math.radians(fdlon - fplon)
        h = math.sin(da/2)**2 + math.cos(a1)*math.cos(a2)*math.sin(do/2)**2
        distance = max(0.5, 2 * radius * math.asin(min(1, math.sqrt(h))) * 1.25)
        checkpoint = str(data.get("requires_checkpoint", "false")).lower() in ("true", "1", "yes")
        base_fare = Decimal(os.getenv("RIDE_BASE_FARE", "5.00"))
        per_km = Decimal(os.getenv("RIDE_PRICE_PER_KM", "2.00"))
        estimated_fee = (base_fare + (Decimal(str(distance)).quantize(Decimal("0.01")) * per_km)).quantize(Decimal("0.01"))
        try:
            fee = Decimal(str(data.get("delivery_fee", estimated_fee))).quantize(Decimal("0.01"))
        except Exception:
            raise ValidationError({"delivery_fee": "Enter a valid delivery price."})
        if not fee.is_finite() or fee < Decimal("0.50") or fee > Decimal("500.00"):
            raise ValidationError({"delivery_fee": "Delivery price must be between 0.50 and 500.00 ILS."})
        checkpoint_fee = Decimal(os.getenv("RIDE_CHECKPOINT_FEE", "15.00")) if checkpoint else Decimal("0.00")
        total = fee + checkpoint_fee
        request_key = request.headers.get("Idempotency-Key", "").strip()[:64]
        order_defaults = dict(
            order_type="ride", required_vehicle="motorcycle", status="new",
            pickup_address=pickup, dropoff_address=dropoff,
            pickup_latitude=plat, pickup_longitude=plon, dropoff_latitude=dlat, dropoff_longitude=dlon,
            distance_km=Decimal(str(distance)).quantize(Decimal("0.01")), delivery_fee=fee,
            checkpoint_fee=checkpoint_fee, total=total, requires_checkpoint=checkpoint,
            payment_method=data.get("payment_method", "cash") if data.get("payment_method") in ("cash", "online") else "cash")
        order_defaults["service_type"] = "ride"
        with transaction.atomic():
            if request_key:
                order, created = Order.objects.get_or_create(
                    customer=request.user, request_key=request_key, defaults=order_defaults
                )
            else:
                order = Order.objects.create(customer=request.user, **order_defaults)
                created = True
            if created:
                record_order_activity(
                    order, "created", actor=request.user, to_status=order.status,
                )
        if created:
            publish_order_event(order, "order.created")
            notify_order_created(order)
        return Response(self.get_serializer(order).data, status=201 if created else 200)

    @action(detail=True, methods=["post"])
    def quote(self, request, pk=None):
        """Operations offers a logistics quote; only the customer can accept it."""
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=pk)
            if order.service_type != "logistics" or order.order_type != "parcel":
                raise ValidationError("Quotes are only available for special logistics requests.")
            details = dict(order.service_details or {})
            if request.user.role == "admin":
                try:
                    amount = Decimal(str(request.data.get("amount"))).quantize(Decimal("0.01"))
                except (InvalidOperation, TypeError, ValueError):
                    raise ValidationError({"amount": "Enter a valid quote amount."})
                if not amount.is_finite() or amount <= 0 or amount > Decimal("10000.00"):
                    raise ValidationError({"amount": "Quote amount must be between 0.01 and 10000.00."})
                if order.status != "new" or details.get("quote_status") != "requested":
                    raise ValidationError("This request is not waiting for a quote.")
                details.update({"quote_status": "offered", "quoted_amount": str(amount)})
                order.delivery_fee = amount
                order.total = amount
                event = "quote.offered"
            elif request.user.role == "customer" and order.customer_id == request.user.id:
                if request.data.get("accept") is not True or details.get("quote_status") != "offered":
                    raise ValidationError("Accept the current quote to dispatch this shipment.")
                details["quote_status"] = "accepted"
                order.status = "ready"
                order.ensure_delivery_otp()
                event = "quote.accepted"
            else:
                raise PermissionDenied("Only operations can offer a quote and only its customer can accept it.")
            order.service_details = details
            order.save(update_fields=["service_details", "delivery_fee", "total", "status", "updated_at"])
            record_order_activity(order, event, actor=request.user, from_status="new", to_status=order.status)
        publish_order_event(order, "order.updated")
        if event == "quote.accepted":
            notify_user_ids(eligible_captain_user_ids(order), "order.available", order=order,
                            payload={"status": "ready", "order_type": "parcel"})
        return Response(self.get_serializer(order).data)

    @action(detail=False, methods=["get"])
    def tracking(self, request):
        """Live delivery tracking for the merchant's own active store orders."""
        if request.user.role != "merchant":
            raise PermissionDenied("Merchant account required.")
        qs = self.get_queryset().filter(
            order_type="store", captain__isnull=False,
            status__in=("assigned", "picked_up", "delivering"),
        ).order_by("-updated_at")
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        if request.user.role != "merchant":
            raise PermissionDenied("Merchant account required.")
        error = subscription_access_error(request.user)
        if error: raise PermissionDenied(error)
        minutes = request.data.get("prep_minutes", 10)
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid preparation time."}, status=400)
        if minutes not in [10, 15, 20, 30, 40]:
            return Response({"detail": "Choose a valid preparation time."}, status=400)
        with transaction.atomic():
            order = Order.objects.select_for_update(of=("self",)).select_related("merchant__user", "customer").get(pk=pk)
            if not order.merchant or order.merchant.user_id != request.user.id:
                raise PermissionDenied("This order does not belong to your store.")
            if order.status != "new":
                return Response({"detail": "This order is no longer new."}, status=409)
            order.prep_minutes = minutes
            order.status = "accepted"
            order.accepted_at = timezone.now()
            order.save()
            record_order_activity(order, "accepted", actor=request.user, from_status="new")
        publish_order_event(order)
        notify_order_event(order, "order.accepted", exclude={request.user.id}, payload={"prep_minutes": minutes})
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def arrive(self, request, pk=None):
        if request.user.role != "captain":
            raise PermissionDenied("Only the assigned captain can report arrival.")
        with transaction.atomic():
            order = Order.objects.select_for_update(of=("self",)).select_related("captain__user", "merchant").get(pk=pk)
            if not order.captain or order.captain.user_id != request.user.id:
                raise PermissionDenied("This order is not assigned to you.")
            if order.order_type != "store" or order.status != "assigned":
                raise ValidationError("Arrival can only be reported for an assigned store order.")
            if not order.merchant_arrived_at:
                order.merchant_arrived_at = timezone.now()
                order.save(update_fields=["merchant_arrived_at", "updated_at"])
                record_order_activity(
                    order,
                    "captain_arrived",
                    actor=request.user,
                    from_status=order.status,
                    to_status=order.status,
                )
        publish_order_event(order, "order.captain_arrived")
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        new_status = request.data.get("status")
        # Existing assigned/in-progress orders may be completed even after a subscription expires.
        transitions = {
            "merchant": {"new": {"cancelled"}, "accepted": {"preparing"}, "preparing": {"ready"}},
            "captain": {"assigned": {"picked_up"}, "picked_up": {"delivering"}, "delivering": {"awaiting_confirmation"}},
            "admin": {"new": {"cancelled"}, "accepted": {"cancelled"}, "preparing": {"cancelled"}, "ready": {"cancelled"}, "assigned": {"cancelled"}},
            "customer": {"new": {"cancelled"}, "awaiting_confirmation": {"completed"}},
        }
        with transaction.atomic():
            order = Order.objects.select_for_update(of=("self",)).select_related("merchant__user", "captain__user", "customer").get(pk=pk)
            role = request.user.role
            if role == "merchant":
                access = merchant_access(request.user)
                if access is None or not order.merchant or access.merchant.id != order.merchant_id:
                    raise PermissionDenied("This order does not belong to your store.")
                needed = "preparation" if new_status in ("preparing", "ready") else "orders"
                if not access.can(needed):
                    raise PermissionDenied("Your staff role does not allow this order action.")
            if role == "captain" and (not order.captain or order.captain.user_id != request.user.id):
                raise PermissionDenied("This order is not assigned to you.")
            if role == "customer" and order.customer_id != request.user.id:
                raise PermissionDenied("This order does not belong to you.")
            if new_status not in transitions.get(role, {}).get(order.status, set()):
                return Response({"detail": "This status transition is not allowed."}, status=400)
            previous_status = order.status
            if new_status == "picked_up" and order.order_type == "store" and not order.merchant_arrived_at:
                return Response({"detail": "Report arrival at the merchant before confirming pickup."}, status=400)
            if new_status == "awaiting_confirmation" and proof_policy(order)["photo_required"] and not proof_complete(order):
                return Response({"detail": "Record the required delivery proof before completing this task."}, status=400)
            # Cash handover is reconciled after successful delivery. It must never
            # block the captain from starting the trip.
            order.status = new_status
            if new_status == "ready":
                order.ready_at = timezone.now()
            elif new_status == "awaiting_confirmation":
                order.captain_delivered_at = timezone.now()
            if new_status == "cancelled":
                restore_order_stock(order)
                order.save()
                record_order_activity(
                    order, "status_changed", actor=request.user,
                    from_status=previous_status, to_status=order.status,
                )
            elif new_status == "completed":
                order.status = "awaiting_confirmation"
                complete_order(order, completed_by=request.user, method="customer")
            else:
                order.save()
                record_order_activity(
                    order, "status_changed", actor=request.user,
                    from_status=previous_status, to_status=order.status,
                )
        publish_order_event(order, "order.ready" if new_status == "ready" else "order.updated")
        if new_status == "cancelled":
            notify_order_event(order, "order.cancelled", exclude={request.user.id},
                               payload={"status": "cancelled"},
                               extra_users=set(admin_user_ids()) - {request.user.id})
        else:
            notify_order_event(order, "order.ready" if new_status == "ready" else "order.status",
                               exclude={request.user.id}, payload={"status": new_status})
            if new_status == "ready":
                notify_user_ids(eligible_captain_user_ids(order), "order.available", order=order,
                                payload={"status": "ready", "order_type": order.order_type})
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        if request.user.role != "captain":
            raise PermissionDenied("Captain account required.")
        try:
            captain = request.user.captain_profile
        except CaptainProfile.DoesNotExist:
            raise PermissionDenied("Captain profile not found.")
        with transaction.atomic():
            order = Order.objects.select_for_update(of=("self",)).select_related("merchant__user", "customer").get(pk=pk)
            eligible_status = order.status == "new" if order.order_type == "ride" else order.status == "ready"
            if not eligible_status or order.captain_id is not None:
                return Response({"detail": "Order is no longer available."}, status=409)
            try:
                accepted_fee = Decimal(str(request.data.get("accepted_delivery_fee"))).quantize(Decimal("0.01"))
            except Exception:
                return Response({"detail": "Confirm the displayed delivery fee before accepting this order."}, status=400)
            if not accepted_fee.is_finite() or accepted_fee != order.delivery_fee:
                return Response({"detail": "The delivery fee changed. Refresh the order and review the new amount."}, status=409)
            elig = evaluate_captain(request.user, captain, order=order)
            if not elig["can_accept_order"]:
                return Response({"detail": elig["message"], "reason": elig["reason"], "eligibility": elig}, status=403)
            previous_status = order.status
            order.captain = captain
            order.status = "assigned"
            order.captain_accepted_at = timezone.now()
            order.save(update_fields=["captain", "status", "captain_accepted_at", "updated_at"])
            record_order_activity(
                order, "assigned", actor=request.user,
                from_status=previous_status, to_status=order.status,
            )
        publish_order_event(order)
        notify_order_event(order, "order.assigned", exclude={request.user.id}, payload={"status": "assigned"})
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Merchant rejects a new/accepted order with a mandatory reason."""
        if request.user.role not in ("merchant", "admin"):
            raise PermissionDenied("Only the store or the administration can reject an order.")
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError({"reason": "A rejection reason is required."})
        if len(reason) > 500:
            raise ValidationError({"reason": "The reason must be 500 characters or fewer."})
        with transaction.atomic():
            order = Order.objects.select_for_update(of=("self",)).select_related(
                "merchant", "captain__user", "customer"
            ).get(pk=pk)
            if request.user.role == "merchant":
                access = merchant_access(request.user)
                if access is None or not order.merchant or access.merchant.id != order.merchant_id:
                    raise PermissionDenied("This order does not belong to your store.")
                if not access.can("orders"):
                    raise PermissionDenied("Your staff role cannot reject orders.")
            if order.status not in ("new", "accepted"):
                return Response({"detail": "Only new or accepted orders can be rejected."}, status=409)
            previous_status = order.status
            order.status = "cancelled"
            order.cancellation_reason = reason
            restore_order_stock(order)
            order.save()
            record_order_activity(
                order, "rejected", actor=request.user,
                from_status=previous_status, to_status=order.status,
            )
        publish_order_event(order, "order.cancelled")
        notify_order_event(order, "order.rejected", exclude={request.user.id},
                           payload={"status": "cancelled", "reason": reason})
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def proof(self, request, pk=None):
        """Record pickup/delivery proof for the captain's own task."""
        if request.user.role != "captain":
            raise PermissionDenied("Captain account required.")
        kind = str(request.data.get("kind", "delivery")).strip()
        if kind not in ("pickup", "delivery"):
            raise ValidationError({"kind": "Choose pickup or delivery."})
        with transaction.atomic():
            order = Order.objects.select_for_update(of=("self",)).select_related("captain__user").get(pk=pk)
            if not order.captain or order.captain.user_id != request.user.id:
                raise PermissionDenied("This order is not assigned to you.")
            if order.status in ("completed", "cancelled"):
                return Response({"detail": "This order is closed."}, status=409)
            existing = OrderProof.objects.filter(order=order, kind=kind).first()
            photo = validate_image_upload(request.FILES.get("photo"), field="photo") if request.FILES.get("photo") else None
            if photo is None and existing is not None:
                photo = existing.photo
            policy = proof_policy(order)
            otp_verified = bool(existing and existing.otp_verified)
            code = str(request.data.get("otp", "")).strip()
            if kind == "delivery" and policy["otp_required"] and order.delivery_otp:
                if code != order.delivery_otp:
                    return Response({"detail": "The delivery code is incorrect."}, status=400)
                otp_verified = True
            recipient = str(request.data.get("recipient_name", "")).strip()[:150]
            if kind == "delivery" and policy["recipient_required"] and not recipient:
                raise ValidationError({"recipient_name": "Enter the recipient name for this service."})
            if kind == "delivery" and policy["photo_required"] and not photo:
                raise ValidationError({"photo": "A delivery photo is required for this service."})
            proof, _ = OrderProof.objects.update_or_create(
                order=order, kind=kind,
                defaults={
                    "photo": photo,
                    "recipient_name": recipient,
                    "notes": str(request.data.get("notes", "")).strip()[:500],
                    "otp_verified": otp_verified,
                    "captured_by": request.user,
                },
            )
            if otp_verified and not order.delivery_otp_verified_at:
                order.delivery_otp_verified_at = timezone.now()
                order.save(update_fields=["delivery_otp_verified_at", "updated_at"])
            record_order_activity(
                order,
                "pickup_proof" if kind == "pickup" else "delivery_proof",
                actor=request.user, from_status=order.status, to_status=order.status,
            )
        publish_order_event(order)
        return Response(OrderProofSerializer(proof).data, status=201)

    @action(detail=True, methods=["get"], url_path=r"proofs/(?P<kind>[a-z]+)/photo")
    def proof_photo(self, request, pk=None, kind=None):
        """Serve a proof photo only to the parties involved in the order."""
        try:
            order = Order.objects.select_related("merchant", "captain__user").get(pk=pk)
        except Order.DoesNotExist:
            raise NotFound("Order not found.")
        user = request.user
        access = merchant_access(user) if user.role == "merchant" else None
        allowed = (
            user.role == "admin"
            or order.customer_id == user.id
            or (order.captain_id and order.captain.user_id == user.id)
            or (access is not None and order.merchant_id == access.merchant.id)
        )
        if not allowed:
            raise PermissionDenied("You are not allowed to access this proof.")
        proof = OrderProof.objects.filter(order=order, kind=kind).first()
        if proof is None or not proof.photo:
            raise NotFound("Proof not found.")
        storage = proof.photo.storage
        try:
            if isinstance(storage, WaselniMediaStorage) and storage.is_remote_private_document(proof.photo.name):
                handle = storage.private_document_handle(proof.photo.name)
            else:
                handle = proof.photo.open("rb")
        except (FileNotFoundError, OSError, ValueError, SuspiciousFileOperation):
            raise NotFound("Proof not found.")
        response = FileResponse(handle, as_attachment=False, filename=os.path.basename(proof.photo.name))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class RatingViewSet(viewsets.ModelViewSet):
    serializer_class = RatingSerializer
    permission_classes = [IsAuthenticated]
    queryset = Rating.objects.select_related("order", "author").order_by("-created_at", "-id")
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.role == "admin" or user.is_superuser:
            return self.queryset
        if user.role == "merchant":
            return self.queryset.filter(target_type="merchant", order__merchant__user=user)
        if user.role == "captain":
            return self.queryset.filter(target_type="captain", order__captain__user=user)
        return self.queryset.filter(author=user)

    def create(self, request, *args, **kwargs):
        if request.user.role != "customer":
            raise PermissionDenied("Only customers can submit order ratings.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data["order"].pk
        target_type = serializer.validated_data["target_type"]
        score = serializer.validated_data["score"]
        comment = serializer.validated_data.get("comment", "")

        with transaction.atomic():
            order = Order.objects.select_for_update().filter(pk=order_id).first()
            if order is None:
                raise NotFound("Order not found.")
            if order.customer_id != request.user.id:
                raise PermissionDenied("You can only rate your own orders.")
            if order.status != "completed":
                raise ValidationError({"order": "Only completed orders can be rated."})
            if target_type == "captain":
                if order.captain_id is None:
                    raise ValidationError({"target_type": "This order has no assigned captain."})
                profile = order.captain
                ratings = Rating.objects.filter(target_type="captain", order__captain=profile)
            elif target_type == "merchant":
                if order.order_type != "store" or order.merchant_id is None:
                    raise ValidationError({"target_type": "Only store orders can rate a merchant."})
                profile = order.merchant
                ratings = Rating.objects.filter(target_type="merchant", order__merchant=profile)
            else:
                raise ValidationError({"target_type": "Choose captain or merchant."})

            rating, created = Rating.objects.get_or_create(
                order=order,
                author=request.user,
                target_type=target_type,
                defaults={"score": score, "comment": comment},
            )
            if not created:
                rating.score = score
                rating.comment = comment
                rating.save(update_fields=["score", "comment"])
            average = ratings.aggregate(value=Avg("score"))["value"]
            profile.rating = (
                Decimal(str(average)).quantize(Decimal("0.01"))
                if average is not None
                else Decimal("5.00")
            )
            profile.save(update_fields=["rating"])

        response = self.get_serializer(rating).data
        return Response(response, status=201 if created else 200)


class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer
    permission_classes = [IsAuthenticated]
    queryset = CashSettlement.objects.select_related("order", "merchant", "captain").all()
    def get_queryset(self):
        u = self.request.user
        if u.role == "admin" or u.is_finance_staff or u.is_superuser: return self.queryset
        if u.role == "merchant":
            access = merchant_access(u)
            return self.queryset.filter(merchant=access.merchant) if access else self.queryset.none()
        if u.role == "captain": return self.queryset.filter(captain__user=u)
        return self.queryset.none()
    http_method_names = ["get", "post", "head", "options"]

    def _is_finance_admin(self, user):
        return user.role == "admin" or user.is_finance_staff or user.is_superuser

    def _receipt_data(self, receipt):
        return {
            "id": receipt.id,
            "reference": receipt.reference,
            "captain_id": receipt.captain_id,
            "captain_name": receipt.captain.user.get_full_name() or receipt.captain.user.username,
            "amount": str(receipt.amount),
            "recorded_by": receipt.recorded_by.get_full_name() or receipt.recorded_by.username if receipt.recorded_by else None,
            "created_at": receipt.created_at.isoformat(),
            "notes": receipt.notes,
            "allocations": [{
                "order_id": allocation.settlement.order_id,
                "order_number": allocation.settlement.order.ensure_order_number(),
                "amount": str(allocation.amount),
            } for allocation in receipt.allocations.select_related("settlement").all()],
        }

    @action(detail=False, methods=["get"])
    def ledger(self, request):
        qs = self.queryset.filter(
            order__status="completed",
            order__payment_method="cash",
            order__order_type="store",
        )
        if request.user.role == "merchant":
            access = merchant_access(request.user)
            if access is None or not access.can("reports"):
                raise PermissionDenied("Your staff role cannot view settlements.")
            qs = qs.filter(merchant=access.merchant)
        elif request.user.role == "captain":
            qs = qs.filter(captain__user=request.user)
        elif not self._is_finance_admin(request.user):
            raise PermissionDenied("Cash settlement access is limited to merchants, captains, and finance staff.")

        rows = []
        for settlement in qs.select_related("order", "merchant", "captain__user").prefetch_related("allocations"):
            allocated = sum((allocation.amount for allocation in settlement.allocations.all()), Decimal("0.00"))
            settled = min(settlement.amount, max(allocated, settlement.amount if settlement.closed else Decimal("0.00")))
            outstanding = max(settlement.amount - settled, Decimal("0.00"))
            rows.append({
                "id": settlement.id,
                "order_id": settlement.order_id,
                "order_number": settlement.order.ensure_order_number(),
                "captain_id": settlement.captain_id,
                "captain_name": settlement.captain.user.get_full_name() or settlement.captain.user.username,
                "merchant_name": settlement.merchant.shop_name,
                "amount": str(settlement.amount),
                "settled_amount": str(settled),
                "outstanding_amount": str(outstanding),
                "status": "settled" if outstanding == 0 else "partial" if settled > 0 else "outstanding",
                "created_at": settlement.created_at.isoformat(),
            })

        receipts = CashSettlementReceipt.objects.select_related("captain__user", "recorded_by").prefetch_related(
            "allocations__settlement"
        )
        if request.user.role == "captain":
            receipts = receipts.filter(captain__user=request.user)
        elif request.user.role == "merchant":
            access = merchant_access(request.user)
            if access is None:
                receipts = receipts.none()
            else:
                receipts = receipts.filter(allocations__settlement__merchant=access.merchant).distinct()
        else:
            receipts = receipts.order_by("-created_at")
        serialized_receipts = [self._receipt_data(receipt) for receipt in receipts[:200]]
        due = sum((Decimal(row["amount"]) for row in rows), Decimal("0.00"))
        settled_total = sum((Decimal(row["settled_amount"]) for row in rows), Decimal("0.00"))
        response = {
            "orders": rows,
            "receipts": serialized_receipts,
            "total_due": str(due),
            "total_settled": str(settled_total),
            "outstanding": str(due - settled_total),
        }
        if self._is_finance_admin(request.user):
            response["captains"] = [{
                "id": captain.id,
                "name": captain.user.get_full_name() or captain.user.username,
            } for captain in CaptainProfile.objects.select_related("user").order_by("user__first_name", "user__last_name")]
        return Response(response)

    @action(detail=False, methods=["get", "post"])
    def receipts(self, request):
        if not self._is_finance_admin(request.user):
            raise PermissionDenied("Only finance staff can record or view cash receipts.")
        if request.method == "GET":
            receipts = CashSettlementReceipt.objects.select_related(
                "captain__user", "recorded_by"
            ).prefetch_related("allocations__settlement")[:200]
            return Response([self._receipt_data(receipt) for receipt in receipts])

        try:
            captain_id = int(request.data.get("captain_id"))
            raw_amount = Decimal(str(request.data.get("amount", "")))
            order_ids = request.data.get("order_ids")
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Enter a captain, valid amount, and order IDs.")
        if not raw_amount.is_finite():
            raise ValidationError({"amount": "Receipt amount must be a finite decimal value."})
        try:
            amount = raw_amount.quantize(Decimal("0.01"))
        except InvalidOperation:
            raise ValidationError({"amount": "Enter a valid amount with at most two decimal places."})
        if amount != raw_amount:
            raise ValidationError({"amount": "Enter an amount with at most two decimal places."})
        reference = str(request.data.get("reference", "")).strip()
        notes = str(request.data.get("notes", "")).strip()
        if not reference or len(reference) > 100:
            raise ValidationError({"reference": "Enter a unique transaction reference (up to 100 characters)."})
        if not amount.is_finite() or amount <= 0 or amount > Decimal("99999999.99"):
            raise ValidationError({"amount": "Receipt amount must be greater than zero and within the supported range."})
        if not isinstance(order_ids, list) or not order_ids:
            raise ValidationError({"order_ids": "Select at least one completed cash order."})
        try:
            order_ids = [int(order_id) for order_id in order_ids]
        except (TypeError, ValueError):
            raise ValidationError({"order_ids": "Order IDs must be integers."})
        if len(set(order_ids)) != len(order_ids):
            raise ValidationError({"order_ids": "Do not repeat order IDs."})

        try:
            with transaction.atomic():
                existing = CashSettlementReceipt.objects.filter(reference=reference).first()
                if existing:
                    existing_order_ids = set(existing.allocations.values_list("settlement__order_id", flat=True))
                    if (
                        existing.captain_id == captain_id
                        and existing.amount == amount
                        and existing.recorded_by_id == request.user.id
                        and existing.notes == notes[:500]
                        and existing_order_ids == set(order_ids)
                    ):
                        return Response(self._receipt_data(existing), status=200)
                    return Response({"detail": "This transaction reference is already in use."}, status=409)

                captain = CaptainProfile.objects.select_related("user").get(pk=captain_id)
                settlements = list(
                    CashSettlement.objects.select_for_update()
                    .filter(
                        order_id__in=order_ids,
                        captain=captain,
                        order__status="completed",
                        order__order_type="store",
                        order__payment_method="cash",
                    )
                    .select_related("order", "merchant")
                    .order_by("order_id")
                )
                if {row.order_id for row in settlements} != set(order_ids):
                    raise ValidationError({"order_ids": "Every selected order must be a completed cash store order assigned to this captain."})

                existing = CashSettlementReceipt.objects.filter(reference=reference).first()
                if existing:
                    existing_order_ids = set(existing.allocations.values_list("settlement__order_id", flat=True))
                    if (
                        existing.captain_id == captain_id
                        and existing.amount == amount
                        and existing.recorded_by_id == request.user.id
                        and existing.notes == notes[:500]
                        and existing_order_ids == set(order_ids)
                    ):
                        return Response(self._receipt_data(existing), status=200)
                    return Response({"detail": "This transaction reference is already in use."}, status=409)

                balances = {}
                available = Decimal("0.00")
                for settlement in settlements:
                    allocated = CashSettlementAllocation.objects.filter(settlement=settlement).aggregate(
                        total=Sum("amount")
                    )["total"] or Decimal("0.00")
                    settled = max(allocated, settlement.amount if settlement.closed else Decimal("0.00"))
                    balance = max(settlement.amount - settled, Decimal("0.00"))
                    balances[settlement.id] = balance
                    available += balance
                if amount > available:
                    raise ValidationError({"amount": f"Receipt exceeds the selected orders' outstanding balance ({available:.2f})."})

                receipt = CashSettlementReceipt.objects.create(
                    captain=captain,
                    recorded_by=request.user,
                    amount=amount,
                    reference=reference,
                    notes=notes[:500],
                )
                remaining = amount
                for settlement in settlements:
                    allocation_amount = min(remaining, balances[settlement.id])
                    if allocation_amount > 0:
                        CashSettlementAllocation.objects.create(
                            receipt=receipt,
                            settlement=settlement,
                            amount=allocation_amount,
                        )
                        remaining -= allocation_amount
                    if remaining == 0:
                        break
        except CaptainProfile.DoesNotExist:
            raise NotFound("Captain profile not found.")

        return Response(self._receipt_data(receipt), status=201)
    def create(self, request, *args, **kwargs):
        order_id = request.data.get("order")
        try:
            order = Order.objects.get(
                pk=order_id,
                payment_method="cash",
                status="completed",
                order_type="store",
            )
        except (Order.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Only completed cash store orders can be reconciled."}, status=404)
        if not order.merchant or not order.captain: return Response({"detail": "Order needs a merchant and captain."}, status=400)
        if request.user.role == "merchant" and order.merchant.user_id != request.user.id:
            raise PermissionDenied()
        if request.user.role == "captain" and order.captain.user_id != request.user.id:
            raise PermissionDenied()
        if request.user.role not in ["admin", "merchant", "captain"]: raise PermissionDenied()
        obj, _ = CashSettlement.objects.get_or_create(order=order, defaults={"merchant": order.merchant, "captain": order.captain, "amount": order.subtotal, "reference": uuid.uuid4().hex[:12].upper()})
        return Response(self.get_serializer(obj).data, status=201)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return Response(
            {"detail": "Record cash collected from captains through POST /api/settlements/receipts/."},
            status=410,
        )

class DelayReportViewSet(viewsets.ModelViewSet):
    serializer_class = DelayReportSerializer
    permission_classes = [IsAuthenticated]
    queryset = DelayReport.objects.all()
    http_method_names = ["get", "post", "head", "options"]
    def get_queryset(self):
        if self.request.user.role == "admin": return self.queryset
        if self.request.user.role == "captain": return self.queryset.filter(captain__user=self.request.user)
        return self.queryset.none()
    def perform_create(self, serializer):
        if self.request.user.role != "captain":
            raise PermissionDenied("Only captains can report merchant delays.")
        captain = CaptainProfile.objects.get(user=self.request.user)
        order = serializer.validated_data.get("order")
        if not order or order.captain_id != captain.id or order.order_type != "store":
            raise ValidationError({"order": "Choose a store order assigned to you."})
        if not order.merchant_arrived_at:
            raise ValidationError({"order": "Report your arrival first."})
        elapsed = (timezone.now() - order.merchant_arrived_at).total_seconds()
        if elapsed < 10 * 60:
            remaining = max(1, math.ceil((10 * 60 - elapsed) / 60))
            raise ValidationError({"detail": f"The free waiting period has not ended. {remaining} minute(s) remain."})
        if DelayReport.objects.filter(order=order, captain=captain).exists():
            raise ValidationError({"order": "A delay report already exists for this order."})
        serializer.save(captain=captain, arrived_at=order.merchant_arrived_at,
                        wait_minutes=max(10, math.floor(elapsed / 60)))

class SupportTicketViewSet(viewsets.ModelViewSet):
    serializer_class = SupportTicketSerializer
    permission_classes = [IsAuthenticated]
    queryset = SupportTicket.objects.all()
    def get_queryset(self):
        user = self.request.user
        return self.queryset if user.role == "admin" or user.is_superuser else self.queryset.filter(user=user)

    def perform_create(self, serializer):
        order = serializer.validated_data.get("order")
        if not order:
            serializer.save(user=self.request.user)
            return
        user = self.request.user
        authorized = (
            user.role == "admin" or user.is_superuser
            or order.customer_id == user.id
            or (order.captain_id and order.captain.user_id == user.id)
            or (order.merchant_id and order.merchant.user_id == user.id)
        )
        if not authorized:
            raise PermissionDenied("You can only report an order you are involved in.")
        with transaction.atomic():
            order = Order.objects.select_for_update(of=("self",)).get(pk=order.pk)
            serializer.save(user=user, order=order)

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user)
        if request.query_params.get("unread") in ("1", "true", "yes"):
            qs = qs.filter(is_read=False)
        return Response({
            "results": NotificationSerializer(qs[:100], many=True).data,
            "unread": Notification.objects.filter(user=request.user, is_read=False).count(),
        })

class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id=None):
        qs = Notification.objects.filter(user=request.user)
        if notification_id is None:
            updated = qs.filter(is_read=False).update(is_read=True)
            return Response({"updated": updated, "unread": 0})
        row = qs.filter(pk=notification_id).first()
        if row is None:
            raise NotFound("Notification not found.")
        if not row.is_read:
            row.is_read = True
            row.save(update_fields=["is_read"])
        return Response(NotificationSerializer(row).data)

class MerchantReportsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "merchant":
            raise PermissionDenied("Merchant account required.")
        access = merchant_access(request.user)
        if access is None or not access.can("reports"):
            raise PermissionDenied("Your staff role cannot view reports.")
        merchant = access.merchant
        today = timezone.localdate()
        orders = Order.objects.filter(merchant=merchant)
        today_orders = orders.filter(created_at__date=today)
        completed_today = today_orders.filter(status="completed")
        gross = completed_today.aggregate(value=Sum("total"))["value"] or Decimal("0.00")
        settlements = CashSettlement.objects.filter(
            merchant=merchant, order__status="completed", order__payment_method="cash",
            order__order_type="store",
        ).select_related("captain__user", "order").prefetch_related("allocations").order_by("-created_at")
        settlement_rows = []
        for row in settlements:
            allocated = sum((allocation.amount for allocation in row.allocations.all()), Decimal("0.00"))
            settled = min(row.amount, max(allocated, row.amount if row.closed else Decimal("0.00")))
            settlement_rows.append({
                "id": row.id, "reference": row.reference, "order_id": row.order_id,
                "order_number": row.order.ensure_order_number(),
                "captain_name": row.captain.user.get_full_name() or row.captain.user.username,
                "amount": str(row.amount), "settled_amount": str(settled),
                "outstanding_amount": str(row.amount - settled),
                "confirmed_by_merchant": row.confirmed_by_merchant,
                "confirmed_by_captain": row.confirmed_by_captain, "closed": row.closed,
                "created_at": row.created_at.isoformat(), "closed_at": row.closed_at.isoformat() if row.closed_at else None,
            })
        return Response({
            "date": today.isoformat(), "orders_today": today_orders.count(),
            "completed_today": completed_today.count(), "gross_sales_today": str(gross),
            # Commission/subscription deductions cannot be inferred until the platform defines a rate/rule.
            "net_sales_today": None, "net_sales_note": "Commission rules are not configured; net earnings are not calculated.",
            "cash_settlements": settlement_rows,
            "cash_products_due": str(sum((Decimal(row["outstanding_amount"]) for row in settlement_rows), Decimal("0.00"))),
            "all_orders": OrderSerializer(orders.order_by("-created_at")[:100], many=True, context={"request": request}).data,
        })


class AdminStoresView(APIView):
    permission_classes = [IsAuthenticated]

    def check_admin(self, request):
        require_admin_permission(request, "providers")

    def get(self, request):
        self.check_admin(request)
        rows = []
        qs = MerchantProfile.objects.select_related("user").prefetch_related("products").order_by("-created_at")
        for store in qs:
            rows.append({
                "id": store.id, "user_id": store.user_id, "username": store.user.username,
                "owner_name": store.user.get_full_name() or store.user.username,
                "shop_name": store.shop_name, "category": store.category,
                "description": store.description, "address": store.address,
                "latitude": float(store.latitude) if store.latitude is not None else None,
                "longitude": float(store.longitude) if store.longitude is not None else None,
                "image": request.build_absolute_uri(store.image.url) if store.image else None,
                "cover_image": request.build_absolute_uri(store.cover_image.url) if store.cover_image else None,
                "is_open": store.is_open, "created_at": store.created_at.isoformat(),
                "product_count": store.products.count(),
                "products": [{"id": p.id, "name": p.name, "price": str(p.price),
                              "available": p.available,
                              "image": request.build_absolute_uri(p.image.url) if p.image else None}
                             for p in store.products.all()],
            })
        return Response(rows)

    def patch(self, request, store_id):
        self.check_admin(request)
        try:
            store = MerchantProfile.objects.get(pk=store_id)
        except MerchantProfile.DoesNotExist:
            raise NotFound("Store not found.")
        if "is_open" in request.data:
            store.is_open = as_bool(request.data["is_open"])
        for field in ("shop_name", "category", "description", "address", "opening_hours"):
            if field in request.data:
                setattr(store, field, str(request.data[field]).strip())
        store.save()
        return Response({"id": store.id, "is_open": store.is_open, "shop_name": store.shop_name})


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        require_admin_permission(request, "dashboard")
        today = timezone.localdate()
        orders = Order.objects.filter(created_at__date=today)
        return Response({
            "orders_today": orders.count(),
            "active_orders": Order.objects.filter(status__in=["new", "accepted", "preparing", "ready", "assigned", "picked_up", "delivering", "awaiting_confirmation"]).count(),
            "completed_today": orders.filter(status="completed").count(),
            "online_captains": len(eligible_captain_user_ids()),  # online AND eligible, per the central service
            "open_merchants": MerchantProfile.objects.filter(is_open=True).count(),
            "sales_today": str(orders.filter(status="completed").aggregate(v=Sum("total"))["v"] or 0),
            "open_tickets": SupportTicket.objects.filter(status="open").count(),
        })


class AdminOperationsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        require_admin_permission(request, "operations")
        captains = []
        profiles = CaptainProfile.objects.select_related("user").prefetch_related("user__subscriptions__payments").order_by("id")
        for p in profiles:
            captains.append(captain_status_row(p, evaluate_captain(p.user, p)))
        merchants = [{"id": p.id, "user_id": p.user_id, "username": p.user.username, "shop_name": p.shop_name, "category": p.category, "address": p.address, "is_open": p.is_open} for p in MerchantProfile.objects.select_related("user").all()]
        orders = [{
            "id": o.id, "order_number": o.ensure_order_number(), "status": o.status, "customer": o.customer.username,
            "merchant": o.merchant.shop_name if o.merchant else "—",
            "merchant_name": o.merchant.shop_name if o.merchant else "—",
            "captain": o.captain.user.username if o.captain else "—",
            "total": str(o.total), "created_at": o.created_at.isoformat(),
            "pickup_address": o.pickup_address, "dropoff_address": o.dropoff_address,
            "dropoff_notes": o.dropoff_notes,
            "pickup_latitude": float(o.pickup_latitude) if o.pickup_latitude is not None else None,
            "pickup_longitude": float(o.pickup_longitude) if o.pickup_longitude is not None else None,
            "dropoff_latitude": float(o.dropoff_latitude) if o.dropoff_latitude is not None else None,
            "dropoff_longitude": float(o.dropoff_longitude) if o.dropoff_longitude is not None else None,
            "captain_latitude": float(o.captain.current_latitude) if o.captain_id and o.captain.current_latitude is not None else None,
            "captain_longitude": float(o.captain.current_longitude) if o.captain_id and o.captain.current_longitude is not None else None,
            "captain_location_updated_at": o.captain.current_location_updated_at.isoformat() if o.captain_id and o.captain.current_location_updated_at else None,
        } for o in Order.objects.select_related("customer", "merchant", "captain__user").order_by("-created_at")[:50]]
        tickets = [{
            "id": x.id, "order_id": x.order_id,
            "order_number": x.order.ensure_order_number() if x.order_id else None,
            "subject": x.subject, "message": x.message, "status": x.status,
            "username": x.user.username, "created_at": x.created_at.isoformat(),
        } for x in SupportTicket.objects.select_related("user", "order").order_by("-created_at")[:50]]
        return Response({"captains": captains, "merchants": merchants, "orders": orders, "tickets": tickets})
    def patch(self, request):
        require_admin_permission(request, "operations")
        kind, obj_id, value = request.data.get("kind"), request.data.get("id"), request.data.get("value")
        try:
            if kind == "captain":
                return Response({"detail": "Use POST /api/admin/captains/<captain_profile_id>/approval/ to change captain approval."}, status=400)
            if kind == "merchant":
                obj = MerchantProfile.objects.get(pk=obj_id); obj.is_open = bool(value); obj.save(update_fields=["is_open"])
                return Response({"ok": True, "is_open": obj.is_open})
            if kind == "ticket":
                obj = SupportTicket.objects.get(pk=obj_id); obj.status = value if value in ["open", "in_review", "resolved"] else obj.status; obj.save(update_fields=["status"])
                return Response({"ok": True, "status": obj.status})
        except (MerchantProfile.DoesNotExist, SupportTicket.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Record not found."}, status=404)
        return Response({"detail": "Unsupported operation."}, status=400)


class AdminCaptainApprovalView(APIView):
    """Explicit approval endpoint.  The URL carries the CaptainProfile id (never a user id)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, captain_profile_id):
        require_admin_permission(request, "captains")
        status = request.data.get("status")
        if status not in APPROVAL_STATUSES:
            raise ValidationError({"status": "Choose approved, rejected or pending."})
        try:
            with transaction.atomic():
                profile = CaptainProfile.objects.select_for_update().select_related("user").get(pk=captain_profile_id)
                previous_status = approval_status(profile)
                if previous_status != status:
                    reason = str(request.data.get("reason", "")).strip()
                    if not reason:
                        raise ValidationError({"reason": "A reason is required when changing captain approval."})
                    if len(reason) > 1000:
                        raise ValidationError({"reason": "The reason must be 1000 characters or fewer."})
                    set_approval(profile, status)
                    AdminAccountAudit.objects.create(
                        target=profile.user,
                        changed_by=request.user,
                        action="captain_approval",
                        previous_value=previous_status,
                        new_value=status,
                        reason=reason,
                    )
                if "checkpoint_badge" in request.data:
                    profile.checkpoint_badge = as_bool(request.data["checkpoint_badge"])
                    profile.save(update_fields=["checkpoint_badge"])
        except CaptainProfile.DoesNotExist:
            return Response({"detail": "Captain profile not found."}, status=404)
        publish_captain_eligibility(profile.user)
        profile.refresh_from_db()
        return Response({"ok": True, **captain_status_row(profile, evaluate_captain(profile.user, profile))})


# ---------------------------------------------------------------------------
# Captain: services, weekly schedule and earnings
# ---------------------------------------------------------------------------
class CaptainScheduleView(APIView):
    """The captain's own weekly working windows (replace-all on PUT)."""
    permission_classes = [IsAuthenticated]

    def get_profile(self, request):
        if request.user.role != "captain":
            raise PermissionDenied("Captain account required.")
        try:
            return request.user.captain_profile
        except CaptainProfile.DoesNotExist:
            raise PermissionDenied("Captain profile not found.")

    def get(self, request):
        profile = self.get_profile(request)
        return Response({
            "windows": CaptainWorkingWindowSerializer(profile.working_windows.all(), many=True).data,
            "available_now": is_within_working_hours(profile),
            "uses_default_schedule": not profile.working_windows.exists(),
        })

    def put(self, request):
        profile = self.get_profile(request)
        rows = request.data.get("windows")
        if not isinstance(rows, list) or len(rows) > 40:
            raise ValidationError({"windows": "Send a list of at most 40 windows."})
        serializer = CaptainWorkingWindowSerializer(data=rows, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            profile.working_windows.all().delete()
            CaptainWorkingWindow.objects.bulk_create([
                CaptainWorkingWindow(captain=profile, **row)
                for row in serializer.validated_data
            ])
        publish_captain_eligibility(profile.user)
        return self.get(request)


class CaptainServicePreferenceView(APIView):
    """A captain may only toggle services an administrator already approved."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != "captain":
            raise PermissionDenied("Captain account required.")
        try:
            profile = request.user.captain_profile
        except CaptainProfile.DoesNotExist:
            raise PermissionDenied("Captain profile not found.")
        rows = request.data.get("services")
        if not isinstance(rows, list) or not rows:
            raise ValidationError({"services": "Send at least one service preference."})
        updated = []
        with transaction.atomic():
            for row in rows:
                service = str(row.get("service", "")).strip()
                if service not in SERVICE_CODES:
                    raise ValidationError({"service": f"Unknown service: {service}"})
                eligibility = CaptainServiceEligibility.objects.select_for_update().filter(
                    captain=profile, service=service
                ).first()
                if eligibility is None:
                    raise PermissionDenied(f"You are not approved for {service}.")
                if "accepting" in row:
                    eligibility.accepting = as_bool(row["accepting"])
                if "regions" in row:
                    regions = row["regions"]
                    if not isinstance(regions, list) or len(regions) > 10:
                        raise ValidationError({"regions": "Send at most 10 regions."})
                    allowed = eligibility.regions or []
                    chosen = [str(value).strip()[:40] for value in regions if str(value).strip()]
                    if allowed:
                        chosen = [value for value in chosen if value in allowed]
                    eligibility.regions = chosen
                eligibility.save(update_fields=["accepting", "regions", "updated_at"])
                updated.append(eligibility)
        publish_captain_eligibility(profile.user)
        return Response({
            "services": CaptainServiceEligibilitySerializer(updated, many=True).data,
            "eligibility": evaluate_captain(profile.user, profile),
        })


class CaptainEarningsView(APIView):
    """Earnings and settlement ledger for the authenticated captain."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "captain":
            raise PermissionDenied("Captain account required.")
        try:
            profile = request.user.captain_profile
        except CaptainProfile.DoesNotExist:
            raise PermissionDenied("Captain profile not found.")
        metrics = captain_metrics(profile)
        rows = []
        settlements = CashSettlement.objects.filter(captain=profile).select_related(
            "order", "merchant"
        ).prefetch_related("allocations").order_by("-created_at")[:100]
        for settlement in settlements:
            allocated = sum((row.amount for row in settlement.allocations.all()), Decimal("0.00"))
            settled = min(settlement.amount, max(allocated, settlement.amount if settlement.closed else Decimal("0.00")))
            rows.append({
                "id": settlement.id,
                "order_number": settlement.order.ensure_order_number(),
                "merchant_name": settlement.merchant.shop_name,
                "amount": str(settlement.amount),
                "settled_amount": str(settled),
                "outstanding_amount": str(max(settlement.amount - settled, Decimal("0.00"))),
                "status": "settled" if settled >= settlement.amount else "partial" if settled > 0 else "outstanding",
                "created_at": settlement.created_at.isoformat(),
            })
        completed = Order.objects.filter(captain=profile, status="completed").select_related("merchant").order_by("-completed_at")[:100]
        return Response({
            **metrics["earnings"],
            "completed_tasks": metrics["completed_tasks"],
            "average_completion_minutes": metrics["average_completion_minutes"],
            "settlements": rows,
            "outstanding_total": str(sum((Decimal(row["outstanding_amount"]) for row in rows), Decimal("0.00"))),
            "tasks": [{
                "order_number": order.ensure_order_number(),
                "service_type": order.resolved_service(),
                "delivery_fee": str(order.delivery_fee),
                "completed_at": order.completed_at.isoformat() if order.completed_at else None,
                "merchant_name": order.merchant.shop_name if order.merchant else None,
            } for order in completed],
        })


class AdminCaptainServicesView(APIView):
    """Administrator approval for one captain and one service (independent rows)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, captain_profile_id):
        self._check(request)
        try:
            profile = CaptainProfile.objects.get(pk=captain_profile_id)
        except CaptainProfile.DoesNotExist:
            raise NotFound("Captain profile not found.")
        return Response({
            "captain_profile_id": profile.id,
            "max_active_tasks": profile.max_active_tasks,
            "services": [
                {"service": code, "label": label,
                 **self._row(profile, code)}
                for code, label in SERVICE_CHOICES
            ],
        })

    def post(self, request, captain_profile_id):
        self._check(request)
        service = str(request.data.get("service", "")).strip()
        if service not in SERVICE_CODES:
            raise ValidationError({"service": "Choose a valid service."})
        status = str(request.data.get("status", "pending")).strip()
        if status not in dict(CaptainServiceEligibility.STATUSES):
            raise ValidationError({"status": "Choose pending, approved or suspended."})
        with transaction.atomic():
            profile = CaptainProfile.objects.select_for_update().select_related("user").filter(
                pk=captain_profile_id
            ).first()
            if profile is None:
                raise NotFound("Captain profile not found.")
            row, _ = CaptainServiceEligibility.objects.select_for_update().get_or_create(
                captain=profile, service=service
            )
            row.status = status
            if status == "approved":
                row.approved_by = request.user
                row.approved_at = timezone.now()
            for field in ("training_required", "training_completed", "document_verified"):
                if field in request.data:
                    setattr(row, field, as_bool(request.data[field]))
            if "regions" in request.data:
                regions = request.data["regions"]
                if not isinstance(regions, list) or len(regions) > 10:
                    raise ValidationError({"regions": "Send at most 10 regions."})
                row.regions = [str(value).strip()[:40] for value in regions if str(value).strip()]
            if "notes" in request.data:
                row.notes = str(request.data["notes"]).strip()[:500]
            row.save()
            if "max_active_tasks" in request.data:
                try:
                    limit = int(request.data["max_active_tasks"])
                except (TypeError, ValueError):
                    raise ValidationError({"max_active_tasks": "Enter a whole number."})
                if not 1 <= limit <= 10:
                    raise ValidationError({"max_active_tasks": "Choose between 1 and 10 active tasks."})
                profile.max_active_tasks = limit
                profile.save(update_fields=["max_active_tasks"])
            publish_captain_eligibility(profile.user)
        return Response({
            "service": service,
            "status": row.status,
            "eligibility": evaluate_captain(profile.user, profile),
            "max_active_tasks": profile.max_active_tasks,
        })

    def _check(self, request):
        require_admin_permission(request, "captains")

    def _row(self, profile, service):
        row = next((item for item in profile.service_eligibilities.all() if item.service == service), None)
        if row is None:
            return {"status": "none", "accepting": False, "active": False, "regions": [],
                    "training_required": False, "training_completed": False, "document_verified": False}
        return {
            "status": row.status, "accepting": row.accepting, "active": row.is_active,
            "regions": row.regions, "training_required": row.training_required,
            "training_completed": row.training_completed, "document_verified": row.document_verified,
        }

