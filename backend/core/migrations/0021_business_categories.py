from django.db import migrations, models
import django.db.models.deletion

# code, name_ar, name_en, platform service code, requires licence
BUSINESS_CATEGORIES = [
    ("restaurant", "مطعم", "Restaurant", "food", False),
    ("supermarket", "سوبرماركت", "Supermarket", "grocery", False),
    ("grocery", "بقالة", "Grocery", "grocery", False),
    ("pharmacy", "صيدلية", "Pharmacy", "pharmacy", True),
    ("bakery", "مخبز", "Bakery", "bakery", False),
    ("produce", "خضار وفواكه", "Vegetables & fruits", "produce", False),
    ("butcher", "لحوم ودواجن", "Meat & poultry", "butcher", False),
    ("electronics", "إلكترونيات", "Electronics", "electronics", False),
    ("clothing", "ملابس", "Clothing", None, False),
    ("flowers_gifts", "ورود وهدايا", "Flowers & gifts", "flowers_gifts", False),
    ("home_supplies", "مستلزمات منزلية", "Home supplies", "home_furniture", False),
    ("baby_supplies", "مستلزمات أطفال", "Kids supplies", "baby_supplies", False),
    ("pet_supplies", "مستلزمات حيوانات", "Pet supplies", "pet_supplies", False),
    ("other", "نشاط آخر", "Other", "other_services", False),
]

# Legacy free-text category values used before this table existed.
LEGACY_CATEGORY = {
    "restaurant": "restaurant",
    "food": "restaurant",
    "supermarket": "supermarket",
    "grocery": "grocery",
    "pharmacy": "pharmacy",
    "bakery": "bakery",
    "produce": "produce",
    "butcher": "butcher",
    "electronics": "electronics",
    "clothing": "clothing",
    "flowers_gifts": "flowers_gifts",
    "home_supplies": "home_supplies",
    "home_furniture": "home_supplies",
    "baby_supplies": "baby_supplies",
    "pet_supplies": "pet_supplies",
    "general": "other",
    "general_store": "other",
    "other": "other",
}


def seed_business_categories(apps, schema_editor):
    BusinessCategory = apps.get_model("core", "BusinessCategory")
    PlatformService = apps.get_model("core", "PlatformService")
    MerchantProfile = apps.get_model("core", "MerchantProfile")

    services = {service.code: service for service in PlatformService.objects.all()}
    for index, (code, name_ar, name_en, service_code, requires_license) in enumerate(BUSINESS_CATEGORIES):
        BusinessCategory.objects.update_or_create(
            code=code,
            defaults={
                "name_ar": name_ar,
                "name_en": name_en,
                "service": services.get(service_code) if service_code else None,
                "requires_license": requires_license,
                "is_active": True,
                "sort_order": index,
            },
        )

    by_code = {category.code: category for category in BusinessCategory.objects.select_related("service")}
    for profile in MerchantProfile.objects.prefetch_related("services").all():
        code = LEGACY_CATEGORY.get((profile.category or "").strip().lower(), "other")
        category = by_code.get(code)
        if category is None:
            continue
        profile.business_category = category
        profile.save(update_fields=["business_category"])
        # Keep an explicit service assignment: give the store the service its
        # activity maps to when it has none of its own yet.
        if category.service_id and not profile.services.exists():
            profile.services.add(category.service)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_service_details_and_pharmacy_safety"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40, unique=True)),
                ("name_ar", models.CharField(max_length=80)),
                ("name_en", models.CharField(max_length=80)),
                ("requires_license", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "service",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                        related_name="business_categories", to="core.platformservice",
                    ),
                ),
            ],
            options={"ordering": ["sort_order", "code"], "verbose_name_plural": "business categories"},
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="business_category",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="merchants", to="core.businesscategory",
            ),
        ),
        migrations.RunPython(seed_business_categories, migrations.RunPython.noop),
    ]
