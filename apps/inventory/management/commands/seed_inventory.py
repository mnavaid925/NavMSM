"""Idempotent seeder for Inventory & Warehouse demo data.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush
  - Skips per-tenant if data already exists
  - Auto-numbered records (GRN-, TRF-, ADJ-, CC-) check existence before creating

Per Lesson L-09, all stdout text is plain ASCII (no Unicode arrows / dots /
emoji - the Windows cp1252 console crashes on them).

Per tenant produces:
    - 2 warehouses (MAIN, SEC) marked default+active and active respectively
    - Each warehouse: 3 zones (RECV, STOR, SHIP) x 4 bins = 24 bins
    - 8 StockItem rows seeded for finished-goods + 4 components
    - 1 completed GRN with 3 lines + putaway tasks
    - 6 movement rows spanning 3 movement types
    - 1 cycle count sheet with 4 lines (1 with variance)
    - 4 lots (one expiring in 15 days), 6 serial numbers on a finished good
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.plm.models import Product

from apps.inventory.models import (
    CycleCountLine, CycleCountSheet, GoodsReceiptNote, GRNLine, Lot, PutawayTask,
    SerialNumber, StockAdjustment, StockItem, StockMovement, StorageBin,
    Warehouse, WarehouseZone,
)
from apps.inventory.services.movements import post_movement


def _seed_warehouse_tree(tenant, stdout):
    if Warehouse.all_objects.filter(tenant=tenant).exists():
        stdout.write('  warehouses: skipped (already seeded)')
        return list(Warehouse.all_objects.filter(tenant=tenant).order_by('code'))

    manager = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
    warehouses = []
    seed = [
        ('MAIN', 'Main Warehouse', True),
        ('SEC', 'Secondary DC', False),
    ]
    for code, name, is_default in seed:
        wh = Warehouse.all_objects.create(
            tenant=tenant, code=code, name=name,
            address=f'{name} - 100 Industrial Park',
            manager=manager, is_default=is_default, is_active=True,
        )
        for z_code, z_name, z_type in [
            ('RECV', 'Receiving Dock', 'receiving'),
            ('STOR', 'Main Storage', 'storage'),
            ('SHIP', 'Shipping Dock', 'shipping'),
        ]:
            zone = WarehouseZone.all_objects.create(
                tenant=tenant, warehouse=wh, code=z_code, name=z_name, zone_type=z_type,
            )
            for n in range(1, 5):
                bin_type = 'pallet' if z_type == 'storage' else 'shelf'
                StorageBin.all_objects.create(
                    tenant=tenant, zone=zone,
                    code=f'{z_code}-{n:02d}', bin_type=bin_type,
                    capacity=Decimal('100'),
                    abc_class=('A' if n == 1 else 'B' if n == 2 else 'C') if z_type == 'storage' else '',
                )
        warehouses.append(wh)
    stdout.write(f'  warehouses: created {len(warehouses)} (with zones + bins)')
    return warehouses


def _seed_lots_and_serials(tenant, stdout):
    if Lot.all_objects.filter(tenant=tenant).exists():
        stdout.write('  lots/serials: skipped (already seeded)')
        return (
            list(Lot.all_objects.filter(tenant=tenant)),
            list(SerialNumber.all_objects.filter(tenant=tenant)),
        )

    finished = Product.all_objects.filter(
        tenant=tenant, product_type='finished_good',
    ).first()
    component = Product.all_objects.filter(
        tenant=tenant, product_type__in=('component', 'raw_material'),
    ).first()
    if not finished or not component:
        stdout.write('  lots/serials: no PLM products available; skipping')
        return [], []

    today = timezone.now().date()
    lots = []
    lot_specs = [
        ('LOT-2026-001', component, today - timedelta(days=120), today + timedelta(days=180), 'active'),
        ('LOT-2026-002', component, today - timedelta(days=60), today + timedelta(days=15), 'active'),  # expiring soon
        ('LOT-FG-001', finished, today - timedelta(days=30), today + timedelta(days=365), 'active'),
        ('LOT-FG-002', finished, today - timedelta(days=200), today - timedelta(days=10), 'expired'),  # expired
    ]
    for ln, product, mfd, exp, status in lot_specs:
        lot = Lot.all_objects.create(
            tenant=tenant, product=product, lot_number=ln,
            manufactured_date=mfd, expiry_date=exp, status=status,
            supplier_name='Demo Supplier Inc.',
        )
        lots.append(lot)

    fg_lot = lots[2]
    serials = []
    for i in range(1, 7):
        sn = SerialNumber.all_objects.create(
            tenant=tenant, product=finished, lot=fg_lot,
            serial_number=f'SN-{finished.sku}-{i:04d}',
            status='available',
        )
        serials.append(sn)
    stdout.write(f'  lots/serials: created {len(lots)} lots, {len(serials)} serials')
    return lots, serials


def _seed_initial_stock(tenant, warehouses, lots, stdout):
    if StockMovement.all_objects.filter(tenant=tenant).exists():
        stdout.write('  initial stock: skipped (already has movements)')
        return

    finished_goods = list(Product.all_objects.filter(
        tenant=tenant, product_type='finished_good',
    )[:2])
    components = list(Product.all_objects.filter(
        tenant=tenant, product_type__in=('component', 'raw_material'),
    )[:4])
    if not finished_goods or not components:
        stdout.write('  initial stock: no PLM products available; skipping')
        return

    main = warehouses[0]
    storage_bins = list(StorageBin.all_objects.filter(zone__warehouse=main, zone__zone_type='storage')[:4])
    if not storage_bins:
        stdout.write('  initial stock: no storage bins; skipping')
        return

    products = finished_goods + components
    fg_lot = next((l for l in lots if l.product == finished_goods[0]), None)
    cmp_lot = next((l for l in lots if l.product == components[0]), None)

    placement = []  # [(product, bin, lot)]
    count = 0
    for i, p in enumerate(products):
        bin = storage_bins[i % len(storage_bins)]
        lot = fg_lot if p == finished_goods[0] else (cmp_lot if p == components[0] else None)
        post_movement(
            tenant=tenant,
            movement_type='receipt',
            product=p,
            qty=Decimal('100'),
            to_bin=bin,
            lot=lot,
            reason='seed: initial stock',
            reference='SEED',
        )
        placement.append((p, bin, lot))
        count += 1

    # An issue, a transfer (issue+receipt), an adjustment (positive)
    if len(placement) >= 4:
        # issue from where component[0] was placed
        cmp0_p, cmp0_bin, cmp0_lot = next(
            ((pp, bb, ll) for pp, bb, ll in placement if pp == components[0]), placement[0]
        )
        post_movement(
            tenant=tenant, movement_type='issue',
            product=cmp0_p, qty=Decimal('5'),
            from_bin=cmp0_bin, lot=cmp0_lot,
            reason='seed: shop floor draw', reference='SEED',
        )
        count += 1

        cmp1_p, cmp1_bin, _ = next(
            ((pp, bb, ll) for pp, bb, ll in placement if pp == components[1]), placement[1]
        )
        # pick a different bin to transfer into
        dest_bin = next((b for b in storage_bins if b != cmp1_bin), storage_bins[0])
        post_movement(
            tenant=tenant, movement_type='transfer',
            product=cmp1_p, qty=Decimal('10'),
            from_bin=cmp1_bin, to_bin=dest_bin,
            reason='seed: rebalance', reference='SEED',
        )
        count += 1

        cmp2_p, cmp2_bin, _ = next(
            ((pp, bb, ll) for pp, bb, ll in placement if pp == components[2]), placement[2]
        )
        post_movement(
            tenant=tenant, movement_type='adjustment',
            product=cmp2_p, qty=Decimal('2'),
            to_bin=cmp2_bin,
            reason='seed: found stock', reference='SEED',
        )
        count += 1
    stdout.write(f'  initial stock: posted {count} movements')


def _seed_grn(tenant, warehouses, stdout):
    if GoodsReceiptNote.all_objects.filter(tenant=tenant).exists():
        stdout.write('  grn: skipped (already seeded)')
        return
    components = list(Product.all_objects.filter(
        tenant=tenant, product_type__in=('component', 'raw_material'),
    )[:3])
    if not components:
        stdout.write('  grn: no products; skipping')
        return
    main = warehouses[0]
    receiving_zone = WarehouseZone.all_objects.filter(
        warehouse=main, zone_type='receiving',
    ).first()
    if not receiving_zone:
        stdout.write('  grn: no receiving zone; skipping')
        return

    user = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
    grn = GoodsReceiptNote.all_objects.create(
        tenant=tenant, warehouse=main,
        supplier_name='Demo Supplier Inc.', po_reference='PO-DEMO-001',
        received_date=timezone.now().date() - timedelta(days=2),
        received_by=user, status='completed',
    )
    storage_bin = StorageBin.all_objects.filter(
        zone__warehouse=main, zone__zone_type='storage', is_blocked=False,
    ).first()
    for i, p in enumerate(components, start=1):
        line = GRNLine.all_objects.create(
            tenant=tenant, grn=grn, product=p,
            expected_qty=Decimal('50'), received_qty=Decimal('50'),
            lot_number=f'GRN-LOT-{i:03d}', receiving_zone=receiving_zone,
        )
        PutawayTask.all_objects.create(
            tenant=tenant, grn_line=line,
            suggested_bin=storage_bin, actual_bin=storage_bin,
            qty=Decimal('50'), strategy='nearest_empty',
            status='completed', completed_by=user,
            completed_at=timezone.now() - timedelta(hours=1),
        )
    stdout.write('  grn: created 1 completed GRN with 3 lines + putaway tasks')


def _seed_cycle_count(tenant, warehouses, stdout):
    if CycleCountSheet.all_objects.filter(tenant=tenant).exists():
        stdout.write('  cycle count: skipped (already seeded)')
        return
    components = list(Product.all_objects.filter(
        tenant=tenant, product_type__in=('component', 'raw_material'),
    )[:4])
    if not components:
        stdout.write('  cycle count: no products; skipping')
        return
    main = warehouses[0]
    bins = list(StorageBin.all_objects.filter(
        zone__warehouse=main, zone__zone_type='storage',
    )[:4])
    if not bins:
        stdout.write('  cycle count: no storage bins; skipping')
        return

    user = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
    sheet = CycleCountSheet.all_objects.create(
        tenant=tenant, warehouse=main,
        count_date=timezone.now().date(),
        counted_by=user, status='draft',
    )
    for i, (p, b) in enumerate(zip(components, bins)):
        # Last line carries a variance to make the demo realistic
        sys_q = Decimal('20')
        cnt_q = Decimal('20') if i < 3 else Decimal('18')
        CycleCountLine.all_objects.create(
            tenant=tenant, sheet=sheet, bin=b, product=p,
            system_qty=sys_q, counted_qty=cnt_q,
            recount_required=(sys_q != cnt_q),
        )
    stdout.write('  cycle count: created 1 sheet with 4 lines (1 with variance)')


class Command(BaseCommand):
    help = 'Seed Module 8 (Inventory & Warehouse) demo data per tenant. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Wipe all inventory data first.')

    def handle(self, *args, **options):
        if options.get('flush'):
            self.stdout.write('flushing all inventory data...')
            for model in (
                StockMovement, StockItem, PutawayTask, GRNLine, GoodsReceiptNote,
                CycleCountLine, CycleCountSheet, StockAdjustment,
                SerialNumber, Lot,
                StorageBin, WarehouseZone, Warehouse,
            ):
                model.all_objects.all().delete()

        tenants = list(Tenant.objects.filter(is_active=True))
        if not tenants:
            self.stdout.write(self.style.WARNING('No active tenants. Run seed_tenants first.'))
            return

        for tenant in tenants:
            self.stdout.write(self.style.HTTP_INFO(f'tenant: {tenant.slug}'))
            warehouses = _seed_warehouse_tree(tenant, self.stdout)
            lots, serials = _seed_lots_and_serials(tenant, self.stdout)
            _seed_initial_stock(tenant, warehouses, lots, self.stdout)
            _seed_grn(tenant, warehouses, self.stdout)
            _seed_cycle_count(tenant, warehouses, self.stdout)

        self.stdout.write(self.style.SUCCESS('seed_inventory: done.'))
        self.stdout.write(
            'Log in as a tenant admin (admin_acme / Welcome@123) to view the data. '
            'The Django superuser has tenant=None and will see empty pages by design.'
        )
