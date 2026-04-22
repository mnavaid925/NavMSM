from django.core.management.base import BaseCommand

from apps.core.models import Tenant
from apps.tenants.services.health import capture_snapshot


class Command(BaseCommand):
    help = 'Capture a health snapshot for every active tenant. Run via cron.'

    def handle(self, *args, **options):
        count = 0
        for tenant in Tenant.objects.filter(is_active=True):
            capture_snapshot(tenant)
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Captured {count} snapshots.'))
