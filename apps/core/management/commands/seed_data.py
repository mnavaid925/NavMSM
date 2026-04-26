from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Orchestrator: seed plans + demo tenants/users/subs/invoices/health.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('→ seed_plans'))
        call_command('seed_plans')
        self.stdout.write(self.style.HTTP_INFO('→ seed_tenants'))
        call_command('seed_tenants', flush=options.get('flush', False))
        self.stdout.write(self.style.HTTP_INFO('→ seed_plm'))
        call_command('seed_plm', flush=options.get('flush', False))
        self.stdout.write(self.style.HTTP_INFO('→ seed_bom'))
        call_command('seed_bom', flush=options.get('flush', False))
        self.stdout.write(self.style.HTTP_INFO('→ seed_pps'))
        call_command('seed_pps', flush=options.get('flush', False))
