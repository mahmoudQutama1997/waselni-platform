import time

from django.db import OperationalError, connection, models, transaction
from django.db.models import F
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone

# Captain service catalogue. Each service is independently approved per captain.
SERVICE_CHOICES = [
    ("food", "Food delivery"),
    ("grocery", "Grocery & supermarket"),
    ("pharmacy", "Pharmacy"),
    ("parcel", "Parcels & documents"),
    ("ride", "Vespa rides"),
    ("logistics", "Special logistics"),
]
SERVICE_CODES = [code for code, _ in SERVICE_CHOICES]

# Merchant categories map to the service a captain must be approved for.
MERCHANT_CATEGORY_SERVICE = {
    "supermarket": "grocery",
    "grocery": "grocery",
    "pharmacy": "pharmacy",
    "restaurant": "food",
    "food": "food",
}


class User(AbstractUser):
    ROLE_CHOICES = [(x, x.title()) for x in ["customer","merchant","captain","admin"]]
    LANGUAGE_CHOICES = [("ar","العربية"),("he","עברית"),("en","English")]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer")
    # Granular role for internal admin staff (empty for every other account).
    ADMIN_ROLES = [
        ("super_admin", "Super admin"),
        ("operations", "Operations manager"),
        ("services", "Services manager"),
        ("merchants", "Merchants manager"),
        ("captains", "Captains manager"),
        ("regions", "Regions manager"),
        ("support", "Support agent"),
        ("finance", "Finance officer"),
        ("review", "Review & approval officer"),
    ]
    admin_role = models.CharField(max_length=20, choices=ADMIN_ROLES, blank=True, default="")
    phone = models.CharField(max_length=30, blank=True)
    identity_number = models.CharField(max_length=40, unique=True, null=True, blank=True)
    is_finance_staff = models.BooleanField(default=False)
    subscription_required = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES, default="ar")
    profile_image = models.ImageField(upload_to="profiles/", blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = "admin"
        super().save(*args, **kwargs)

class MerchantProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="merchant_profile")
    shop_name = models.CharField(max_length=160)
    image = models.ImageField(upload_to="stores/logos/", blank=True, null=True)
    cover_image = models.ImageField(upload_to="stores/covers/", blank=True, null=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=40, default="supermarket")
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    opening_hours = models.CharField(max_length=120, blank=True)
    is_open = models.BooleanField(default=True)
    # Pausing new orders without closing the store permanently.
    temporarily_closed = models.BooleanField(default=False)
    prep_minutes = models.PositiveSmallIntegerField(default=15)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5)
    APPROVAL_STATES = [("pending", "Pending"), ("approved", "Approved"), ("suspended", "Suspended"), ("rejected", "Rejected")]
    # Existing stores trade until reviewed; admin-created stores start pending.
    approval_status = models.CharField(max_length=12, choices=APPROVAL_STATES, default="approved")
    rejection_reason = models.CharField(max_length=500, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_merchants",
    )
    # Services this merchant is allowed to sell; empty means derive from category.
    services = models.ManyToManyField("PlatformService", blank=True, related_name="merchants")
    # Administrator-managed business activity. Stores on the service through the
    # category row, so the link is a database relation rather than string guessing.
    business_category = models.ForeignKey(
        "BusinessCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="merchants",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.shop_name

    @property
    def is_approved(self):
        return self.approval_status == "approved"

    @property
    def accepts_orders(self):
        return self.is_open and not self.temporarily_closed

    @property
    def service_type(self):
        linked = self.business_category.service if self.business_category_id else None
        if linked is not None:
            # A catalogue entry such as "Bakery" is executed by the implemented
            # store flow it is linked to, so orders and catalogue filters always
            # agree with the admin-managed activity.
            return linked.effective_code
        return MERCHANT_CATEGORY_SERVICE.get((self.category or "").strip().lower(), "food")


class BusinessCategory(models.Model):
    """A business activity line that maps a store to exactly one platform service.

    Administrators add and edit these rows; ``MerchantProfile.business_category``
    then gives every store a real foreign key to the service it trades under, so
    nothing downstream has to compare free-text category names.
    """

    code = models.CharField(max_length=40, unique=True)
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    service = models.ForeignKey(
        "PlatformService", on_delete=models.SET_NULL, null=True, blank=True, related_name="business_categories",
    )
    # Pharmacies and similar lines need a licence on file before approval.
    requires_license = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name_plural = "business categories"

    def __str__(self):
        return self.name_en

class CaptainProfile(models.Model):
    VEHICLES = [("car","Car"),("motorcycle","Motorcycle"),("truck","Truck")]
    PERMITS = [("jerusalem_id","Jerusalem ID"),("west_bank","West Bank"),("work_permit","Work Permit")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="captain_profile")
    vehicle_type = models.CharField(max_length=20, choices=VEHICLES, default="motorcycle")
    vehicle_model = models.CharField(max_length=100, blank=True)
    plate_number = models.CharField(max_length=30, blank=True)
    permit_type = models.CharField(max_length=30, choices=PERMITS, default="west_bank")
    checkpoint_badge = models.BooleanField(default=False)
    license_verified = models.BooleanField(default=False)
    insurance_verified = models.BooleanField(default=False)
    identity_document = models.FileField(upload_to="captain_documents/identity/", blank=True, null=True)
    driving_license_document = models.FileField(upload_to="captain_documents/licenses/", blank=True, null=True)
    insurance_document = models.FileField(upload_to="captain_documents/insurance/", blank=True, null=True)
    digital_undertaking_signed_at = models.DateTimeField(null=True, blank=True)
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    online = models.BooleanField(default=False)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5)
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_location_updated_at = models.DateTimeField(null=True, blank=True)
    # Dispatch capacity: how many tasks may be active at the same time.
    max_active_tasks = models.PositiveSmallIntegerField(default=1)


class CaptainServiceEligibility(models.Model):
    """Administrator-controlled approval for one captain and one service.

    ``status`` is the platform decision; ``accepting`` is the captain's own
    preference within the approved services. A missing row means the captain is
    not eligible for that service at all.
    """
    STATUSES = [("pending", "Pending"), ("approved", "Approved"), ("suspended", "Suspended")]
    captain = models.ForeignKey(CaptainProfile, on_delete=models.CASCADE, related_name="service_eligibilities")
    service = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    status = models.CharField(max_length=12, choices=STATUSES, default="pending")
    accepting = models.BooleanField(default=True)
    regions = models.JSONField(default=list, blank=True)
    training_required = models.BooleanField(default=False)
    training_completed = models.BooleanField(default=False)
    document_verified = models.BooleanField(default=False)
    notes = models.CharField(max_length=500, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["service"]
        constraints = [
            models.UniqueConstraint(fields=["captain", "service"], name="uniq_captain_service"),
        ]

    @property
    def is_active(self):
        return self.status == "approved" and (not self.training_required or self.training_completed)


class CaptainWorkingWindow(models.Model):
    """Recurring weekly availability window; a break is a window flagged ``is_break``."""
    captain = models.ForeignKey(CaptainProfile, on_delete=models.CASCADE, related_name="working_windows")
    weekday = models.PositiveSmallIntegerField()  # 0 = Monday … 6 = Sunday
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_break = models.BooleanField(default=False)

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(condition=models.Q(weekday__gte=0, weekday__lte=6), name="captain_window_weekday"),
        ]


class MerchantBranch(models.Model):
    """One physical branch of a merchant. Legacy stores keep a single default branch."""
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    opening_hours = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    region = models.ForeignKey(
        "ServiceRegion", on_delete=models.SET_NULL, null=True, blank=True, related_name="branches",
    )
    services = models.ManyToManyField("PlatformService", blank=True, related_name="branches")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.merchant.shop_name} · {self.name}"


class MerchantStaff(models.Model):
    """A non-owner employee of one merchant with a scoped role."""
    ROLES = [
        ("manager", "Manager"),
        ("orders", "Order desk"),
        ("preparation", "Preparation"),
        ("inventory", "Inventory"),
        ("reports", "Reports"),
    ]
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name="staff")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="merchant_staff_roles")
    role = models.CharField(max_length=20, choices=ROLES, default="orders")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["merchant", "user"], name="uniq_merchant_staff"),
            models.UniqueConstraint(fields=["user"], name="uniq_staff_single_merchant"),
        ]


class MerchantHours(models.Model):
    """Weekly opening hours for a merchant or one of its branches (branch wins)."""
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name="business_hours")
    branch = models.ForeignKey(MerchantBranch, on_delete=models.CASCADE, null=True, blank=True, related_name="business_hours")
    weekday = models.PositiveSmallIntegerField()
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(fields=["merchant", "branch", "weekday"], name="uniq_merchant_branch_weekday"),
        ]


class StoreClosure(models.Model):
    """A dated exception (holiday, maintenance) that closes the store for that day."""
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name="closures")
    branch = models.ForeignKey(MerchantBranch, on_delete=models.CASCADE, null=True, blank=True, related_name="closures")
    date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["merchant", "branch", "date"], name="uniq_store_closure_day"),
        ]


class Product(models.Model):
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    available = models.BooleanField(default=True)
    prescription_required = models.BooleanField(default=False)
    controlled_substance = models.BooleanField(default=False)
    PHARMACY_REVIEW_STATES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")]
    pharmacy_review_status = models.CharField(max_length=12, choices=PHARMACY_REVIEW_STATES, default="pending")
    # NULL means the product predates inventory tracking: it keeps selling on
    # the available flag alone. New products are created with an explicit count.
    quantity = models.PositiveIntegerField(null=True, blank=True)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    # Time-boxed promotion. The server is the only authority on the price the
    # customer is charged; the client displays ``effective_price``.
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_starts_at = models.DateTimeField(null=True, blank=True)
    discount_ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

    @property
    def discount_active(self):
        if self.discount_price is None:
            return False
        now = timezone.now()
        if self.discount_starts_at and self.discount_starts_at > now:
            return False
        if self.discount_ends_at and self.discount_ends_at < now:
            return False
        return self.discount_price < self.price

    @property
    def effective_price(self):
        return self.discount_price if self.discount_active else self.price

    @property
    def stock_status(self):
        if self.quantity is None:
            return "untracked"
        if self.quantity <= 0:
            return "out"
        if self.quantity <= self.low_stock_threshold:
            return "low"
        return "in"


class OrderNumberSequence(models.Model):
    last_number = models.PositiveBigIntegerField(default=0)


class Order(models.Model):
    TYPES = [("ride","Ride"),("parcel","Parcel"),("store","Store")]
    STATUSES = [(x,x.title()) for x in ["new","accepted","preparing","ready","assigned","picked_up","delivering","awaiting_confirmation","completed","cancelled"]]
    PAYMENT = [("cash","Cash"),("online","Online")]
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_orders")
    # Nullable for rolling-deploy compatibility; application reads and writes backfill legacy nulls.
    order_number = models.CharField(max_length=32, editable=False, blank=True, null=True)
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    captain = models.ForeignKey(CaptainProfile, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    order_type = models.CharField(max_length=20, choices=TYPES, default="store")
    # Service needed to execute this order; drives captain dispatch eligibility.
    service_type = models.CharField(max_length=20, choices=SERVICE_CHOICES, blank=True, default="")
    branch = models.ForeignKey(
        "MerchantBranch", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders",
    )
    REQUIRED_VEHICLES = [("any", "Any vehicle"), ("car", "Car"), ("motorcycle", "Motorcycle"), ("truck", "Truck")]
    required_vehicle = models.CharField(max_length=20, choices=REQUIRED_VEHICLES, default="any")
    status = models.CharField(max_length=24, choices=STATUSES, default="new")
    items = models.JSONField(default=list, blank=True)
    service_details = models.JSONField(default=dict, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    checkpoint_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT, default="cash")
    pickup_address = models.CharField(max_length=255, blank=True)
    dropoff_address = models.CharField(max_length=255, blank=True)
    dropoff_notes = models.TextField(blank=True)
    requires_checkpoint = models.BooleanField(default=False)
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    prep_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    captain_accepted_at = models.DateTimeField(null=True, blank=True)
    merchant_arrived_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    captain_delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="completed_orders")
    completed_by_name = models.CharField(max_length=150, blank=True)
    COMPLETION_METHODS = [("captain", "Captain"), ("customer", "Customer"), ("automatic", "Automatic")]
    completion_method = models.CharField(max_length=12, choices=COMPLETION_METHODS, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    request_key = models.CharField(max_length=64, null=True, blank=True)
    # Set exactly once when a cancelled order returns its reserved stock.
    stock_restored_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=500, blank=True)
    # Proof of fulfilment. The OTP is only ever returned to the customer.
    delivery_otp = models.CharField(max_length=6, blank=True)
    delivery_otp_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["customer", "request_key"], name="uniq_order_customer_request_key"),
            models.UniqueConstraint(fields=["order_number"], name="uniq_order_business_number"),
        ]

    @classmethod
    def _next_order_number(cls):
        for attempt in range(20):
            try:
                return cls._allocate_order_number()
            except OperationalError as exc:
                if (
                    connection.vendor != "sqlite"
                    or "locked" not in str(exc).lower()
                    or attempt == 19
                ):
                    raise
                time.sleep(0.01 * (attempt + 1))

    @classmethod
    def _allocate_order_number(cls):
        with transaction.atomic():
            updated = OrderNumberSequence.objects.filter(pk=1).update(
                last_number=F("last_number") + 1
            )
            if updated != 1:
                highest_number = 0
                numbers = cls.objects.exclude(order_number__isnull=True).values_list(
                    "order_number", flat=True
                )
                for number in numbers.iterator(chunk_size=1000):
                    try:
                        suffix = int(number.rsplit("-", 1)[1])
                    except (IndexError, ValueError) as exc:
                        raise ValueError(f"Invalid persisted order number: {number}") from exc
                    highest_number = max(highest_number, suffix)
                OrderNumberSequence.objects.get_or_create(
                    pk=1, defaults={"last_number": highest_number}
                )
                updated = OrderNumberSequence.objects.filter(pk=1).update(
                    last_number=F("last_number") + 1
                )
            if updated != 1:
                raise OrderNumberSequence.DoesNotExist("Order number counter could not be initialized.")
            last_number = OrderNumberSequence.objects.values_list("last_number", flat=True).get(pk=1)
            return f"WAS-{timezone.localdate().year}-{last_number:06d}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.order_number = self._next_order_number()
        elif self.pk:
            persisted_number = type(self).objects.filter(pk=self.pk).values_list(
                "order_number", flat=True
            ).first()
            if persisted_number is None:
                self.order_number = self._next_order_number()
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = set(kwargs["update_fields"]) | {"order_number"}
            else:
                self.order_number = persisted_number
        super().save(*args, **kwargs)

    def ensure_order_number(self):
        if self.order_number or not self.pk:
            return self.order_number
        generated = self._next_order_number()
        updated = type(self).objects.filter(pk=self.pk, order_number__isnull=True).update(
            order_number=generated
        )
        if updated:
            self.order_number = generated
        else:
            self.order_number = type(self).objects.filter(pk=self.pk).values_list(
                "order_number", flat=True
            ).first()
        return self.order_number

    def resolved_service(self):
        """Service needed to execute this order, derived for legacy rows."""
        if self.service_type:
            return self.service_type
        if self.order_type == "ride":
            return "ride"
        if self.order_type == "parcel":
            return "parcel"
        if self.merchant_id:
            return self.merchant.service_type
        return "food"

    def ensure_delivery_otp(self):
        """Create a delivery OTP once; it is delivered to the customer only."""
        import secrets as _secrets
        if self.delivery_otp:
            return self.delivery_otp
        code = f"{_secrets.randbelow(900000) + 100000}"
        type(self).objects.filter(pk=self.pk, delivery_otp="").update(delivery_otp=code)
        self.delivery_otp = code
        return code


class OrderActivity(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="activities")
    event = models.CharField(max_length=32)
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_activities",
    )
    actor_name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["order", "created_at"], name="order_activity_time")]


class CashSettlement(models.Model):
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="settlement")
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.PROTECT)
    captain = models.ForeignKey(CaptainProfile, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    confirmed_by_merchant = models.BooleanField(default=False)
    confirmed_by_captain = models.BooleanField(default=False)
    closed = models.BooleanField(default=False)
    reference = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)


class CashSettlementReceipt(models.Model):
    captain = models.ForeignKey(CaptainProfile, on_delete=models.PROTECT, related_name="settlement_receipts")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_settlement_receipts")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True)
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="cash_receipt_amount_positive"),
        ]


class CashSettlementAllocation(models.Model):
    receipt = models.ForeignKey(CashSettlementReceipt, on_delete=models.PROTECT, related_name="allocations")
    settlement = models.ForeignKey(CashSettlement, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["receipt", "settlement"], name="uniq_receipt_settlement_allocation"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="cash_allocation_amount_positive"),
        ]


class FinanceAccessAudit(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="finance_access_changes")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="finance_access_audits")
    granted = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class AdminAccountAudit(models.Model):
    ACTION_CHOICES = [
        ("account_status", "Account status"),
        ("captain_approval", "Captain approval"),
    ]

    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="admin_account_changes",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="admin_account_audits",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    previous_value = models.CharField(max_length=32)
    new_value = models.CharField(max_length=32)
    reason = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class DelayReport(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="delay_reports")
    captain = models.ForeignKey(CaptainProfile, on_delete=models.PROTECT)
    arrived_at = models.DateTimeField(default=timezone.now)
    reported_at = models.DateTimeField(auto_now_add=True)
    wait_minutes = models.PositiveSmallIntegerField(default=10)
    details = models.TextField(blank=True)
    reviewed = models.BooleanField(default=False)

class Rating(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="ratings")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    target_type = models.CharField(max_length=20)
    score = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class SupportTicket(models.Model):
    STATUSES = [("open","Open"),("in_review","In review"),("resolved","Resolved")]
    PRIORITIES = [("low", "Low"), ("normal", "Normal"), ("high", "High")]
    CATEGORIES = [
        ("order", "Order issue"), ("delivery", "Delivery issue"), ("payment", "Payment issue"),
        ("account", "Account issue"), ("merchant", "Merchant issue"), ("technology", "Technical issue"),
        ("other", "Other"),
    ]
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets",
    )
    subject = models.CharField(max_length=180)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUSES, default="open")
    priority = models.CharField(max_length=10, choices=PRIORITIES, default="normal")
    category = models.CharField(max_length=20, choices=CATEGORIES, default="other")
    resolution = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    """Persisted in-app notification for one user.

    ``event`` is a stable identifier ("order.created", "stock.out", …) and
    ``payload`` carries only the data needed to render it in the user's
    language; the client never receives another user's notifications.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    event = models.CharField(max_length=40)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "-created_at"], name="notif_user_read_created")]


class Subscription(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("pending", "Pending payment"), ("expired", "Expired"), ("cancelled", "Cancelled")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    months = models.PositiveSmallIntegerField(default=1)
    currency = models.CharField(max_length=8, default="ILS")
    starts_on = models.DateField()
    ends_on = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_subscriptions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_on", "-created_at"]

    def __str__(self):
        return f"{self.user.username} · {self.amount} {self.currency} · {self.starts_on}"

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.status == "active" and self.starts_on <= today <= self.ends_on


class SubscriptionPayment(models.Model):
    METHODS = [("cash", "Cash"), ("bank", "Bank transfer"), ("online", "Online"), ("other", "Other")]
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=12, choices=METHODS, default="cash")
    reference = models.CharField(max_length=100, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-paid_at"]


class InventoryMovement(models.Model):
    """Immutable audit row for every stock change.

    The partial unique constraint makes the order reservation idempotent: a
    retried request can never deduct the same product for the same order twice.
    """
    REASONS = [
        ("manual", "Manual adjustment"),
        ("restock", "Restock"),
        ("order", "Order reserved"),
        ("cancel", "Order cancelled"),
        ("correction", "Correction"),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_movements")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_movements")
    delta = models.IntegerField()
    quantity_before = models.IntegerField(null=True, blank=True)
    quantity_after = models.IntegerField(null=True, blank=True)
    reason = models.CharField(max_length=16, choices=REASONS)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["product", "-created_at"], name="inventory_product_time")]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "product", "reason"],
                condition=models.Q(reason="order"),
                name="uniq_order_stock_deduction",
            ),
        ]


class PriceChange(models.Model):
    """Audit trail for price and promotion edits, required for merchant reports."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_changes")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="price_changes")
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    old_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class OrderProof(models.Model):
    """Immutable fulfilment proof (pickup or delivery) for one order."""
    KINDS = [("pickup", "Pickup"), ("delivery", "Delivery")]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="proofs")
    kind = models.CharField(max_length=10, choices=KINDS)
    photo = models.ImageField(upload_to="order_proofs/", blank=True, null=True)
    recipient_name = models.CharField(max_length=150, blank=True)
    notes = models.CharField(max_length=500, blank=True)
    otp_verified = models.BooleanField(default=False)
    captured_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="order_proofs")
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["captured_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "kind"], name="uniq_order_proof_kind"),
        ]


class ServiceRegion(models.Model):
    """A geographic operating area a service can be offered in."""

    code = models.CharField(max_length=30, unique=True)
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    center_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    center_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radius_km = models.PositiveSmallIntegerField(default=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name_en"]

    def __str__(self):
        return self.name_en


class PlatformService(models.Model):
    """Administrator-owned definition of one service on the platform.

    The catalogue is data, not code: a new service can be added, switched on and
    scoped to regions from the admin console. Only ``is_operational`` services
    are exposed to customers, because that flag means an order flow is wired.
    """

    CATEGORIES = [
        ("food_trade", "Food & trade"),
        ("delivery", "Delivery & transport"),
        ("home_personal", "Home & personal services"),
        ("gifts", "Gifts & occasions"),
        ("travel", "Travel & bookings"),
        ("education", "Education & specialised"),
        ("other", "Other"),
    ]
    BUSINESS_TYPES = [
        ("merchant", "Merchant"), ("captain", "Captain"), ("specialist", "Specialist"),
        ("booking", "Booking provider"), ("platform", "Platform operated"),
    ]
    WORKFLOWS = [
        ("instant", "Instant order"),
        ("merchant_accept", "Merchant acceptance"),
        ("provider_accept", "Provider approval"),
        ("booking", "Scheduled booking"),
        ("quote", "Quote request"),
    ]
    PRICING_MODES = [
        ("fixed", "Fixed price"), ("distance", "Distance based"),
        ("time", "Time based"), ("quote", "Quote"),
    ]
    STATUS_GROUPS = [
        ["new", "accepted", "preparing", "ready", "assigned", "picked_up", "delivering", "awaiting_confirmation", "completed"],
    ]

    code = models.CharField(max_length=40, unique=True)
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    name_he = models.CharField(max_length=120, blank=True)
    description_ar = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORIES, default="other")
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPES, default="merchant")
    workflow = models.CharField(max_length=20, choices=WORKFLOWS, default="merchant_accept")
    pricing_mode = models.CharField(max_length=20, choices=PRICING_MODES, default="fixed")
    requires_merchant = models.BooleanField(default=True)
    requires_captain = models.BooleanField(default=True)
    requires_specialist = models.BooleanField(default=False)
    requires_booking = models.BooleanField(default=False)
    # True only while an implemented order flow exists for this code.
    is_operational = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    icon = models.CharField(max_length=40, blank=True)
    image = models.ImageField(upload_to="services/", blank=True, null=True)
    provider_requirements = models.TextField(blank=True)
    order_flow = models.JSONField(default=list, blank=True)
    working_hours = models.JSONField(default=list, blank=True)
    regions = models.ManyToManyField(ServiceRegion, blank=True, related_name="services")
    # Which implemented service runs the orders of this catalogue entry. The
    # six SERVICE_CODES own real order flows; activities such as "Restaurants"
    # or "Bakeries" are executed by one of them instead of duplicating a flow.
    fulfilment_service = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="catalogue_aliases",
        help_text="Implemented service that runs orders for this catalogue entry.",
    )
    sort_order = models.PositiveSmallIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return self.name_en

    @property
    def display_name(self):
        return self.name_en or self.code

    @property
    def effective_service(self):
        """The service whose order flow actually executes this entry."""
        alias = self.fulfilment_service if self.fulfilment_service_id else None
        return alias if alias is not None else self

    @property
    def effective_code(self):
        return self.effective_service.code

    @property
    def runs_order_flow(self):
        """True when this entry can be offered: its own flow or its linked flow exists."""
        if self.is_operational:
            return True
        alias = self.fulfilment_service if self.fulfilment_service_id else None
        return bool(alias and alias.is_operational)

    @property
    def is_offered_to_customers(self):
        return bool(self.is_active and self.runs_order_flow)

    @classmethod
    def active_codes(cls):
        return {
            service.code for service in cls.objects.select_related("fulfilment_service").all()
            if service.is_offered_to_customers
        }

    @classmethod
    def is_offered(cls, code):
        """False only when a configured service is switched off for customers."""
        service = cls.objects.select_related("fulfilment_service").filter(code=code).first()
        return service is None or service.is_offered_to_customers


class PlatformSettings(models.Model):
    """Singleton operational settings; commission stays null until configured."""

    default_delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    default_commission_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="ILS")
    support_email = models.EmailField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "platform settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def commission_configured(self):
        return self.default_commission_percent is not None


class AuditLog(models.Model):
    """Immutable record of an administrative action."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_entries",
    )
    actor_name = models.CharField(max_length=150)
    action = models.CharField(max_length=60)
    target_type = models.CharField(max_length=40)
    target_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=255)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["target_type", "target_id"], name="audit_target")]
