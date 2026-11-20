from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_legacy(apps, schema_editor):
    MerchantProfile = apps.get_model("core", "MerchantProfile")
    MerchantBranch = apps.get_model("core", "MerchantBranch")
    CaptainProfile = apps.get_model("core", "CaptainProfile")
    CaptainServiceEligibility = apps.get_model("core", "CaptainServiceEligibility")
    Order = apps.get_model("core", "Order")

    for merchant in MerchantProfile.objects.all().iterator():
        MerchantBranch.objects.create(
            merchant=merchant,
            name=merchant.shop_name or "Main branch",
            address=merchant.address,
            latitude=merchant.latitude,
            longitude=merchant.longitude,
            opening_hours=merchant.opening_hours,
            is_active=True,
        )

    for profile in CaptainProfile.objects.filter(approved=True).iterator():
        CaptainServiceEligibility.objects.get_or_create(
            captain=profile,
            service="food",
            defaults={"status": "approved", "accepting": True},
        )

    for order in Order.objects.all().iterator():
        service = "ride" if order.order_type == "ride" else "parcel" if order.order_type == "parcel" else "food"
        Order.objects.filter(pk=order.pk).update(service_type=service)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0017_order_business_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchantprofile",
            name="temporarily_closed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="prep_minutes",
            field=models.PositiveSmallIntegerField(default=15),
        ),
        migrations.AddField(
            model_name="captainprofile",
            name="max_active_tasks",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="product",
            name="discount_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="discount_starts_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="discount_ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="CaptainServiceEligibility",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.CharField(choices=[("food", "Food delivery"), ("grocery", "Grocery & supermarket"), ("pharmacy", "Pharmacy"), ("parcel", "Parcels & documents"), ("ride", "Vespa rides"), ("logistics", "Special logistics")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("suspended", "Suspended")], default="pending", max_length=12)),
                ("accepting", models.BooleanField(default=True)),
                ("regions", models.JSONField(blank=True, default=list)),
                ("training_required", models.BooleanField(default=False)),
                ("training_completed", models.BooleanField(default=False)),
                ("document_verified", models.BooleanField(default=False)),
                ("notes", models.CharField(blank=True, max_length=500)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("captain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_eligibilities", to="core.captainprofile")),
            ],
            options={"ordering": ["service"]},
        ),
        migrations.AddConstraint(
            model_name="captainserviceeligibility",
            constraint=models.UniqueConstraint(fields=("captain", "service"), name="uniq_captain_service"),
        ),
        migrations.CreateModel(
            name="CaptainWorkingWindow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("weekday", models.PositiveSmallIntegerField()),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("is_break", models.BooleanField(default=False)),
                ("captain", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="working_windows", to="core.captainprofile")),
            ],
            options={"ordering": ["weekday", "start_time"]},
        ),
        migrations.AddConstraint(
            model_name="captainworkingwindow",
            constraint=models.CheckConstraint(condition=models.Q(("weekday__gte", 0), ("weekday__lte", 6)), name="captain_window_weekday"),
        ),
        migrations.CreateModel(
            name="MerchantBranch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("address", models.CharField(blank=True, max_length=255)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("opening_hours", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="branches", to="core.merchantprofile")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="MerchantStaff",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("manager", "Manager"), ("orders", "Order desk"), ("preparation", "Preparation"), ("inventory", "Inventory"), ("reports", "Reports")], default="orders", max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="staff", to="core.merchantprofile")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="merchant_staff_roles", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="merchantstaff",
            constraint=models.UniqueConstraint(fields=("merchant", "user"), name="uniq_merchant_staff"),
        ),
        migrations.AddConstraint(
            model_name="merchantstaff",
            constraint=models.UniqueConstraint(fields=("user",), name="uniq_staff_single_merchant"),
        ),
        migrations.CreateModel(
            name="MerchantHours",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("weekday", models.PositiveSmallIntegerField()),
                ("opens_at", models.TimeField(blank=True, null=True)),
                ("closes_at", models.TimeField(blank=True, null=True)),
                ("is_closed", models.BooleanField(default=False)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="business_hours", to="core.merchantbranch")),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="business_hours", to="core.merchantprofile")),
            ],
            options={"ordering": ["weekday"]},
        ),
        migrations.AddConstraint(
            model_name="merchanthours",
            constraint=models.UniqueConstraint(fields=("merchant", "branch", "weekday"), name="uniq_merchant_branch_weekday"),
        ),
        migrations.CreateModel(
            name="StoreClosure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("reason", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="closures", to="core.merchantbranch")),
                ("merchant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="closures", to="core.merchantprofile")),
            ],
            options={"ordering": ["date"]},
        ),
        migrations.AddConstraint(
            model_name="storeclosure",
            constraint=models.UniqueConstraint(fields=("merchant", "branch", "date"), name="uniq_store_closure_day"),
        ),
        migrations.AddField(
            model_name="order",
            name="service_type",
            field=models.CharField(blank=True, choices=[("food", "Food delivery"), ("grocery", "Grocery & supermarket"), ("pharmacy", "Pharmacy"), ("parcel", "Parcels & documents"), ("ride", "Vespa rides"), ("logistics", "Special logistics")], default="", max_length=20),
        ),
        migrations.AddField(
            model_name="order",
            name="branch",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="core.merchantbranch"),
        ),
        migrations.AddField(
            model_name="order",
            name="cancellation_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_otp",
            field=models.CharField(blank=True, max_length=6),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_otp_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="InventoryMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("delta", models.IntegerField()),
                ("quantity_before", models.IntegerField(blank=True, null=True)),
                ("quantity_after", models.IntegerField(blank=True, null=True)),
                ("reason", models.CharField(choices=[("manual", "Manual adjustment"), ("restock", "Restock"), ("order", "Order reserved"), ("cancel", "Order cancelled"), ("correction", "Correction")], max_length=16)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventory_movements", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventory_movements", to="core.order")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="movements", to="core.product")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="inventorymovement",
            index=models.Index(fields=["product", "-created_at"], name="inventory_product_time"),
        ),
        migrations.AddConstraint(
            model_name="inventorymovement",
            constraint=models.UniqueConstraint(condition=models.Q(("reason", "order")), fields=("order", "product", "reason"), name="uniq_order_stock_deduction"),
        ),
        migrations.CreateModel(
            name="PriceChange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("old_price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("new_price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("old_discount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("new_discount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("reason", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="price_changes", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="price_changes", to="core.product")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="OrderProof",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("pickup", "Pickup"), ("delivery", "Delivery")], max_length=10)),
                ("photo", models.ImageField(blank=True, null=True, upload_to="order_proofs/")),
                ("recipient_name", models.CharField(blank=True, max_length=150)),
                ("notes", models.CharField(blank=True, max_length=500)),
                ("otp_verified", models.BooleanField(default=False)),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
                ("captured_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="order_proofs", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proofs", to="core.order")),
            ],
            options={"ordering": ["captured_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="orderproof",
            constraint=models.UniqueConstraint(fields=("order", "kind"), name="uniq_order_proof_kind"),
        ),
        migrations.RunPython(backfill_legacy, migrations.RunPython.noop),
    ]
