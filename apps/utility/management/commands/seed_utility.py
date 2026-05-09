"""Idempotent seeder for Module 14 - Energy & Utility Management.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush.
  - Skips per-tenant if data already exists (Lesson L-12).
  - Auto-numbered records (MTR-, UC-, TRF-, UAL-, DRE-, CE-, BCR-) check
    existence before creating and rely on the model's save() retry pattern.

Per Lesson L-09, all stdout text is plain ASCII - no Unicode arrows /
dots / emoji. The Windows cp1252 console crashes on them.

Per Lesson L-08, consumption window is anchored to the prior + current
``cost.AccountingPeriod`` so the rows fall inside the existing period.

Per tenant produces:
    - 6 UtilityType rows (electricity / water / natural_gas / steam /
      compressed_air / fuel_oil). Electricity is linked to cost.CostDriver
      'KWH' when present.
    - 5 UtilityTariff rows (one per type except fuel_oil), with flat-rate
      pricing in USD anchored to the current accounting period.
    - 3 TOURateBand rows on the electricity tariff (peak / shoulder /
      off_peak; weekday + weekend windows).
    - 1 DemandResponseEvent (voluntary, scheduled tomorrow 14:00-17:00).
    - 4 UtilityMeter rows (MAIN-ELEC-01 / MAIN-WATER-01 / MAIN-GAS-01 /
      LINE-2-ELEC-01 sub-meter).
    - 30 days of UtilityConsumption per meter spanning prior + current
      accounting periods. Electricity meters use eam.AssetMeterReading
      writes so the post_save auto-feed signal cascades a UtilityConsumption
      (proves the cross-module hook). Water / gas / etc. write
      UtilityConsumption directly via services.meters.post_consumption,
      letting the consumption -> CarbonEmission post_save cascade.
    - 5 EmissionFactor rows (electricity_grid scope_2, natural_gas scope_1,
      water scope_3, fuel_oil scope_1, employee_commute scope_3).
    - CarbonEmission rows are auto-emitted by the post_save signal.
    - 1 UtilityAllocation per metered cost_center for the current period
      via services.allocation.post_allocation (writes matching
      cost.DriverActuals).
    - 1 SustainabilityKPI for prior + current period.
    - 1 BenchmarkSnapshot for prior period.
    - 1 BenchmarkComparison (period-over-period: prior vs current).
"""
from datetime import datetime, timedelta, time as dtime
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Tenant
from apps.utility import models as U
from apps.utility.services import (
    allocation as alloc_svc,
    benchmark as bench_svc,
    carbon as carbon_svc,
    meters as meter_svc,
)


# Utility type catalog.  (code, name, unit_of_measure, optional driver code).
UTILITY_TYPES = [
    ('electricity', 'Electricity', 'kwh', 'KWH'),
    ('water', 'Water', 'm3', None),
    ('natural_gas', 'Natural Gas', 'm3', None),
    ('steam', 'Steam', 'kg', None),
    ('compressed_air', 'Compressed Air', 'scfm', None),
    ('fuel_oil', 'Fuel Oil', 'l', None),
]

# Tariff catalog (utility code, flat_rate per unit, currency).  Fuel oil
# deliberately has no tariff per spec (it is consumed via deliveries).
TARIFFS = [
    ('electricity', Decimal('0.120000'), 'USD'),
    ('water', Decimal('0.003000'), 'USD'),
    ('natural_gas', Decimal('0.450000'), 'USD'),
    ('steam', Decimal('0.080000'), 'USD'),
    ('compressed_air', Decimal('0.020000'), 'USD'),
]

# TOU bands attached to the electricity tariff only.
# (band_type, day_of_week, start_time, end_time, rate)
TOU_BANDS = [
    ('peak', 'weekday', dtime(9, 0), dtime(13, 0), Decimal('0.180000')),
    ('shoulder', 'weekday', dtime(13, 0), dtime(17, 0), Decimal('0.120000')),
    ('off_peak', 'weekday', dtime(17, 0), dtime(9, 0), Decimal('0.060000')),
    ('off_peak', 'weekend', dtime(0, 0), dtime(23, 59), Decimal('0.060000')),
]

# Meter catalog.  (meter_number, utility_code, name, source, parent_number).
METERS = [
    ('MAIN-ELEC-01', 'electricity', 'Main Electricity Meter', 'eam_meter', None),
    ('MAIN-WATER-01', 'water', 'Main Water Meter', 'manual', None),
    ('MAIN-GAS-01', 'natural_gas', 'Main Gas Meter', 'manual', None),
    ('LINE-2-ELEC-01', 'electricity', 'Line 2 Electricity Sub-meter',
     'eam_meter', 'MAIN-ELEC-01'),
]

# EmissionFactor catalog (source_type, scope, factor, unit, label).
EMISSION_FACTORS = [
    ('electricity_grid', 'scope_2', Decimal('0.420000'), 'kwh', 'Grid Electricity (kgCO2e/kWh)'),
    ('natural_gas', 'scope_1', Decimal('1.890000'), 'm3', 'Natural Gas (kgCO2e/m3)'),
    ('water', 'scope_3', Decimal('0.340000'), 'm3', 'Municipal Water (kgCO2e/m3)'),
    ('fuel_oil', 'scope_1', Decimal('2.680000'), 'l', 'Fuel Oil (kgCO2e/L)'),
    ('employee_commute', 'scope_3', Decimal('0.170000'), 'km', 'Employee Commute (kgCO2e/km)'),
]


class Command(BaseCommand):
    help = 'Idempotent demo data for Module 14 - Energy & Utility Management.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true')
        parser.add_argument('--tenant', type=str, default=None,
                            help='Slug to limit seeding to a single tenant.')

    def handle(self, *args, **options):
        flush = options.get('flush', False)
        slug = options.get('tenant')
        tenants = Tenant.objects.filter(is_active=True)
        if slug:
            tenants = tenants.filter(slug=slug)

        for tenant in tenants:
            self._seed_one(tenant, flush=flush)

        self.stdout.write('seed_utility done.')
        self.stdout.write(
            'Login as a tenant admin (e.g. admin_acme / Welcome@123) to view seeded utility data.'
        )
        self.stdout.write(
            "Superuser 'admin' has no tenant - data wont appear when logged in as admin."
        )

    # ------------------------------------------------------------------
    # Per-tenant orchestration
    # ------------------------------------------------------------------

    def _seed_one(self, tenant: Tenant, *, flush: bool):
        random.seed(hash(tenant.slug) & 0xFFFFFFFF)
        if flush:
            self._flush_tenant(tenant)

        if U.UtilityType.all_objects.filter(tenant=tenant).exists():
            self.stdout.write(
                f'[{tenant.slug}] utility data already exists. Use --flush to re-seed.'
            )
            return

        # Confirm the upstream cost periods exist (L-08 horizon alignment).
        from apps.cost.models import AccountingPeriod
        prior_period = (
            AccountingPeriod.all_objects
            .filter(tenant=tenant).order_by('start_date').first()
        )
        current_period = (
            AccountingPeriod.all_objects
            .filter(tenant=tenant).order_by('-start_date').first()
        )
        if prior_period is None or current_period is None or prior_period.pk == current_period.pk:
            # Try to identify the canonical prior + current pair by status.
            periods = list(
                AccountingPeriod.all_objects
                .filter(tenant=tenant).order_by('start_date')
            )
            if len(periods) < 2:
                self.stdout.write(
                    f'[{tenant.slug}] skipped - need at least 2 cost.AccountingPeriod rows. '
                    f'Run seed_cost first.'
                )
                return
            prior_period, current_period = periods[0], periods[1]

        with transaction.atomic():
            types = self._seed_types(tenant)
            tariffs = self._seed_tariffs(tenant, types, current_period)
            tou_count = self._seed_tou_bands(tenant, tariffs)
            dre_count = self._seed_demand_response(tenant, types)
            meters = self._seed_meters(tenant, types)
            factor_count = self._seed_emission_factors(tenant, prior_period)
            cons_count = self._seed_consumptions(
                tenant, meters, prior_period, current_period,
            )
            alloc_count = self._seed_allocations(
                tenant, meters, current_period,
            )
            kpi_count = self._seed_sustainability_kpis(
                tenant, prior_period, current_period,
            )
            bench_count, comp_count = self._seed_benchmarks(
                tenant, prior_period, current_period,
            )

        emissions_total = U.CarbonEmission.all_objects.filter(
            tenant=tenant, is_reversal=False,
        ).count()
        self.stdout.write(
            f'[seed_utility] tenant={tenant.slug} '
            f'types={len(types)} meters={len(meters)} tariffs={len(tariffs)} '
            f'tou_bands={tou_count} dre_events={dre_count} '
            f'consumptions={cons_count} factors={factor_count} '
            f'allocations={alloc_count} emissions={emissions_total} '
            f'sustainability={kpi_count} benchmarks={bench_count} '
            f'comparisons={comp_count}'
        )
        self.stdout.write(
            f'[seed_utility] LOGIN as admin_{tenant.slug} / Welcome@123'
        )

    # ------------------------------------------------------------------
    # Flush
    # ------------------------------------------------------------------

    def _flush_tenant(self, tenant: Tenant):
        # Order matters - children before parents to dodge PROTECT FKs.
        for cls in (
            U.PeakShavingSuggestion,
            U.BenchmarkComparison, U.BenchmarkSnapshot,
            U.SustainabilityKPI, U.CarbonEmission, U.EmissionFactor,
            U.UtilityAllocation, U.DemandResponseEvent, U.TOURateBand,
            U.UtilityTariff, U.UtilityConsumption, U.UtilityMeter,
            U.UtilityType,
        ):
            cls.all_objects.filter(tenant=tenant).delete()
        # Tear down the cost.DriverActuals rows the allocation service wrote
        # so a re-seed doesn't accumulate utility-tagged actuals across runs.
        try:
            from apps.cost.models import DriverActuals
            DriverActuals.all_objects.filter(
                tenant=tenant, notes__startswith='utility:',
            ).delete()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Section helpers
    # ------------------------------------------------------------------

    def _seed_types(self, tenant: Tenant) -> dict:
        from apps.cost.models import CostDriver
        out = {}
        for code, name, uom, driver_code in UTILITY_TYPES:
            driver = None
            if driver_code:
                driver = CostDriver.all_objects.filter(
                    tenant=tenant, code=driver_code,
                ).first()
                if driver is None:
                    self.stdout.write(
                        f'[seed_utility] [{tenant.slug}] WARN: cost.CostDriver '
                        f'code={driver_code} not found - {code} will not '
                        f'auto-bridge into the cost overhead pipeline.'
                    )
            out[code] = U.UtilityType.all_objects.create(
                tenant=tenant, code=code, name=name,
                unit_of_measure=uom, cost_driver=driver,
                description=f'{name} utility type.',
                is_active=True,
            )
        return out

    def _seed_tariffs(self, tenant: Tenant, types: dict, current_period) -> dict:
        out = {}
        eff_from = current_period.start_date
        for code, flat_rate, currency in TARIFFS:
            tariff = U.UtilityTariff.all_objects.create(
                tenant=tenant,
                utility_type=types[code],
                name=f'{types[code].name} Standard Tariff',
                effective_from=eff_from,
                flat_rate=flat_rate,
                currency=currency,
                is_active=True,
                notes='Seeded standard tariff.',
            )
            out[code] = tariff
        return out

    def _seed_tou_bands(self, tenant: Tenant, tariffs: dict) -> int:
        elec = tariffs.get('electricity')
        if elec is None:
            return 0
        count = 0
        for band_type, dow, start, end, rate in TOU_BANDS:
            U.TOURateBand.all_objects.create(
                tenant=tenant,
                tariff=elec,
                band_type=band_type,
                day_of_week=dow,
                start_time=start,
                end_time=end,
                rate=rate,
                notes=f'{band_type} band for {dow}.',
            )
            count += 1
        return count

    def _seed_demand_response(self, tenant: Tenant, types: dict) -> int:
        elec = types.get('electricity')
        if elec is None:
            return 0
        # Tomorrow 14:00-17:00 local.
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        start = timezone.make_aware(datetime.combine(tomorrow, dtime(14, 0)))
        end = timezone.make_aware(datetime.combine(tomorrow, dtime(17, 0)))
        U.DemandResponseEvent.all_objects.create(
            tenant=tenant,
            utility_type=elec,
            event_type='voluntary',
            start_at=start, end_at=end,
            target_reduction_pct=Decimal('15.00'),
            incentive_amount=Decimal('500.00'),
            status='scheduled',
            source='utility_provider',
            notes='Seeded voluntary curtailment window.',
        )
        return 1

    def _seed_meters(self, tenant: Tenant, types: dict) -> dict:
        from apps.eam.models import Asset
        from apps.inventory.models import Warehouse
        from apps.labor.models import CostCenter

        first_asset = Asset.all_objects.filter(tenant=tenant).first()
        first_wh = Warehouse.all_objects.filter(tenant=tenant).first()
        first_cc = CostCenter.all_objects.filter(tenant=tenant).first()

        out = {}
        # Pass 1: parents.
        for meter_number, utility_code, name, source, parent_number in METERS:
            if parent_number is not None:
                continue
            asset = first_asset if utility_code == 'electricity' else None
            cc = first_cc if utility_code == 'electricity' else None
            out[meter_number] = U.UtilityMeter.all_objects.create(
                tenant=tenant,
                meter_number=meter_number,
                utility_type=types[utility_code],
                name=name,
                location=first_wh,
                asset=asset,
                cost_center=cc,
                installed_at=timezone.now().date() - timedelta(days=180),
                last_calibrated_at=timezone.now().date() - timedelta(days=30),
                multiplier=Decimal('1.0000'),
                is_active=True,
                notes='Seeded main meter.',
            )
        # Pass 2: sub-meters.  Sub-meters explicitly do NOT carry the parent's
        # asset FK - the EAM auto-feed signal resolves the meter by asset, and
        # two electricity meters sharing one asset would let only the first
        # match consume readings.  Only the parent (MAIN-ELEC-01) carries the
        # asset link; LINE-2-ELEC-01 uses direct post_consumption.
        for meter_number, utility_code, name, source, parent_number in METERS:
            if parent_number is None:
                continue
            out[meter_number] = U.UtilityMeter.all_objects.create(
                tenant=tenant,
                meter_number=meter_number,
                utility_type=types[utility_code],
                name=name,
                location=first_wh,
                parent_meter=out[parent_number],
                asset=None,
                cost_center=first_cc,
                installed_at=timezone.now().date() - timedelta(days=120),
                last_calibrated_at=timezone.now().date() - timedelta(days=20),
                multiplier=Decimal('1.0000'),
                is_active=True,
                notes='Seeded sub-meter.',
            )
        return out

    def _seed_emission_factors(self, tenant: Tenant, anchor_period) -> int:
        from_date = anchor_period.start_date
        count = 0
        for source_type, scope, factor, uom, label in EMISSION_FACTORS:
            U.EmissionFactor.all_objects.create(
                tenant=tenant,
                source_type=source_type,
                scope=scope,
                region='',
                factor=factor,
                unit_of_measure=uom,
                effective_from=from_date,
                source_reference='Seeded - GHG Protocol / DEFRA reference factor.',
                is_active=True,
                notes=label,
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Consumption
    # ------------------------------------------------------------------

    def _seed_consumptions(self, tenant, meters, prior_period, current_period):
        """Generate ~30 daily rows per meter inside the prior + current periods.

        For electricity meters, write apps.eam.AssetMeterReading rows so the
        cross-module post_save signal auto-creates UtilityConsumption rows
        (proves the cascade). For other meters, call meters.post_consumption
        directly. Either way, UtilityConsumption.post_save will cascade
        CarbonEmission auto-emission.
        """
        from apps.eam.models import AssetMeterReading

        rng = random.Random(hash(tenant.slug) & 0xFFFFFFFF)
        cons_count = 0

        # Build a flat list of (date, period) tuples, ~30 days total spread
        # across both periods.  Prior period gets ~15 days near the END,
        # current period gets ~15 days near the START.
        prior_days = self._even_dates(
            prior_period.start_date, prior_period.end_date, 15,
        )
        current_today = min(timezone.now().date(), current_period.end_date)
        current_days = self._even_dates(
            current_period.start_date, current_today, 15,
        )
        all_days = [(d, prior_period) for d in prior_days] + \
                   [(d, current_period) for d in current_days]

        for meter_number, meter in meters.items():
            utility_code = meter.utility_type.code
            # Per-meter starting reading + per-day delta target.
            cumulative_reading = Decimal(rng.randint(10000, 50000))
            for d, period in all_days:
                # Daily delta - random walk anchored to a deterministic seed.
                if utility_code == 'electricity':
                    delta = Decimal(rng.randint(180, 320))  # kWh / day
                elif utility_code == 'water':
                    delta = Decimal(rng.randint(8, 22))  # m3 / day
                elif utility_code == 'natural_gas':
                    delta = Decimal(rng.randint(40, 90))  # m3 / day
                else:
                    delta = Decimal(rng.randint(10, 30))
                start_reading = cumulative_reading
                end_reading = cumulative_reading + delta
                cumulative_reading = end_reading

                # Period window: 1-day window.
                period_start = timezone.make_aware(
                    datetime.combine(d, dtime(0, 0))
                )
                period_end = timezone.make_aware(
                    datetime.combine(d, dtime(23, 59))
                )

                if utility_code == 'electricity':
                    # Write an AssetMeterReading so the EAM auto-feed signal
                    # cascades a UtilityConsumption automatically.  Skip if
                    # the meter has no asset link (signal would no-op anyway).
                    if meter.asset_id is None:
                        # No asset means no signal cascade - fall back to
                        # direct post_consumption to keep counts on target.
                        meter_svc.post_consumption(
                            meter,
                            period_start=period_start,
                            period_end=period_end,
                            start_reading=start_reading,
                            end_reading=end_reading,
                            source='manual',
                        )
                        cons_count += 1
                        continue
                    AssetMeterReading.all_objects.create(
                        tenant=tenant,
                        asset=meter.asset,
                        meter_type='kwh',
                        reading_value=end_reading,
                        recorded_at=period_end,
                        notes=(
                            f'Seeded for {meter.meter_number} on {d.isoformat()}'
                        ),
                    )
                    # The post_save signal will spawn the UtilityConsumption
                    # row (idempotent on source_meter_reading).
                    cons_count += 1
                else:
                    meter_svc.post_consumption(
                        meter,
                        period_start=period_start,
                        period_end=period_end,
                        start_reading=start_reading,
                        end_reading=end_reading,
                        source='manual',
                    )
                    cons_count += 1
        return cons_count

    @staticmethod
    def _even_dates(start_date, end_date, count: int) -> list:
        """Return ``count`` evenly-spaced dates inside [start, end]."""
        if end_date < start_date:
            return []
        span = (end_date - start_date).days
        if span <= 0 or count <= 1:
            return [start_date]
        if count > span + 1:
            count = span + 1
        step = span / (count - 1)
        return [
            start_date + timedelta(days=int(round(step * i)))
            for i in range(count)
        ]

    # ------------------------------------------------------------------
    # Allocation
    # ------------------------------------------------------------------

    def _seed_allocations(self, tenant, meters, current_period) -> int:
        """For each metered cost-center, post a 100% allocation in the current
        period via services.allocation.post_allocation (which writes
        cost.DriverActuals downstream).
        """
        count = 0
        for meter_number, meter in meters.items():
            if meter.cost_center_id is None:
                continue
            try:
                result = alloc_svc.post_allocation(
                    period=current_period,
                    meter=meter,
                    targets=[{
                        'cost_center': meter.cost_center,
                        'product': None,
                        'production_order': None,
                        'share_pct': Decimal('100'),
                    }],
                )
                count += result.get('created', 0)
            except Exception as exc:
                self.stdout.write(
                    f'[seed_utility] [{tenant.slug}] WARN: allocation for '
                    f'{meter.meter_number} skipped - {exc}'
                )
        return count

    # ------------------------------------------------------------------
    # Sustainability KPI + Benchmarks
    # ------------------------------------------------------------------

    def _seed_sustainability_kpis(self, tenant, prior_period, current_period) -> int:
        count = 0
        for period in (prior_period, current_period):
            try:
                carbon_svc.generate_sustainability_kpi(period)
                count += 1
            except Exception as exc:
                self.stdout.write(
                    f'[seed_utility] [{tenant.slug}] WARN: KPI for '
                    f'{period.name} skipped - {exc}'
                )
        return count

    def _seed_benchmarks(self, tenant, prior_period, current_period):
        bench_count = 0
        comp_count = 0
        try:
            prior_snap = bench_svc.generate_snapshot(prior_period)
            bench_count += 1
            current_snap = bench_svc.generate_snapshot(current_period)
            bench_count += 1
        except Exception as exc:
            self.stdout.write(
                f'[seed_utility] [{tenant.slug}] WARN: benchmark snapshot '
                f'skipped - {exc}'
            )
            return bench_count, comp_count
        try:
            bench_svc.create_comparison(
                comparison_type='period_over_period',
                from_snapshot=prior_snap,
                to_snapshot=current_snap,
                tenant=tenant,
                notes='Seeded period-over-period comparison.',
            )
            comp_count += 1
        except Exception as exc:
            self.stdout.write(
                f'[seed_utility] [{tenant.slug}] WARN: benchmark comparison '
                f'skipped - {exc}'
            )
        return bench_count, comp_count
