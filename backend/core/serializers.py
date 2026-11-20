from rest_framework import serializers
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import *
from .services.merchant_access import ROLE_PERMISSIONS
from .validators import validate_image_upload

User = get_user_model()

# Every map component emits full-precision floats (e.g. 31.94993417521601), while
# the coordinate columns store 6 decimals. DRF validates max_digits before it
# quantizes, so raw floats are rejected; normalize them first on the way in.
COORDINATE_FIELDS = ("pickup_latitude", "pickup_longitude", "dropoff_latitude", "dropoff_longitude")
COORDINATE_QUANTUM = Decimal("0.000001")


def normalize_coordinate(value):
    """Round a raw map coordinate to the 6-decimal precision used by the models."""
    if value is None or value == "":
        return value
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return value
    if not number.is_finite():
        return value
    return number.quantize(COORDINATE_QUANTUM, rounding=ROUND_HALF_UP)


def normalize_coordinates(data, fields=COORDINATE_FIELDS):
    """Return a mutable copy of request data with coordinate fields quantized."""
    try:
        data = data.copy()
    except AttributeError:
        return data
    for field in fields:
        if field in data:
            data[field] = normalize_coordinate(data[field])
    return data


def _validate_latitude(value):
    if value is not None and not Decimal("-90") <= value <= Decimal("90"):
        raise serializers.ValidationError("Latitude must be between -90 and 90.")
    return value


def _validate_longitude(value):
    if value is not None and not Decimal("-180") <= value <= Decimal("180"):
        raise serializers.ValidationError("Longitude must be between -180 and 180.")
    return value


def _delete_replaced_upload(instance, field_name, previous_name):
    """Remove the old file only after the replacement has been stored."""
    if not previous_name or previous_name == getattr(instance, field_name).name:
        return
    instance._meta.get_field(field_name).storage.delete(previous_name)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "phone", "identity_number", "role", "language", "profile_image", "is_active", "is_finance_staff", "subscription_required", "must_change_password"]
        read_only_fields = ["is_finance_staff"]

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name", "last_name", "phone", "role", "language"]
    def validate_role(self, value):
        if value != "customer":
            raise serializers.ValidationError("Merchant, captain and admin accounts must be created or approved by an administrator.")
        return value
    def create(self, data):
        password = data.pop("password")
        return User.objects.create_user(password=password, **data)

class MerchantPublicSerializer(serializers.ModelSerializer):
    service_type = serializers.CharField(read_only=True)
    business_category_code = serializers.SerializerMethodField()
    branches = serializers.SerializerMethodField()

    class Meta:
        model = MerchantProfile
        fields = ["id", "shop_name", "image", "cover_image", "description", "category", "business_category_code", "address", "latitude", "longitude", "opening_hours", "is_open", "temporarily_closed", "rating", "service_type", "branches"]

    def get_business_category_code(self, obj):
        return obj.business_category.code if obj.business_category_id else ""

    def get_branches(self, obj):
        """Active branches a customer may choose at checkout."""
        return [
            {
                "id": branch.id,
                "name": branch.name,
                "address": branch.address,
                "phone": branch.phone,
                "latitude": None if branch.latitude is None else str(branch.latitude),
                "longitude": None if branch.longitude is None else str(branch.longitude),
                "opening_hours": branch.opening_hours,
            }
            for branch in obj.branches.filter(is_active=True).order_by("id")
        ]


class MerchantProfileSerializer(serializers.ModelSerializer):
    service_type = serializers.CharField(read_only=True)
    business_category_code = serializers.SerializerMethodField()
    is_approved = serializers.BooleanField(read_only=True)

    class Meta:
        model = MerchantProfile
        fields = ["id", "shop_name", "image", "cover_image", "description", "category", "business_category", "business_category_code", "address", "latitude", "longitude", "opening_hours", "is_open", "temporarily_closed", "prep_minutes", "rating", "service_type", "approval_status", "is_approved", "rejection_reason", "created_at"]
        read_only_fields = ["id", "is_open", "rating", "service_type", "approval_status", "is_approved", "rejection_reason", "created_at"]

    def get_business_category_code(self, obj):
        return obj.business_category.code if obj.business_category_id else ""

    def validate_shop_name(self, value):
        value = str(value or "").strip()
        if not value:
            raise serializers.ValidationError("Store name is required.")
        return value[:160]

    def validate_latitude(self, value):
        return _validate_latitude(value)

    def validate_longitude(self, value):
        return _validate_longitude(value)

    def to_internal_value(self, data):
        return super().to_internal_value(normalize_coordinates(data, ("latitude", "longitude")))

    def validate_image(self, value):
        return validate_image_upload(value)

    def validate_cover_image(self, value):
        return validate_image_upload(value)

    def validate(self, attrs):
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError("Provide both store coordinates.")
        category = attrs.get("business_category")
        if category is not None and not category.is_active:
            raise serializers.ValidationError({"business_category": "Choose an active business activity."})
        return attrs

    def update(self, instance, validated_data):
        previous = {
            field: getattr(instance, field).name
            for field in ("image", "cover_image")
            if field in validated_data and getattr(instance, field)
        }
        instance = super().update(instance, validated_data)
        for field, old_name in previous.items():
            _delete_replaced_upload(instance, field, old_name)
        return instance

class AvailabilityField(serializers.BooleanField):
    """Keep a product available when an HTML form omits the checkbox.

    DRF treats a missing checkbox in multipart input as False, which silently
    hid products created from the merchant form. Omitted values now use the
    model default (True); explicit values from any client are still honored,
    and partial updates that omit the field keep the stored value.
    """

    default_empty_html = True


class ProductSerializer(serializers.ModelSerializer):
    merchant_name = serializers.CharField(source="merchant.shop_name", read_only=True)
    stock_status = serializers.CharField(read_only=True)
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    discount_active = serializers.BooleanField(read_only=True)
    available = AvailabilityField(default=True)
    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["merchant", "pharmacy_review_status"]

    def validate(self, attrs):
        price = attrs.get("price", getattr(self.instance, "price", None))
        discount = attrs.get("discount_price", getattr(self.instance, "discount_price", None))
        if discount is not None and price is not None and discount >= price:
            raise serializers.ValidationError({"discount_price": "The offer price must be lower than the regular price."})
        starts = attrs.get("discount_starts_at", getattr(self.instance, "discount_starts_at", None))
        ends = attrs.get("discount_ends_at", getattr(self.instance, "discount_ends_at", None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError({"discount_ends_at": "The offer must end after it starts."})
        return attrs

    def validate_quantity(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value

    def validate_low_stock_threshold(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Low-stock threshold cannot be negative.")
        return value

    def validate_image(self, value):
        return validate_image_upload(value)

    def create(self, validated_data):
        # A product is only sellable against a real count. Omitting the field
        # used to leave quantity NULL, which meant "unlimited" at order time.
        if validated_data.get("quantity") is None:
            validated_data["quantity"] = 0
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "quantity" in validated_data and validated_data["quantity"] is None:
            validated_data["quantity"] = 0
        previous = instance.image.name if instance.image and "image" in validated_data else ""
        instance = super().update(instance, validated_data)
        _delete_replaced_upload(instance, "image", previous)
        return instance


class OrderActivitySerializer(serializers.ModelSerializer):
    actor_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderActivity
        fields = ["id", "event", "from_status", "to_status", "actor_id", "actor_name", "created_at"]
        read_only_fields = fields


class OrderProofSerializer(serializers.ModelSerializer):
    captured_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderProof
        fields = ["id", "kind", "recipient_name", "notes", "otp_verified", "captured_at", "captured_by_name"]
        read_only_fields = fields

    def get_captured_by_name(self, obj):
        return obj.captured_by.get_full_name() or obj.captured_by.username


class OrderSerializer(serializers.ModelSerializer):
    activities = OrderActivitySerializer(many=True, read_only=True)
    proofs = OrderProofSerializer(many=True, read_only=True)
    delivery_otp = serializers.SerializerMethodField()
    my_ratings = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="customer.get_full_name", read_only=True)
    customer_profile_image = serializers.SerializerMethodField()
    captain_profile_image = serializers.SerializerMethodField()
    captain_latitude = serializers.SerializerMethodField()
    captain_longitude = serializers.SerializerMethodField()
    captain_location_updated_at = serializers.SerializerMethodField()
    merchant_name = serializers.CharField(source="merchant.shop_name", read_only=True)
    captain_name = serializers.CharField(source="captain.user.get_full_name", read_only=True)
    captain_rating = serializers.DecimalField(
        source="captain.rating", max_digits=3, decimal_places=2, read_only=True, allow_null=True,
    )
    merchant_rating = serializers.DecimalField(
        source="merchant.rating", max_digits=3, decimal_places=2, read_only=True, allow_null=True,
    )
    merchant = serializers.PrimaryKeyRelatedField(queryset=MerchantProfile.objects.all(), required=False, allow_null=True)
    items = serializers.ListField(child=serializers.DictField(), required=False)

    def get_delivery_otp(self, obj):
        """Only the customer may see the delivery code (and only while active)."""
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return None
        if obj.customer_id != request.user.id or obj.delivery_otp_verified_at:
            return None
        return obj.delivery_otp or None

    def get_customer_profile_image(self, obj):
        return self._profile_url(obj.customer)

    def get_captain_profile_image(self, obj):
        return self._profile_url(obj.captain.user) if obj.captain_id else None

    def get_captain_latitude(self, obj):
        return obj.captain.current_latitude if obj.captain_id and obj.status in ("assigned", "picked_up", "delivering") else None

    def get_captain_longitude(self, obj):
        return obj.captain.current_longitude if obj.captain_id and obj.status in ("assigned", "picked_up", "delivering") else None

    def get_captain_location_updated_at(self, obj):
        return obj.captain.current_location_updated_at if obj.captain_id and obj.status in ("assigned", "picked_up", "delivering") else None

    def _profile_url(self, user):
        if not user.profile_image:
            return None
        request = self.context.get("request")
        url = user.profile_image.url
        return request.build_absolute_uri(url) if request else url

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = [
            "order_number", "customer", "captain", "status", "accepted_at", "captain_accepted_at",
            "ready_at", "captain_delivered_at", "completed_at", "completed_by",
            "completed_by_name", "completion_method", "created_at", "updated_at", "total", "subtotal",
            "request_key", "service_type", "cancellation_reason", "delivery_otp_verified_at",
            "proofs", "service_details",
        ]

    def to_representation(self, instance):
        instance.ensure_order_number()
        return super().to_representation(instance)

    def get_my_ratings(self, obj):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return []
        return [
            {"target_type": rating.target_type, "score": rating.score, "comment": rating.comment}
            for rating in obj.ratings.all()
            if rating.author_id == request.user.id
        ]

    def to_internal_value(self, data):
        return super().to_internal_value(normalize_coordinates(data))

    def validate_pickup_latitude(self, value):
        return _validate_latitude(value)

    def validate_pickup_longitude(self, value):
        return _validate_longitude(value)

    def validate_dropoff_latitude(self, value):
        return _validate_latitude(value)

    def validate_dropoff_longitude(self, value):
        return _validate_longitude(value)

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.method == "POST":
            if request.user.role != "customer":
                raise serializers.ValidationError("Only customers can create orders.")
            order_type = attrs.get("order_type", "store")
            if order_type == "ride":
                raise serializers.ValidationError("Use the dedicated /orders/ride/ endpoint to create a ride request.")
            if order_type != "store":
                raise serializers.ValidationError("Parcel requests are not enabled in this release.")
            if order_type == "store":
                merchant = attrs.get("merchant")
                if not merchant:
                    raise serializers.ValidationError({"merchant": "Choose an open merchant."})
                service = str(request.data.get("service_code") or merchant.service_type).strip()
                if service not in SERVICE_CODES:
                    raise serializers.ValidationError({"service_code": "Choose a supported service."})
                if service != merchant.service_type and not merchant.services.filter(code=service).exists():
                    raise serializers.ValidationError({"service_code": "This merchant is not approved for that service."})
                if merchant.approval_status != "approved":
                    raise serializers.ValidationError({"merchant": "This store is awaiting Waselni approval."})
                if not PlatformService.is_offered(service):
                    raise serializers.ValidationError({"merchant": "This service is paused by Waselni administration."})
                from .services.merchant_access import store_open_state
                open_now, closed_reason = store_open_state(merchant)
                if not open_now:
                    message = (
                        "This store is outside its opening hours."
                        if closed_reason == "outside_hours" else "Choose an open merchant."
                    )
                    raise serializers.ValidationError({"merchant": message})
                if merchant.latitude is None or merchant.longitude is None:
                    raise serializers.ValidationError({"merchant": "The store must set its map location before accepting delivery orders."})
                raw_items = attrs.get("items", [])
                if not raw_items:
                    raise serializers.ValidationError({"items": "Add at least one product."})
                normalized, subtotal = [], 0
                for row in raw_items:
                    try:
                        product_id, quantity = int(row.get("product_id")), int(row.get("quantity", 1))
                    except (TypeError, ValueError):
                        raise serializers.ValidationError({"items": "Each item needs product_id and quantity."})
                    if quantity < 1 or quantity > 50:
                        raise serializers.ValidationError({"items": "Quantity must be between 1 and 50."})
                    try:
                        product = Product.objects.get(pk=product_id, merchant=merchant, available=True)
                    except Product.DoesNotExist:
                        raise serializers.ValidationError({"items": f"Product {product_id} is unavailable."})
                    if service == "pharmacy" and (
                        product.pharmacy_review_status != "approved"
                        or product.prescription_required or product.controlled_substance
                    ):
                        raise serializers.ValidationError({"items": f"Product {product_id} requires a prescription or is not available for online ordering."})
                    # The final quantity check runs inside the creation transaction
                    # (reserve_stock) so concurrent orders cannot oversell. The price
                    # is always the server-side effective price, never a client value.
                    unit_price = product.effective_price
                    line = unit_price * quantity
                    subtotal += line
                    normalized.append({
                        "product_id": product.id, "name": product.name, "quantity": quantity,
                        "unit_price": str(unit_price), "line_total": str(line),
                        "stock_tracked": product.quantity is not None,
                    })
                attrs["items"] = normalized
                attrs["subtotal"] = subtotal
                # Persist the merchant pickup point on every store order so admin,
                # merchant and authorized delivery views share the same origin.
                attrs["pickup_address"] = merchant.address or merchant.shop_name
                attrs["pickup_latitude"] = normalize_coordinate(merchant.latitude)
                attrs["pickup_longitude"] = normalize_coordinate(merchant.longitude)
                attrs["service_type"] = service
                selected_branch = attrs.get("branch")
                if selected_branch is not None and (
                    selected_branch.merchant_id != merchant.id or not selected_branch.is_active
                ):
                    raise serializers.ValidationError(
                        {"branch": "Choose one of this store's active branches."}
                    )
                # The customer may pick the branch; otherwise the store's first
                # active branch keeps legacy clients working unchanged.
                attrs["branch"] = (
                    selected_branch
                    or merchant.branches.filter(is_active=True).order_by("id").first()
                )
                dlat = attrs.get("dropoff_latitude")
                dlon = attrs.get("dropoff_longitude")
                if dlat is None or dlon is None:
                    raise serializers.ValidationError({"location": "Select the customer's delivery point on the map."})
                raw_fee = attrs.get("delivery_fee")
                if raw_fee is None:
                    raise serializers.ValidationError({"delivery_fee": "Enter the delivery price before sending the order to captains."})
                try:
                    delivery_fee = Decimal(str(raw_fee)).quantize(Decimal("0.01"))
                except Exception:
                    raise serializers.ValidationError({"delivery_fee": "Enter a valid delivery price."})
                if not delivery_fee.is_finite() or delivery_fee < Decimal("0.50") or delivery_fee > Decimal("500.00"):
                    raise serializers.ValidationError({"delivery_fee": "Delivery price must be between 0.50 and 500.00 ILS."})
                attrs["delivery_fee"] = delivery_fee
                attrs["checkpoint_fee"] = Decimal("0.00")
                attrs["total"] = subtotal + delivery_fee
        return attrs

class SettlementSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = CashSettlement
        fields = "__all__"
        read_only_fields = ["reference", "closed", "closed_at", "order_number"]

    def get_order_number(self, obj):
        return obj.order.ensure_order_number()


class DelayReportSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = DelayReport
        fields = "__all__"
        read_only_fields = ["captain", "reviewed", "reported_at", "order_number"]

    def get_order_number(self, obj):
        return obj.order.ensure_order_number()


class SupportTicketSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = "__all__"
        read_only_fields = ["user", "status", "created_at", "updated_at", "order_number",
                            "assigned_to", "priority", "resolution"]

    def get_order_number(self, obj):
        return obj.order.ensure_order_number() if obj.order_id else None


class NotificationSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = ["user", "event", "order", "payload", "created_at", "order_number"]

    def get_order_number(self, obj):
        return obj.order.ensure_order_number() if obj.order_id else None


class RatingSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = Rating
        fields = ["id", "order", "order_number", "target_type", "score", "comment", "created_at"]
        read_only_fields = ["id", "order_number", "created_at"]

    def get_order_number(self, obj):
        return obj.order.ensure_order_number()

    def validate_score(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Score must be between 1 and 5.")
        return value


class CaptainServiceEligibilitySerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)
    service_label = serializers.CharField(source="get_service_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CaptainServiceEligibility
        fields = [
            "id", "service", "service_label", "status", "status_label", "accepting",
            "regions", "training_required", "training_completed", "document_verified",
            "notes", "approved_at", "updated_at", "is_active",
        ]
        read_only_fields = ["id", "approved_at", "updated_at", "is_active", "service_label", "status_label"]


class CaptainWorkingWindowSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaptainWorkingWindow
        fields = ["id", "weekday", "start_time", "end_time", "is_break"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": "The window must end after it starts."})
        return attrs


class MerchantBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantBranch
        fields = [
            "id", "name", "address", "phone", "latitude", "longitude",
            "opening_hours", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_latitude(self, value):
        return _validate_latitude(value)

    def validate_longitude(self, value):
        return _validate_longitude(value)

    def to_internal_value(self, data):
        return super().to_internal_value(normalize_coordinates(data, ("latitude", "longitude")))

    def validate(self, attrs):
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError("Provide both branch coordinates.")
        return attrs


class MerchantStaffSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    name = serializers.CharField(source="user.get_full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = MerchantStaff
        fields = ["id", "user", "username", "name", "phone", "role", "is_active", "permissions", "created_at"]
        read_only_fields = ["id", "user", "username", "name", "phone", "permissions", "created_at"]

    def get_permissions(self, obj):
        return sorted(ROLE_PERMISSIONS.get(obj.role, set()))


class MerchantHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantHours
        fields = ["id", "branch", "weekday", "opens_at", "closes_at", "is_closed"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        is_closed = attrs.get("is_closed", getattr(self.instance, "is_closed", False))
        opens = attrs.get("opens_at", getattr(self.instance, "opens_at", None))
        closes = attrs.get("closes_at", getattr(self.instance, "closes_at", None))
        if not is_closed:
            if not opens or not closes:
                raise serializers.ValidationError({"hours": "Set opening and closing times, or mark the day closed."})
            if closes <= opens:
                raise serializers.ValidationError({"closes_at": "Closing time must be after opening time."})
        return attrs


class StoreClosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreClosure
        fields = ["id", "branch", "date", "reason", "created_at"]
        read_only_fields = ["id", "created_at"]


class InventoryMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    order_number = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = InventoryMovement
        fields = [
            "id", "product", "product_name", "order", "order_number", "actor_name",
            "delta", "quantity_before", "quantity_after", "reason", "note", "created_at",
        ]
        read_only_fields = fields

    def get_order_number(self, obj):
        return obj.order.ensure_order_number() if obj.order_id else None

    def get_actor_name(self, obj):
        if not obj.actor_id:
            return "Automatic" if obj.reason in ("order", "cancel") else None
        return obj.actor.get_full_name() or obj.actor.username


class PriceChangeSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PriceChange
        fields = [
            "id", "product", "product_name", "changed_by_name", "old_price",
            "new_price", "old_discount", "new_discount", "reason", "created_at",
        ]
        read_only_fields = fields

    def get_changed_by_name(self, obj):
        if not obj.changed_by_id:
            return None
        return obj.changed_by.get_full_name() or obj.changed_by.username
