from rest_framework import serializers
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import *
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
    class Meta:
        model = MerchantProfile
        fields = ["id", "shop_name", "image", "cover_image", "description", "category", "address", "latitude", "longitude", "is_open", "rating"]

class MerchantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantProfile
        fields = ["id", "shop_name", "image", "cover_image", "description", "category", "address", "latitude", "longitude", "opening_hours", "is_open", "rating"]
        read_only_fields = ["id", "is_open", "rating"]

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
    available = AvailabilityField(default=True)
    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["merchant"]

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


class OrderSerializer(serializers.ModelSerializer):
    activities = OrderActivitySerializer(many=True, read_only=True)
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
            "request_key",
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
                if not merchant or not merchant.is_open:
                    raise serializers.ValidationError({"merchant": "Choose an open merchant."})
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
                    # The final quantity check runs inside the creation transaction
                    # (reserve_stock) so concurrent orders cannot oversell.
                    line = product.price * quantity
                    subtotal += line
                    normalized.append({
                        "product_id": product.id, "name": product.name, "quantity": quantity,
                        "unit_price": str(product.price), "line_total": str(line),
                        "stock_tracked": product.quantity is not None,
                    })
                attrs["items"] = normalized
                attrs["subtotal"] = subtotal
                # Persist the merchant pickup point on every store order so admin,
                # merchant and authorized delivery views share the same origin.
                attrs["pickup_address"] = merchant.address or merchant.shop_name
                attrs["pickup_latitude"] = normalize_coordinate(merchant.latitude)
                attrs["pickup_longitude"] = normalize_coordinate(merchant.longitude)
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
        read_only_fields = ["user", "status", "created_at", "order_number"]

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
