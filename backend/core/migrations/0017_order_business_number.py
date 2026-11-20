from django.db import migrations, models
from django.utils import timezone


def backfill_order_numbers(apps, schema_editor):
    Order = apps.get_model("core", "Order")
    Sequence = apps.get_model("core", "OrderNumberSequence")
    database = schema_editor.connection.alias
    sequence = 0
    batch = []

    orders = Order.objects.using(database).order_by("created_at", "pk")
    for order in orders.iterator(chunk_size=1000):
        sequence += 1
        created_at = order.created_at
        if timezone.is_naive(created_at):
            created_at = timezone.make_aware(created_at, timezone.get_default_timezone())
        year = timezone.localtime(created_at).year
        order.order_number = f"WAS-{year}-{sequence:06d}"
        batch.append(order)
        if len(batch) == 1000:
            Order.objects.using(database).bulk_update(batch, ["order_number"], batch_size=1000)
            batch.clear()

    if batch:
        Order.objects.using(database).bulk_update(batch, ["order_number"], batch_size=1000)

    Sequence.objects.using(database).create(pk=1, last_number=sequence)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0016_adminaccountaudit"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderNumberSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_number", models.PositiveBigIntegerField(default=0)),
            ],
        ),
        migrations.AddField(
            model_name="order",
            name="order_number",
            field=models.CharField(blank=True, editable=False, max_length=32, null=True),
        ),
        migrations.RunPython(backfill_order_numbers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(fields=("order_number",), name="uniq_order_business_number"),
        ),
    ]
