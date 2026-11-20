from django.db import migrations, models
import django.db.models.deletion


# Catalogue entries that do not own an order flow are executed by an implemented
# service. This is data, not code: administrators can change it from the console.
FULFILMENT_LINKS = {
    "restaurants": "food",
    "supermarket": "grocery",
    "bakery": "food",
    "produce": "grocery",
    "butcher": "food",
    "general_store": "grocery",
    "health_products": "pharmacy",
    "home_furniture": "grocery",
    "baby_supplies": "grocery",
    "pet_supplies": "grocery",
}


def link_fulfilment_services(apps, schema_editor):
    PlatformService = apps.get_model("core", "PlatformService")
    services = {service.code: service for service in PlatformService.objects.all()}
    for alias_code, flow_code in FULFILMENT_LINKS.items():
        alias = services.get(alias_code)
        flow = services.get(flow_code)
        if alias is None or flow is None or alias.pk == flow.pk:
            continue
        # Never overwrite a link an administrator already set.
        if alias.fulfilment_service_id is None:
            alias.fulfilment_service = flow
            alias.save(update_fields=["fulfilment_service"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_business_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformservice",
            name="fulfilment_service",
            field=models.ForeignKey(
                blank=True,
                help_text="Implemented service that runs orders for this catalogue entry.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="catalogue_aliases",
                to="core.platformservice",
            ),
        ),
        migrations.RunPython(link_fulfilment_services, migrations.RunPython.noop),
    ]
