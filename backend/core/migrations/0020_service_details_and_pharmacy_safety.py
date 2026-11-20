from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_admin_control_center"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="prescription_required",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="product",
            name="controlled_substance",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="product",
            name="pharmacy_review_status",
            field=models.CharField(
                choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
                default="pending",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="service_details",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
