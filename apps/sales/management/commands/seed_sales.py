"""Idempotent demo seeder for Module 17 - Sales (17.1 portion).

Seeds per tenant:
    * 4 customer categories (root + 3 children)
    * 2 price lists (one default + one VIP)
    * 6 price list items (2 products x 3 tiers; uses first 2 plm.Products
      it finds for the tenant - silently skipped if no Products exist)
    * 8 customers spanning all customer_class values, including 2 with
      credit_limits + 1 on_hold
    * 3 contacts per customer
    * 5 communication log entries per tenant (mix of types/directions)

Safe to rerun without `--flush`. Use `--flush` to wipe all sales data
for the chosen tenants before reseeding.

Expansion in 17.2+: SalesOrder / Shipment / SalesInvoice rows.
"""
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

from apps.core.models import Tenant
from apps.sales.models import (
    CommunicationLog,
    Customer,
    CustomerCategory,
    CustomerContact,
    PriceList,
    PriceListItem,
)


CATEGORY_TREE = [
    {'name': 'Manufacturing', 'children': ['Automotive', 'Aerospace']},
    {'name': 'Distribution', 'children': ['Wholesale', 'Retail Chain']},
]
CUSTOMERS_PER_TENANT = [
    ('ACME Industries', 'key', 'active'),
    ('Globex Manufacturing', 'key', 'active'),
    ('Initech Robotics', 'standard', 'active'),
    ('Umbrella Aerospace', 'standard', 'active'),
    ('Soylent Distribution', 'distributor', 'active'),
    ('Hooli Wholesale', 'distributor', 'active'),
    ('Pied Piper Lab', 'standard', 'on_hold'),
    ('Stark Walk-in', 'one_time', 'active'),
]
COMM_TEMPLATES = [
    ('call', 'inbound', 'Initial product enquiry', 'done'),
    ('email', 'outbound', 'Quotation follow-up', 'open'),
    ('meeting', 'outbound', 'Quarterly business review', 'done'),
    ('note', 'internal', 'Credit check completed', 'done'),
    ('email', 'inbound', 'Delivery schedule confirmation request', 'open'),
]


class Command(BaseCommand):
    help = 'Idempotent demo seeder for Sales module 17.1 (Customer Master & CRM Lite).'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=str, default=None,
                            help='Slug of a single tenant to seed (default: all).')
        parser.add_argument('--flush', action='store_true',
                            help='Delete existing sales 17.1 data before seeding.')

    def handle(self, *args, **opts):
        slug = opts.get('tenant')
        tenants = (
            Tenant.objects.filter(slug=slug)
            if slug else Tenant.objects.filter(is_active=True)
        )
        if not tenants.exists():
            self.stderr.write(self.style.WARNING('No matching tenants found.'))
            return

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(f'\n== Tenant: {tenant.slug} =='))
            if opts['flush']:
                self._flush(tenant)
            elif Customer.all_objects.filter(tenant=tenant).exists():
                self.stdout.write(self.style.WARNING(
                    '  Sales data already exists. Skipping. Use --flush to re-seed.',
                ))
                continue
            self._seed_tenant(tenant)

        self.stdout.write(self.style.SUCCESS('\nDone. Log in as a tenant admin '
            '(e.g. admin_<slug>) to see sales data; the global "admin" superuser has '
            'no tenant and will see empty lists.'))

    def _flush(self, tenant):
        CommunicationLog.all_objects.filter(tenant=tenant).delete()
        CustomerContact.all_objects.filter(tenant=tenant).delete()
        Customer.all_objects.filter(tenant=tenant).delete()
        PriceListItem.all_objects.filter(tenant=tenant).delete()
        PriceList.all_objects.filter(tenant=tenant).delete()
        CustomerCategory.all_objects.filter(tenant=tenant).delete()
        self.stdout.write('  Flushed existing sales 17.1 rows.')

    def _seed_tenant(self, tenant):
        faker = Faker()
        # --- categories
        cats = {}
        for entry in CATEGORY_TREE:
            root, _ = CustomerCategory.all_objects.get_or_create(
                tenant=tenant, name=entry['name'], parent=None,
                defaults={'is_active': True},
            )
            cats[entry['name']] = root
            for child in entry['children']:
                obj, _ = CustomerCategory.all_objects.get_or_create(
                    tenant=tenant, name=child, parent=root,
                    defaults={'is_active': True},
                )
                cats[child] = obj
        self.stdout.write(f'  Categories: {len(cats)}')

        # --- price lists
        default_pl, _ = PriceList.all_objects.get_or_create(
            tenant=tenant, name='Standard Price List',
            defaults={'currency': 'USD', 'is_default': True, 'is_active': True},
        )
        vip_pl, _ = PriceList.all_objects.get_or_create(
            tenant=tenant, name='VIP Customers',
            defaults={'currency': 'USD', 'is_default': False, 'is_active': True},
        )
        self.stdout.write('  Price lists: 2 (default + VIP)')

        # --- price list items (best-effort - need a Product to link)
        try:
            from apps.plm.models import Product
            products = list(Product.objects.filter(tenant=tenant)[:2])
        except Exception:
            products = []
        items_created = 0
        if products:
            tiers = [(Decimal('1'), Decimal('100.00')),
                     (Decimal('10'), Decimal('90.00')),
                     (Decimal('100'), Decimal('75.00'))]
            for product in products:
                for min_qty, price in tiers:
                    _, created = PriceListItem.all_objects.get_or_create(
                        tenant=tenant, price_list=default_pl,
                        product=product, min_qty=min_qty,
                        defaults={'unit_price': price, 'discount_pct': Decimal('0')},
                    )
                    if created:
                        items_created += 1
        self.stdout.write(f'  Price list items: {items_created} new')

        # --- customers
        cat_keys = list(cats.values())
        wh = None
        try:
            from apps.inventory.models import Warehouse
            wh = Warehouse.objects.filter(tenant=tenant, is_default=True).first()
        except Exception:
            pass

        customers = []
        for i, (name, klass, status) in enumerate(CUSTOMERS_PER_TENANT):
            existing = Customer.all_objects.filter(tenant=tenant, name=name).first()
            if existing:
                customers.append(existing)
                continue
            cust = Customer(
                tenant=tenant, name=name, customer_class=klass, status=status,
                legal_name=name + ', Inc.',
                category=cat_keys[i % len(cat_keys)],
                email=faker.company_email(),
                phone=faker.phone_number()[:30],
                tax_id=f'TAX-{tenant.id}-{i:03d}',
                billing_address=faker.address(),
                shipping_address=faker.address(),
                city=faker.city(),
                state=faker.state(),
                postal_code=faker.postcode(),
                country='USA',
                currency='USD',
                payment_terms='net30',
                credit_limit=Decimal('50000') if klass == 'key' else Decimal('10000'),
                default_price_list=vip_pl if klass == 'key' else default_pl,
                default_warehouse=wh,
            )
            cust.save()
            customers.append(cust)
        self.stdout.write(f'  Customers: {len(customers)}')

        # --- contacts
        c_count = 0
        for cust in customers:
            if cust.contacts.exists():
                continue
            for j, role in enumerate(['buyer', 'accounts', 'shipping']):
                CustomerContact(
                    tenant=tenant, customer=cust,
                    full_name=faker.name(),
                    designation=faker.job()[:80],
                    role=role,
                    email=faker.email(),
                    phone_primary=faker.phone_number()[:30],
                    is_primary=(j == 0),
                    is_active=True,
                ).save()
                c_count += 1
        self.stdout.write(f'  Contacts: {c_count}')

        # --- communications
        comm_count = 0
        now = timezone.now()
        for k, (typ, direction, subject, status) in enumerate(COMM_TEMPLATES):
            cust = customers[k % len(customers)]
            existing = CommunicationLog.all_objects.filter(
                tenant=tenant, customer=cust, subject=subject,
            ).first()
            if existing:
                continue
            CommunicationLog(
                tenant=tenant, customer=cust,
                type=typ, direction=direction,
                subject=subject,
                body=faker.paragraph(nb_sentences=3),
                occurred_at=now - timedelta(days=k),
                status=status,
            ).save()
            comm_count += 1
        self.stdout.write(f'  Communications: {comm_count}')
