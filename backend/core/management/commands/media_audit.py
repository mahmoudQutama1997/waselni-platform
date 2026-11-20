import os

from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import MerchantProfile, Product, User
from core.storage import imagekit_config

PUBLIC_IMAGES = (
    (User, "profile_image"),
    (MerchantProfile, "image"),
    (MerchantProfile, "cover_image"),
    (Product, "image"),
)


class Command(BaseCommand):
    help = (
        "Read-only report of public image references: how many files still "
        "exist under MEDIA_ROOT, how many are missing, and which URL the API "
        "would return. Nothing is modified."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--examples",
            type=int,
            default=10,
            help="Rows to list per field (default 10).",
        )

    def handle(self, *args, **options):
        limit = max(0, options["examples"])
        configured = imagekit_config() is not None
        self.stdout.write(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
        self.stdout.write(f"ImageKit configured: {'yes' if configured else 'no'}")
        self.stdout.write("")
        for model, field_name in PUBLIC_IMAGES:
            field = model._meta.get_field(field_name)
            present = missing = empty = 0
            samples = []
            for obj in model.objects.only("pk", field_name).iterator():
                name = getattr(obj, field_name).name
                if not name:
                    empty += 1
                    continue
                if os.path.exists(os.path.join(settings.MEDIA_ROOT, name)):
                    present += 1
                else:
                    missing += 1
                    if len(samples) < limit:
                        samples.append((obj.pk, name, field.storage.url(name)))
            label = f"{model._meta.label}.{field_name}"
            self.stdout.write(f"{label}: present={present} missing={missing} empty={empty}")
            for pk, name, url in samples:
                self.stdout.write(f"  id={pk} stored={name} url={url}")
        self.stdout.write("")
        self.stdout.write(
            "Missing means no local copy exists under MEDIA_ROOT. Remote "
            "ImageKit files are not checked by this command."
        )
