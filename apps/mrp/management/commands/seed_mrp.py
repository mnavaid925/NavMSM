"""Idempotent seeder for Material Requirements Planning demo data.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush
  - Skips per-tenant if data already exists
  - Auto-numbered records (FRUN-, MRP-, MRPRUN-, MPR-) check existence before creating

Per tenant produces:
    - 2 ForecastModels (moving_avg, naive_seasonal)
    - 12 SeasonalityProfile rows for 2 finished-goods (monthly indices)
    - 1 completed ForecastRun + ~32 ForecastResult rows (8 products × 4 periods)
    - ~10 InventorySnapshot rows (per finished-good + components)
    - ~5 ScheduledReceipt rows (open POs / planned production)
    - 1 completed MRPCalculation linked to the seeded MPS, with NetRequirement,
      MRPPurchaseRequisition, and MRPException rows
    - 1 completed MRPRun + MRPRunResult
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product
from apps.pps.models import MasterProductionSchedule

from apps.mrp.models import (
    ForecastModel, ForecastResult, ForecastRun, InventorySnapshot,
    MRPCalculation, MRPPurchaseRequisition, MRPRun, MRPRunResult,
    NetRequirement, ScheduledReceipt, SeasonalityProfile,
)
from apps.mrp.services import exceptions as exception_service
from apps.mrp.services import mrp_engine


def _next_number(model, tenant, field, prefix, width=5):
    last = model.all_objects.filter(tenant=tenant).aggregate(Max(field))[f'{field}__max']
    n = 1
    if last:
        import re
        m = re.match(rf'^{prefix}-(\d+)$', str(last))
        if m:
            n = int(m.group(1)) + 1
        else:
            n = model.all_objects.filter(tenant=tenant).count() + 1
    return f'{prefix}-{n:0{width}d}'


def _seed_forecast_models(tenant, admin_user, stdout):
    fixtures = [
        ('Default Moving Avg (3-period)', 'moving_avg', {'window': 3}, 'week', 12),
        ('Naive Seasonal (12-month)', 'naive_seasonal', {'season_length': 12}, 'month', 12),
    ]
    created = 0
    out = []
    for name, method, params, period_type, horizon in fixtures:
        fm, was = ForecastModel.all_objects.get_or_create(
            tenant=tenant, name=name,
            defaults={
                'method': method, 'params': params,
                'period_type': period_type, 'horizon_periods': horizon,
                'is_active': True, 'created_by': admin_user,
                'description': f'Seeded {method} model for demo MRP runs.',
            },
        )
        out.append(fm)
        if was:
            created += 1
    stdout.write(f'  forecast models: {created} created')
    return out


def _seed_seasonality(tenant, products_by_sku, stdout):
    targets = ['SKU-4001', 'SKU-4002']
    indices = ['1.10', '1.05', '0.95', '0.90', '0.85', '0.80',
               '0.85', '0.95', '1.05', '1.15', '1.25', '1.20']
    created = 0
    for sku in targets:
        product = products_by_sku.get(sku)
        if product is None:
            continue
        for month in range(1, 13):
            _, was = SeasonalityProfile.all_objects.get_or_create(
                tenant=tenant, product=product,
                period_type='month', period_index=month,
                defaults={
                    'seasonal_index': Decimal(indices[month - 1]),
                    'notes': 'Seeded monthly seasonality.',
                },
            )
            if was:
                created += 1
    stdout.write(f'  seasonality profiles: {created} created')


def _seed_forecast_run(tenant, forecast_models, products_by_sku, admin_user, stdout):
    if ForecastRun.all_objects.filter(tenant=tenant).exists():
        stdout.write('  forecast runs: skipped (already seeded)')
        return
    fm = forecast_models[0] if forecast_models else None
    if fm is None:
        return
    run_number = _next_number(ForecastRun, tenant, 'run_number', 'FRUN')
    run = ForecastRun.all_objects.create(
        tenant=tenant, run_number=run_number,
        forecast_model=fm, run_date=date.today(),
        status='completed',
        started_by=admin_user,
        started_at=timezone.now() - timedelta(minutes=2),
        finished_at=timezone.now(),
        notes='Seeded completed forecast run.',
    )
    targets = ['SKU-4001', 'SKU-4002', 'SKU-4003', 'SKU-4004']
    today = date.today()
    created = 0
    for sku in targets:
        product = products_by_sku.get(sku)
        if product is None:
            continue
        for wk in range(4):
            ps = today + timedelta(days=wk * 7)
            pe = ps + timedelta(days=6)
            qty = Decimal(str(60 + wk * 5 + random.randint(0, 20)))
            ForecastResult.all_objects.create(
                tenant=tenant, run=run, product=product,
                period_start=ps, period_end=pe,
                forecasted_qty=qty,
                lower_bound=qty * Decimal('0.85'),
                upper_bound=qty * Decimal('1.15'),
                confidence_pct=Decimal('80'),
            )
            created += 1
    stdout.write(f'  forecast results: {created} created (run {run.run_number})')


def _seed_inventory(tenant, products_by_sku, stdout):
    fixtures = [
        # (sku, on_hand, safety, reorder, lead_days, method, value, max)
        ('SKU-4001', 25, 10, 20, 14, 'l4l', 0, 0),
        ('SKU-4002', 30, 8, 18, 10, 'foq', 50, 0),
        ('SKU-4003', 12, 5, 15, 21, 'poq', 4, 0),
        ('SKU-4004', 40, 15, 30, 7, 'min_max', 20, 100),
        ('SKU-4005', 50, 20, 35, 14, 'l4l', 0, 0),
        ('SKU-3001', 200, 50, 100, 7, 'foq', 100, 0),
        ('SKU-3002', 500, 100, 200, 14, 'l4l', 0, 0),
        ('SKU-2001', 800, 200, 400, 5, 'foq', 250, 0),
    ]
    created = 0
    for sku, oh, ss, rop, lt, method, val, mx in fixtures:
        product = products_by_sku.get(sku)
        if product is None:
            continue
        _, was = InventorySnapshot.all_objects.get_or_create(
            tenant=tenant, product=product,
            defaults={
                'on_hand_qty': Decimal(str(oh)),
                'safety_stock': Decimal(str(ss)),
                'reorder_point': Decimal(str(rop)),
                'lead_time_days': lt,
                'lot_size_method': method,
                'lot_size_value': Decimal(str(val)),
                'lot_size_max': Decimal(str(mx)),
                'as_of_date': date.today(),
                'notes': 'Seeded snapshot — replace once Inventory module ships.',
            },
        )
        if was:
            created += 1
    stdout.write(f'  inventory snapshots: {created} created')


def _seed_receipts(tenant, products_by_sku, stdout):
    if ScheduledReceipt.all_objects.filter(tenant=tenant).exists():
        stdout.write('  scheduled receipts: skipped (already seeded)')
        return
    fixtures = [
        ('SKU-3001', 'open_po', 200, 7, 'PO-EXT-1042'),
        ('SKU-3002', 'open_po', 300, 10, 'PO-EXT-1051'),
        ('SKU-2001', 'open_po', 500, 5, 'PO-EXT-1060'),
        ('SKU-4001', 'planned_production', 30, 14, 'WO-PLAN-201'),
        ('SKU-4003', 'transfer', 10, 4, 'XFR-WH-1'),
    ]
    created = 0
    today = date.today()
    for sku, rtype, qty, days, ref in fixtures:
        product = products_by_sku.get(sku)
        if product is None:
            continue
        ScheduledReceipt.all_objects.create(
            tenant=tenant, product=product,
            receipt_type=rtype, quantity=Decimal(str(qty)),
            expected_date=today + timedelta(days=days),
            reference=ref,
            notes='Seeded receipt for demo MRP run.',
        )
        created += 1
    stdout.write(f'  scheduled receipts: {created} created')


def _seed_mrp_run(tenant, admin_user, stdout):
    if MRPRun.all_objects.filter(tenant=tenant).exists():
        stdout.write('  MRP runs: skipped (already seeded)')
        return

    mps = MasterProductionSchedule.all_objects.filter(
        tenant=tenant, status='released',
    ).first()

    # Align MRP horizon with the MPS horizon (when an MPS is linked) so that
    # seeded MPS lines actually fall inside the MRP window — otherwise the
    # engine sees zero demand and produces no net requirements / PRs.
    if mps is not None:
        horizon_start = mps.horizon_start
        horizon_end = mps.horizon_end
    else:
        today = date.today()
        horizon_start = today
        horizon_end = today + timedelta(days=28)

    calc = MRPCalculation.all_objects.create(
        tenant=tenant,
        mrp_number=_next_number(MRPCalculation, tenant, 'mrp_number', 'MRP'),
        name=f'Demo MRP {horizon_start:%b %Y}',
        horizon_start=horizon_start, horizon_end=horizon_end,
        time_bucket='week',
        status='running',
        source_mps=mps,
        description='Seeded MRP calculation for demo (auto-completed).',
        started_by=admin_user,
        started_at=timezone.now() - timedelta(minutes=1),
    )
    run = MRPRun.all_objects.create(
        tenant=tenant,
        run_number=_next_number(MRPRun, tenant, 'run_number', 'MRPRUN'),
        name='Initial regenerative run',
        run_type='regenerative',
        status='running',
        mrp_calculation=calc,
        source_mps=mps,
        started_by=admin_user,
        started_at=timezone.now() - timedelta(minutes=1),
    )

    try:
        # Bind tenant for the engine's queries (TenantManager picks it up)
        set_current_tenant(tenant)
        summary = mrp_engine.run_mrp(calc, mode='regenerative')
        exc_count = exception_service.generate_exceptions(
            calc, skipped_no_bom_skus=summary.skipped_no_bom,
        )

        from django.db.models import Sum
        agg = NetRequirement.all_objects.filter(mrp_calculation=calc).aggregate(
            gross=Sum('gross_requirement'), net=Sum('net_requirement'),
        )
        gross = agg['gross'] or Decimal('0')
        net = agg['net'] or Decimal('0')
        coverage = Decimal('100')
        if gross > 0:
            coverage = ((gross - net) / gross) * Decimal('100')
            if coverage < 0:
                coverage = Decimal('0')
        late = summary.notes.count('late')  # not strictly accurate; expanded below
        # Use exception store for actual late_order count
        from apps.mrp.models import MRPException as _MRPException
        late = _MRPException.all_objects.filter(
            mrp_calculation=calc, exception_type='late_order',
        ).count()
        MRPRunResult.all_objects.create(
            tenant=tenant, run=run,
            total_planned_orders=summary.total_planned_orders,
            total_pr_suggestions=summary.total_pr_suggestions,
            total_exceptions=exc_count,
            late_orders_count=late,
            coverage_pct=coverage.quantize(Decimal('0.01')),
            summary_json={
                'skipped_no_bom': summary.skipped_no_bom,
                'notes': summary.notes,
            },
            computed_at=timezone.now(),
        )
        run.status = 'completed'
        run.finished_at = timezone.now()
        run.save()
        calc.status = 'completed'
        calc.finished_at = timezone.now()
        calc.save()
        stdout.write(
            f'  MRP run: {run.run_number} completed — '
            f'{summary.total_planned_orders} planned orders · '
            f'{summary.total_pr_suggestions} PRs · {exc_count} exceptions'
        )
    except Exception as exc:
        run.status = 'failed'
        run.finished_at = timezone.now()
        run.error_message = str(exc)
        run.save()
        calc.status = 'failed'
        calc.finished_at = timezone.now()
        calc.error_message = str(exc)
        calc.save()
        stdout.write(f'  MRP run failed: {exc}')
    finally:
        set_current_tenant(None)


class Command(BaseCommand):
    help = 'Seed Material Requirements Planning demo data per active tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Wipe MRP data for the 3 demo tenants and re-seed.',
        )

    def handle(self, *args, **options):
        if options['flush']:
            slugs = ['acme', 'globex', 'stark']
            tenants = Tenant.objects.filter(slug__in=slugs)
            self.stdout.write(self.style.WARNING(
                f'Flushing MRP data for {tenants.count()} demo tenants...'
            ))
            for model in (MRPRunResult, MRPRun, MRPCalculation, ScheduledReceipt,
                          InventorySnapshot, ForecastResult, ForecastRun,
                          SeasonalityProfile, ForecastModel):
                model.all_objects.filter(tenant__in=tenants).delete()

        for tenant in Tenant.objects.filter(is_active=True):
            self.stdout.write(self.style.HTTP_INFO(f'\n-> Tenant: {tenant.name}'))
            admin_user = User.objects.filter(
                tenant=tenant, is_tenant_admin=True,
            ).first()
            if admin_user is None:
                self.stdout.write('  no tenant admin — skipping')
                continue

            products = list(Product.all_objects.filter(tenant=tenant))
            products_by_sku = {p.sku: p for p in products}
            if not products_by_sku:
                self.stdout.write('  no products — run seed_plm first; skipping')
                continue

            forecast_models = _seed_forecast_models(tenant, admin_user, self.stdout)
            _seed_seasonality(tenant, products_by_sku, self.stdout)
            _seed_forecast_run(tenant, forecast_models, products_by_sku, admin_user, self.stdout)
            _seed_inventory(tenant, products_by_sku, self.stdout)
            _seed_receipts(tenant, products_by_sku, self.stdout)
            _seed_mrp_run(tenant, admin_user, self.stdout)

        self.stdout.write(self.style.SUCCESS('\nMRP seed complete.'))
        self.stdout.write(self.style.WARNING(
            'Reminder: superuser "admin" has tenant=None — log in as a tenant '
            'admin (e.g. admin_acme / Welcome@123) to see MRP data.'
        ))
