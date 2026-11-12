import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from core.models import MerchantProfile, CaptainProfile

class Command(BaseCommand):
    help = "Create or repair Waselni demo users and their required profiles."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo accounts can only be created while DEBUG=True.")
        demo_password = os.getenv("WASELNI_DEMO_PASSWORD", "")
        if len(demo_password) < 12:
            raise CommandError(
                "Set WASELNI_DEMO_PASSWORD to a development-only password of at least 12 characters."
            )
        User = get_user_model()
        accounts = [
            ("customer1", "customer", "Demo Customer"),
            ("merchant1", "merchant", "Demo Store"),
            ("merchant_pharmacy", "merchant", "Demo Pharmacy"),
            ("merchant_electronics", "merchant", "Demo Electronics"),
            ("captain1", "captain", "Demo Captain"),
        ]
        for username, role, display_name in accounts:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "first_name": display_name},
            )
            changed = False
            if user.role != role:
                user.role = role
                changed = True
            if not user.first_name:
                user.first_name = display_name
                changed = True
            if created:
                user.set_password(demo_password)
                changed = True
            if changed:
                user.save()

            if role == "merchant":
                MerchantProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "shop_name": display_name,
                        "category": "general",
                        "address": "Demo address",
                        "is_open": True,
                    },
                )
            elif role == "captain":
                CaptainProfile.objects.get_or_create(
                    user=user,
                    defaults={"approved": False, "online": False},
                )
            state = "created" if created else "already existed / checked"
            self.stdout.write(f"{username}: {state}")

        self.stdout.write(self.style.SUCCESS("Demo setup complete. Use WASELNI_DEMO_PASSWORD for newly created accounts."))
        self.stdout.write("Existing account passwords are not changed. "
                          "Captain1 is created unapproved; approve it in the React admin dashboard (Captains tab).")
