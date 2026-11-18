from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


OPERATIONAL_SERVICES = [
    # code, name_en, name_ar, category, business_type, workflow, pricing, merchant, captain, specialist
    ("food", "Food delivery", "توصيل الطعام", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False),
    ("grocery", "Grocery & supermarket", "السوبرماركت والبقالة", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False),
    ("pharmacy", "Pharmacy", "الصيدليات", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False),
    ("parcel", "Parcels & documents", "توصيل الطرود والمستندات", "delivery", "captain", "instant", "distance", False, True, False),
    ("ride", "Vespa rides", "مشاوير الفيسبا", "delivery", "captain", "instant", "distance", False, True, False),
    ("logistics", "Special logistics", "الشحن الخاص", "delivery", "captain", "provider_accept", "distance", False, True, True),
]

STORE_FLOW = ["new", "accepted", "preparing", "ready", "assigned", "picked_up", "delivering", "awaiting_confirmation", "completed"]
DIRECT_FLOW = ["new", "assigned", "picked_up", "delivering", "awaiting_confirmation", "completed"]

# The full future catalogue. Every row is created inactive and non-operational:
# an administrator switches a service on only when its order flow exists.
CATALOG_SERVICES = [
    ("restaurants", "Restaurants & meals", "المطاعم والوجبات", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("supermarket", "Supermarkets & groceries", "السوبرماركت والبقالة", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("produce", "Fruit & vegetables", "الخضار والفواكه", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("bakery", "Bakeries & sweets", "المخابز والحلويات", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("butcher", "Meat, poultry & fish", "اللحوم والدواجن والأسماك", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("general_store", "General stores", "المتاجر العامة", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("electronics", "Electronics, phones & computers", "الإلكترونيات والهواتف والحواسيب", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("health_products", "Pharmacy & health products", "الصيدليات والمنتجات الصحية", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("home_furniture", "Home & furniture supplies", "مستلزمات المنزل والأثاث", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("baby_supplies", "Baby supplies", "مستلزمات الأطفال", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("pet_supplies", "Pet supplies", "مستلزمات الحيوانات الأليفة", "food_trade", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("package_delivery", "Parcels & documents", "توصيل الطرود والمستندات", "delivery", "captain", "instant", "distance", False, True, False, False),
    ("scooter_rides", "Scooter rides", "مشاوير الفيسبا", "delivery", "captain", "instant", "distance", False, True, False, False),
    ("vehicle_transport", "Transport by vehicle type", "النقل حسب المركبة", "delivery", "captain", "instant", "distance", False, True, False, False),
    ("intercity_freight", "Intercity shipping", "الشحن بين المدن والمناطق", "delivery", "captain", "quote", "distance", False, True, True, False),
    ("bulky_moving", "Furniture & bulky moving", "نقل الأغراض والأثاث", "delivery", "captain", "quote", "distance", False, True, True, False),
    ("vehicle_rental", "Vehicle, scooter & equipment rental", "تأجير السيارات والدراجات والمعدات", "delivery", "specialist", "booking", "time", False, False, True, True),
    ("home_maintenance", "Home maintenance", "الصيانة المنزلية", "home_personal", "specialist", "provider_accept", "quote", False, False, True, False),
    ("electrical_plumbing", "Electrical, plumbing & HVAC", "الكهرباء والسباكة والتكييف", "home_personal", "specialist", "provider_accept", "quote", False, False, True, False),
    ("appliance_repair", "Home appliance repair", "صيانة الأجهزة المنزلية", "home_personal", "specialist", "provider_accept", "quote", False, False, True, False),
    ("home_cleaning", "Home cleaning", "التنظيف المنزلي", "home_personal", "specialist", "provider_accept", "fixed", False, False, True, False),
    ("laundry", "Laundry, washing & ironing", "المغاسل وغسيل وكي الملابس", "home_personal", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("car_wash", "Car wash & detailing", "غسيل السيارات والعناية بها", "home_personal", "merchant", "booking", "fixed", True, False, False, True),
    ("roadside_assistance", "Roadside & emergency assistance", "خدمات الطريق والمساعدة الطارئة", "home_personal", "specialist", "provider_accept", "distance", False, True, True, False),
    ("personal_care", "Personal care & beauty", "العناية الشخصية والتجميل", "home_personal", "specialist", "booking", "fixed", False, False, True, True),
    ("flowers_gifts", "Flowers & gifts", "الورود والهدايا", "gifts", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("gift_wrapping", "Gift wrapping", "تغليف الهدايا", "gifts", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("party_supplies", "Party & occasion supplies", "مستلزمات المناسبات والحفلات", "gifts", "merchant", "merchant_accept", "fixed", True, True, False, False),
    ("event_planning", "Event planning", "تنظيم الفعاليات", "gifts", "specialist", "quote", "quote", False, False, True, True),
    ("hotel_booking", "Hotels & apartments", "حجوزات الفنادق والشقق", "travel", "booking", "booking", "time", False, False, False, True),
    ("tours", "Tours & tourism activities", "الرحلات والأنشطة السياحية", "travel", "booking", "booking", "fixed", False, False, False, True),
    ("event_tickets", "Tickets & events", "التذاكر والفعاليات", "travel", "booking", "booking", "fixed", False, False, False, True),
    ("sports_courts", "Sports courts & activities", "حجوزات الملاعب والأنشطة الرياضية", "travel", "booking", "booking", "time", False, False, False, True),
    ("facility_booking", "Facility & service bookings", "حجوزات المرافق والخدمات", "travel", "booking", "booking", "time", False, False, False, True),
    ("private_tutoring", "Private tutoring", "الدروس الخصوصية", "education", "specialist", "booking", "time", False, False, True, True),
    ("training_courses", "Courses & training", "الدورات والتدريب", "education", "specialist", "booking", "fixed", False, False, True, True),
    ("tech_services", "Technical services", "الخدمات التقنية", "education", "specialist", "provider_accept", "quote", False, False, True, False),
    ("business_support", "Business support services", "خدمات الأعمال والمساندة", "education", "specialist", "quote", "quote", False, False, True, False),
    ("pet_services", "Pet services", "خدمات الحيوانات الأليفة", "education", "specialist", "booking", "fixed", False, False, True, True),
    ("other_services", "Other services", "خدمات أخرى", "other", "specialist", "quote", "quote", False, False, True, False),
]

CATEGORY_SERVICE = {
    "supermarket": "grocery",
    "grocery": "grocery",
    "pharmacy": "pharmacy",
    "restaurant": "food",
    "food": "food",
}


def seed_services(apps, schema_editor):
    ServiceRegion = apps.get_model("core", "ServiceRegion")
    PlatformService = apps.get_model("core", "PlatformService")
    PlatformSettings = apps.get_model("core", "PlatformSettings")
    MerchantProfile = apps.get_model("core", "MerchantProfile")

    PlatformSettings.objects.get_or_create(pk=1, defaults={"currency": "ILS"})
    for index, row in enumerate(OPERATIONAL_SERVICES):
        code, name_en, name_ar, category, business, workflow, pricing, merchant, captain, specialist = row
        PlatformService.objects.update_or_create(
            code=code,
            defaults={
                "name_en": name_en, "name_ar": name_ar, "category": category,
                "business_type": business, "workflow": workflow, "pricing_mode": pricing,
                "requires_merchant": merchant, "requires_captain": captain,
                "requires_specialist": specialist, "requires_booking": False,
                "is_operational": True, "is_active": True,
                "order_flow": STORE_FLOW if merchant else DIRECT_FLOW,
                "sort_order": index,
            },
        )
    for index, row in enumerate(CATALOG_SERVICES):
        code, name_en, name_ar, category, business, workflow, pricing, merchant, captain, specialist, booking = row
        PlatformService.objects.update_or_create(
            code=code,
            defaults={
                "name_en": name_en, "name_ar": name_ar, "category": category,
                "business_type": business, "workflow": workflow, "pricing_mode": pricing,
                "requires_merchant": merchant, "requires_captain": captain,
                "requires_specialist": specialist, "requires_booking": booking,
                # These entries define the catalogue; a flow must be wired before
                # an administrator may switch one on for customers.
                "is_operational": False, "is_active": False,
                "order_flow": [],
                "sort_order": 200 + index,
            },
        )

    # Existing merchants were trading before approval states existed; keep them live.
    MerchantProfile.objects.update(approval_status="approved")
    operational = {service.code: service for service in PlatformService.objects.filter(is_operational=True)}
    for profile in MerchantProfile.objects.all():
        code = CATEGORY_SERVICE.get((profile.category or "").strip().lower())
        service = operational.get(code) if code else None
        if service is not None:
            profile.services.add(service)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0018_multiservice_captain_merchant_management"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceRegion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30, unique=True)),
                ("name_ar", models.CharField(max_length=80)),
                ("name_en", models.CharField(max_length=80)),
                ("center_latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("center_longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("radius_km", models.PositiveSmallIntegerField(default=15)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name_en"]},
        ),
        migrations.CreateModel(
            name="PlatformService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40, unique=True)),
                ("name_ar", models.CharField(max_length=120)),
                ("name_en", models.CharField(max_length=120)),
                ("name_he", models.CharField(blank=True, max_length=120)),
                ("description_ar", models.TextField(blank=True)),
                ("description_en", models.TextField(blank=True)),
                ("category", models.CharField(choices=[("food_trade", "Food & trade"), ("delivery", "Delivery & transport"), ("home_personal", "Home & personal services"), ("gifts", "Gifts & occasions"), ("travel", "Travel & bookings"), ("education", "Education & specialised"), ("other", "Other")], default="other", max_length=20)),
                ("business_type", models.CharField(choices=[("merchant", "Merchant"), ("captain", "Captain"), ("specialist", "Specialist"), ("booking", "Booking provider"), ("platform", "Platform operated")], default="merchant", max_length=20)),
                ("workflow", models.CharField(choices=[("instant", "Instant order"), ("merchant_accept", "Merchant acceptance"), ("provider_accept", "Provider approval"), ("booking", "Scheduled booking"), ("quote", "Quote request")], default="merchant_accept", max_length=20)),
                ("pricing_mode", models.CharField(choices=[("fixed", "Fixed price"), ("distance", "Distance based"), ("time", "Time based"), ("quote", "Quote")], default="fixed", max_length=20)),
                ("requires_merchant", models.BooleanField(default=True)),
                ("requires_captain", models.BooleanField(default=True)),
                ("requires_specialist", models.BooleanField(default=False)),
                ("requires_booking", models.BooleanField(default=False)),
                ("is_operational", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=False)),
                ("icon", models.CharField(blank=True, max_length=40)),
                ("image", models.ImageField(blank=True, null=True, upload_to="services/")),
                ("provider_requirements", models.TextField(blank=True)),
                ("order_flow", models.JSONField(blank=True, default=list)),
                ("working_hours", models.JSONField(blank=True, default=list)),
                ("sort_order", models.PositiveSmallIntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("regions", models.ManyToManyField(blank=True, related_name="services", to="core.serviceregion")),
            ],
            options={"ordering": ["sort_order", "code"]},
        ),
        migrations.CreateModel(
            name="PlatformSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("default_delivery_fee", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("default_commission_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("currency", models.CharField(default="ILS", max_length=8)),
                ("support_email", models.EmailField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name_plural": "platform settings"},
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_name", models.CharField(max_length=150)),
                ("action", models.CharField(max_length=60)),
                ("target_type", models.CharField(max_length=40)),
                ("target_id", models.CharField(blank=True, max_length=40)),
                ("summary", models.CharField(max_length=255)),
                ("before", models.JSONField(blank=True, default=dict)),
                ("after", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["target_type", "target_id"], name="audit_target"),
        ),
        migrations.AddField(
            model_name="user",
            name="admin_role",
            field=models.CharField(blank=True, choices=[("super_admin", "Super admin"), ("operations", "Operations manager"), ("services", "Services manager"), ("merchants", "Merchants manager"), ("captains", "Captains manager"), ("regions", "Regions manager"), ("support", "Support agent"), ("finance", "Finance officer"), ("review", "Review & approval officer")], default="", max_length=20),
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="approval_status",
            field=models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("suspended", "Suspended"), ("rejected", "Rejected")], default="approved", max_length=12),
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="rejection_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_merchants", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="services",
            field=models.ManyToManyField(blank=True, related_name="merchants", to="core.platformservice"),
        ),
        migrations.AddField(
            model_name="merchantbranch",
            name="region",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="branches", to="core.serviceregion"),
        ),
        migrations.AddField(
            model_name="merchantbranch",
            name="services",
            field=models.ManyToManyField(blank=True, related_name="branches", to="core.platformservice"),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="assigned_to",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_tickets", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="priority",
            field=models.CharField(choices=[("low", "Low"), ("normal", "Normal"), ("high", "High")], default="normal", max_length=10),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="category",
            field=models.CharField(choices=[("order", "Order issue"), ("delivery", "Delivery issue"), ("payment", "Payment issue"), ("account", "Account issue"), ("merchant", "Merchant issue"), ("technology", "Technical issue"), ("other", "Other")], default="other", max_length=20),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="resolution",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(seed_services, migrations.RunPython.noop),
    ]
