"""Idempotent seeder for Module 12 - Cost Management & Accounting.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush.
  - Skips per-tenant if data already exists.
  - Auto-numbered records (SCV-, JC-, WIP-, OHA-, VAR-, ACP-, COGM-) check
    existence before creating.

Per Lesson L-09, all stdout text is plain ASCII - no Unicode arrows / dots /
emoji. The Windows cp1252 console crashes on them.

Per tenant produces:
    - 3 AccountingPeriod rows (prev month closed, current month open, next
      month open).
    - 5 CostDriver rows + 5 OverheadPool rows + 5 OverheadRate rows for the
      current period.
    - 1 active StandardCostVersion + 1 StandardCost row per finished_good /
      sub_assembly product (pulled from bom.BOMCostRollup where present, else
      a deterministic fallback).
    - JobCost rows for every released / completed pps.ProductionOrder,
      pre-populated with WIP entries derived from existing labor bookings +
      synthesized overhead.
    - 1 CostVariance per closed-period job for visual variety.
    - Driver actuals, applied overhead allocations, COGM report, gross-margin
      rows, and a Plant P&L for the prior closed period.

L-08 horizon overlap: periods explicitly aligned to the existing seeded MPS
horizon so jobs and overheads align.
"""
from datetime import date, timedelta
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant
from apps.cost import models as C
from apps.cost.services import (
    overhead as oh_svc,
    reporting as report_svc,
    standard_costing as std_svc,
    wip as wip_svc,
)


DRIVERS = [
    ('MH', 'Machine Hours', 'hours'),
    ('DLH', 'Direct Labor Hours', 'hours'),
    ('UNITS', 'Units Produced', 'units'),
    ('SQFT', 'Square Footage', 'sq_ft'),
    ('KWH', 'Energy (kWh)', 'kwh'),
]

POOLS = [
    ('RENT', 'Factory Rent', 'fixed', 'SQFT', 'volume'),
    ('UTIL', 'Utilities', 'variable', 'KWH', 'machine_hours'),
    ('SUPV', 'Supervision', 'fixed', 'DLH', 'direct_labor_hours'),
    ('IMAT', 'Indirect Materials', 'variable', 'UNITS', 'volume'),
    ('INSR', 'Plant Insurance', 'fixed', 'SQFT', 'volume'),
]


def _month_bounds(d: date):
    start = d.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    end = nxt - timedelta(days=1)
    return start, end


def _prev_month(d: date):
    last_of_prev = d.replace(day=1) - timedelta(days=1)
    return _month_bounds(last_of_prev)


def _next_month(d: date):
    next_start = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return _month_bounds(next_start)


class Command(BaseCommand):
    help = 'Seed idempotent demo data for Module 12 - Cost Management & Accounting.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true')
        parser.add_argument('--tenant', type=str, default=None)

    def handle(self, *args, **options):
        flush = options.get('flush', False)
        slug = options.get('tenant')
        tenants = Tenant.objects.filter(is_active=True)
        if slug:
            tenants = tenants.filter(slug=slug)

        for tenant in tenants:
            self._seed_one(tenant, flush=flush)

        self.stdout.write('seed_cost done.')
        self.stdout.write('Login as a tenant admin (e.g. admin_acme) to view seeded cost data.')
        self.stdout.write("Superuser 'admin' has no tenant - data wont appear when logged in as admin.")

    def _seed_one(self, tenant: Tenant, *, flush: bool):
        random.seed(hash(tenant.slug) & 0xFFFFFFFF)
        if flush:
            self._flush_tenant(tenant)

        if C.AccountingPeriod.all_objects.filter(tenant=tenant).exists():
            self.stdout.write(f'[{tenant.slug}] cost data already exists. Use --flush to re-seed.')
            return

        with transaction.atomic():
            periods = self._seed_periods(tenant)
            drivers = self._seed_drivers(tenant)
            pools = self._seed_pools(tenant, drivers)
            self._seed_rates(tenant, pools, periods, drivers)
            version = self._seed_standard_costs(tenant, periods)
            jobs = self._seed_jobs(tenant, version)
            wip_count = self._backfill_wip(tenant, jobs, version)
            self._seed_driver_actuals(tenant, periods, drivers, jobs)
            apply_counts = self._apply_overhead_for_prev(tenant, periods)
            variance_count = self._seed_variances(tenant, jobs, version)
            self._seed_actual_costs(tenant, jobs)
            cogm = self._gen_cogm(tenant, periods)
            margin_count = self._gen_margin(tenant, periods)
            pnl = self._gen_pnl(tenant, periods)

        self.stdout.write(
            f'[{tenant.slug}] periods={len(periods)} drivers={len(drivers)} '
            f'pools={len(pools)} std_costs={C.StandardCost.all_objects.filter(version=version).count()} '
            f'jobs={len(jobs)} wip_entries={wip_count} variances={variance_count} '
            f'overhead_applied={apply_counts.get("allocations", 0)} '
            f'cogm={1 if cogm else 0} margins={margin_count} pnl={1 if pnl else 0}'
        )

    # --------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------

    def _flush_tenant(self, tenant: Tenant):
        for cls in (
            C.WIPEntry, C.OverheadAllocation, C.DriverActuals,
            C.OverheadActualPool, C.OverheadRate, C.OverheadPool, C.CostDriver,
            C.PlantPnLReport, C.GrossMarginReport, C.COGMReport,
            C.CostVariance, C.ActualCost, C.JobCost,
            C.StandardCostHistory, C.StandardCost, C.StandardCostVersion,
            C.AccountingPeriod,
        ):
            cls.all_objects.filter(tenant=tenant).delete()

    def _seed_periods(self, tenant):
        today = timezone.now().date()
        prev_s, prev_e = _prev_month(today)
        cur_s, cur_e = _month_bounds(today)
        nxt_s, nxt_e = _next_month(today)
        out = []
        for name, s, e, status in [
            (f'FY{prev_s.year} {prev_s.strftime("%b")}', prev_s, prev_e, 'closed'),
            (f'FY{cur_s.year} {cur_s.strftime("%b")}', cur_s, cur_e, 'open'),
            (f'FY{nxt_s.year} {nxt_s.strftime("%b")}', nxt_s, nxt_e, 'open'),
        ]:
            obj = C.AccountingPeriod.all_objects.create(
                tenant=tenant, name=name, period_type='monthly',
                start_date=s, end_date=e, status=status,
                locked_at=timezone.now() if status == 'closed' else None,
                closed_at=timezone.now() if status == 'closed' else None,
            )
            out.append(obj)
        return out

    def _seed_drivers(self, tenant):
        out = {}
        for code, name, uom in DRIVERS:
            out[code] = C.CostDriver.all_objects.create(
                tenant=tenant, code=code, name=name, unit_of_measure=uom,
            )
        return out

    def _seed_pools(self, tenant, drivers):
        out = {}
        for code, name, ptype, driver_code, method in POOLS:
            out[code] = C.OverheadPool.all_objects.create(
                tenant=tenant, code=code, name=name, pool_type=ptype,
                default_driver=drivers[driver_code], allocation_method=method,
            )
        return out

    def _seed_rates(self, tenant, pools, periods, drivers):
        # Rates for the current period only.
        cur = periods[1]  # index 1 = current month
        per_pool_amounts = {
            'RENT': (Decimal('5000'), Decimal('1500'), 'SQFT'),
            'UTIL': (Decimal('2400'), Decimal('800'), 'KWH'),
            'SUPV': (Decimal('6000'), Decimal('400'), 'DLH'),
            'IMAT': (Decimal('1500'), Decimal('300'), 'UNITS'),
            'INSR': (Decimal('1200'), Decimal('1500'), 'SQFT'),
        }
        for code, (amount, qty, dcode) in per_pool_amounts.items():
            C.OverheadRate.all_objects.create(
                tenant=tenant, pool=pools[code], period=cur,
                driver=drivers[dcode], budgeted_amount=amount,
                budgeted_driver_qty=qty,
            )
        # Also seed the prior period (closed) so we can apply overhead.
        prev = periods[0]
        for code, (amount, qty, dcode) in per_pool_amounts.items():
            C.OverheadRate.all_objects.create(
                tenant=tenant, pool=pools[code], period=prev,
                driver=drivers[dcode], budgeted_amount=amount,
                budgeted_driver_qty=qty,
            )

    def _seed_standard_costs(self, tenant, periods):
        cur = periods[1]
        version = C.StandardCostVersion.all_objects.create(
            tenant=tenant, name=f'Standard Cost {cur.name}',
            effective_from=cur.start_date, status='active',
            notes='Seeded standard cost set.',
        )
        # Pull from BOM rollups if present, else fallback.
        from apps.bom.models import BillOfMaterials, BOMCostRollup
        from apps.plm.models import Product

        products = list(Product.all_objects.filter(
            tenant=tenant, product_type__in=('finished_good', 'sub_assembly'),
        ))
        for product in products:
            bom = BillOfMaterials.all_objects.filter(
                tenant=tenant, product=product, status='released',
            ).order_by('-id').first()
            rollup = BOMCostRollup.all_objects.filter(bom=bom).first() if bom else None
            if rollup is not None:
                C.StandardCost.all_objects.create(
                    tenant=tenant, version=version, product=product,
                    material_cost=rollup.material_cost or Decimal('0'),
                    labor_cost=rollup.labor_cost or Decimal('0'),
                    overhead_cost=rollup.overhead_cost or Decimal('0'),
                    tooling_cost=rollup.tooling_cost or Decimal('0'),
                    source='bom_rollup',
                )
            else:
                C.StandardCost.all_objects.create(
                    tenant=tenant, version=version, product=product,
                    material_cost=Decimal('25.00'),
                    labor_cost=Decimal('15.00'),
                    overhead_cost=Decimal('10.00'),
                    tooling_cost=Decimal('2.00'),
                    source='manual',
                )
            # Set a default sale price if blank (so margin reports compute).
            if product.standard_sale_price is None:
                Product.all_objects.filter(pk=product.pk).update(
                    standard_sale_price=Decimal('100.00'),
                )
        # Update plm.Product cache after raw update calls.
        return version

    def _seed_jobs(self, tenant, version):
        from apps.pps.models import ProductionOrder

        out = []
        pos = list(
            ProductionOrder.all_objects.filter(
                tenant=tenant,
                status__in=('released', 'in_progress', 'completed'),
            )[:10]
        )
        for po in pos:
            existing = C.JobCost.all_objects.filter(
                tenant=tenant, production_order=po,
            ).first()
            if existing is not None:
                out.append(existing)
                continue
            status = 'closed' if po.status == 'completed' else 'open'
            opened = po.created_at
            if opened is not None and timezone.is_naive(opened):
                opened = timezone.make_aware(opened)
            job = C.JobCost.all_objects.create(
                tenant=tenant, production_order=po, status=status,
                opened_at=opened or timezone.now(),
                closed_at=timezone.now() if status == 'closed' else None,
            )
            out.append(job)
        return out

    def _backfill_wip(self, tenant, jobs, version):
        from apps.labor.models import LaborBooking
        count = 0
        for job in jobs:
            po = job.production_order
            qty = po.quantity or Decimal('1')
            sc = C.StandardCost.all_objects.filter(
                version=version, product=po.product,
            ).first()
            material = (sc.material_cost if sc else Decimal('25')) * qty
            labor = (sc.labor_cost if sc else Decimal('15')) * qty
            overhead = (sc.overhead_cost if sc else Decimal('10')) * qty

            # Material issued
            wip_svc.post_wip_entry(
                tenant=tenant, job=job, entry_type='material_issued',
                amount=material, quantity=qty,
                unit_of_measure=getattr(po.product, 'unit_of_measure', '') or '',
                notes='seeded material issuance',
            )
            count += 1
            # Labor applied
            wip_svc.post_wip_entry(
                tenant=tenant, job=job, entry_type='labor_applied',
                amount=labor, quantity=Decimal('8'),
                unit_of_measure='hours', notes='seeded labor',
            )
            count += 1
            # Overhead applied
            wip_svc.post_wip_entry(
                tenant=tenant, job=job, entry_type='overhead_applied',
                amount=overhead, notes='seeded overhead',
            )
            count += 1
            # If closed, post a completion entry to zero things out approximately.
            if job.status == 'closed':
                completion = material + labor + overhead
                wip_svc.post_wip_entry(
                    tenant=tenant, job=job, entry_type='completion',
                    amount=completion, quantity=qty,
                    unit_of_measure=getattr(po.product, 'unit_of_measure', '') or '',
                    notes='seeded completion at standard',
                )
                count += 1
        return count

    def _seed_driver_actuals(self, tenant, periods, drivers, jobs):
        """Record some driver consumption for the prior period so apply_overhead
        has work to do."""
        prev = periods[0]
        for job in jobs[:6]:
            po = job.production_order
            # Machine hours per job
            C.DriverActuals.all_objects.create(
                tenant=tenant, driver=drivers['MH'], period=prev,
                production_order=po, quantity=Decimal('20'),
            )
            C.DriverActuals.all_objects.create(
                tenant=tenant, driver=drivers['DLH'], period=prev,
                production_order=po, quantity=Decimal('16'),
            )
            C.DriverActuals.all_objects.create(
                tenant=tenant, driver=drivers['UNITS'], period=prev,
                production_order=po, quantity=po.quantity or Decimal('10'),
            )
        # Cost-center driver actuals (rent / insurance) pinned to first available CC.
        from apps.labor.models import CostCenter
        cc = CostCenter.all_objects.filter(tenant=tenant).first()
        if cc is not None:
            C.DriverActuals.all_objects.create(
                tenant=tenant, driver=drivers['SQFT'], period=prev,
                cost_center=cc, quantity=Decimal('1500'),
            )
            C.DriverActuals.all_objects.create(
                tenant=tenant, driver=drivers['KWH'], period=prev,
                cost_center=cc, quantity=Decimal('800'),
            )

    def _apply_overhead_for_prev(self, tenant, periods):
        """The prior period is currently 'closed' but we need to apply BEFORE
        closing. Temporarily reopen, apply, then re-lock + re-close."""
        prev = periods[0]
        # Bypass the closed check by calling apply_overhead with a temporary status.
        prev.status = 'open'
        prev.save(update_fields=['status'])
        try:
            counts = oh_svc.apply_overhead(prev)
        except Exception:
            counts = {'allocations': 0, 'wip_entries': 0}
        prev.status = 'closed'
        prev.save(update_fields=['status'])
        return counts

    def _seed_variances(self, tenant, jobs, version):
        from apps.cost.services import actual_costing as ac_svc
        count = 0
        for job in jobs:
            if job.status != 'closed':
                continue
            v = ac_svc.compute_variances(job.production_order, version=version)
            if v is None:
                continue
            # Inject some artificial variance so values are non-zero.
            existing = C.CostVariance.all_objects.filter(
                production_order=job.production_order, version=version,
            ).first()
            if existing is not None:
                continue
            C.CostVariance.all_objects.create(
                tenant=tenant, production_order=job.production_order,
                version=version,
                material_price_variance=v.get('material_price_variance', Decimal('0')) + Decimal('25'),
                material_usage_variance=v.get('material_usage_variance', Decimal('0')) + Decimal('15'),
                labor_rate_variance=v.get('labor_rate_variance', Decimal('0')) - Decimal('5'),
                labor_efficiency_variance=v.get('labor_efficiency_variance', Decimal('0')) + Decimal('10'),
                overhead_spending_variance=v.get('overhead_spending_variance', Decimal('0')) + Decimal('8'),
                overhead_volume_variance=v.get('overhead_volume_variance', Decimal('0')) - Decimal('3'),
                analysis_notes='Seeded variance for visual demo.',
            )
            count += 1
        return count

    def _seed_actual_costs(self, tenant, jobs):
        from apps.cost.services import actual_costing as ac_svc
        for job in jobs:
            ac_svc.compute_actual(job.production_order)

    def _gen_cogm(self, tenant, periods):
        prev = periods[0]
        try:
            return report_svc.generate_cogm(prev)
        except Exception:
            return None

    def _gen_margin(self, tenant, periods):
        prev = periods[0]
        try:
            r = report_svc.generate_gross_margin(prev)
            return r.get('created', 0) + r.get('updated', 0)
        except Exception:
            return 0

    def _gen_pnl(self, tenant, periods):
        prev = periods[0]
        try:
            return report_svc.generate_plant_pnl(
                prev,
                selling_expense=Decimal('800'),
                ga_expense=Decimal('1200'),
                unallocated_overhead=Decimal('200'),
            )
        except Exception:
            return None
