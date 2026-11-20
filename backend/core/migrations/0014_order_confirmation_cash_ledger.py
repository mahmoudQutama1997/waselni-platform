import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_inventory_notifications"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_finance_staff",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("accepted", "Accepted"),
                    ("preparing", "Preparing"),
                    ("ready", "Ready"),
                    ("assigned", "Assigned"),
                    ("picked_up", "Picked_Up"),
                    ("delivering", "Delivering"),
                    ("awaiting_confirmation", "Awaiting_Confirmation"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="new",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="captain_delivered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="completed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="completed_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="completed_by_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="order",
            name="completion_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("captain", "Captain"),
                    ("customer", "Customer"),
                    ("automatic", "Automatic"),
                ],
                max_length=12,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="CashSettlementReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("reference", models.CharField(max_length=100, unique=True)),
                ("notes", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("captain", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="settlement_receipts",
                    to="core.captainprofile",
                )),
                ("recorded_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="cash_settlement_receipts",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CashSettlementAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("receipt", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="allocations",
                    to="core.cashsettlementreceipt",
                )),
                ("settlement", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="allocations",
                    to="core.cashsettlement",
                )),
            ],
        ),
        migrations.CreateModel(
            name="FinanceAccessAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("granted", models.BooleanField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="finance_access_audits",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="finance_access_changes",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="cashsettlementreceipt",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="cash_receipt_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="cashsettlementallocation",
            constraint=models.UniqueConstraint(fields=("receipt", "settlement"), name="uniq_receipt_settlement_allocation"),
        ),
        migrations.AddConstraint(
            model_name="cashsettlementallocation",
            constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="cash_allocation_amount_positive"),
        ),
    ]
