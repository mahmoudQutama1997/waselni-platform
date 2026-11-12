from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0011_captain_location_timestamp")]
    operations = [
        migrations.AddField(
            model_name="order",
            name="captain_accepted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
