from django.core.management.base import BaseCommand

from core.services.order_completion import complete_expired_order_confirmations


class Command(BaseCommand):
    help = "Complete orders awaiting customer confirmation for at least 12 hours."

    def handle(self, *args, **options):
        completed = complete_expired_order_confirmations()
        self.stdout.write(self.style.SUCCESS(f"Automatically completed {completed} order(s)."))
