from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_service_fulfilment"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchantprofile",
            name="requested_business_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="requested_by_merchants",
                to="core.businesscategory",
            ),
        ),
        migrations.AddField(
            model_name="merchantprofile",
            name="activity_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
