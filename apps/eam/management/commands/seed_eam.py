"""Idempotent seeder for Module 10 - Equipment & Asset Management.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush.
  - Skips per-tenant if data already exists.
  - Auto-numbered records (ASSET-, TOOL-, MWO-, PMS-) check existence
    before creating.

Per Lesson L-09, all stdout text is plain ASCII - no Unicode arrows / dots /
emoji. The Windows cp1252 console crashes on them.

Per tenant produces:
    - 6 Asset Categories (Pumps, Motors, CNC, Conveyor, HVAC, Tooling)
      with parent-child links.
    - ~10 Assets across 3 categories with mixed criticality and 1 parent-child
      pair (CNC-LATHE-01 with sub-asset SPINDLE-01).
    - 1-3 Spare parts per critical asset linked to existing plm.Product rows.
    - 30 days of synthetic meter readings per metered asset.
    - 4 PM plans (calendar + meter mix), each with 3-4 tasks, with the next 3
      schedules per plan generated.
    - 2 Condition monitoring points per critical asset, 25 readings each (1
      deliberately critical to trigger a FailurePrediction via signal).
    - 3 MWOs (1 breakdown completed, 1 scheduled, 1 in-progress) with labor +
      material logs and a downtime event for the breakdown one.
    - 2 Tools incl. 1 mold with 4 cavities + maintenance records + usage logs.
"""
from datetime import date, timedelta
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.plm.models import Product
from apps.eam.models import (
    Asset, AssetCategory, AssetMeterReading, AssetSparePart,
    ConditionMonitoringPoint, ConditionReading,
    DowntimeEvent, FailurePrediction,
    MaintenancePlan, MaintenanceTask, MaintenanceWorkOrder,
    MoldCavityHistory, MWOLaborLog, MWOMaterialLog,
    PMSchedule, PMTaskCompletion,
    Tool, ToolMaintenanceRecord, ToolUsageLog,
)
from apps.eam.services.pm_scheduler import generate_upcoming_pm

CATEGORY_SEED = [
    ('Pumps', None),
    ('Motors', None),
    ('CNC Machines', None),
    ('Conveyor Systems', None),
    ('HVAC Equipment', None),
    ('Tooling', None),
]

ASSET_SEED = [
    # (tag-suffix, name, category, criticality, parent-suffix, mfg, model)
    ('PUMP-01', 'Process Pump 1', 'Pumps', 'high', None, 'Grundfos', 'CR45-2'),
    ('PUMP-02', 'Process Pump 2', 'Pumps', 'medium', None, 'Grundfos', 'CR45-2'),
    ('MOTOR-01', 'Conveyor Drive Motor 1', 'Motors', 'medium', None, 'Siemens', '1LE1'),
    ('MOTOR-02', 'Conveyor Drive Motor 2', 'Motors', 'medium', None, 'Siemens', '1LE1'),
    ('CNC-LATHE-01', 'CNC Lathe Bay 1', 'CNC Machines', 'critical', None, 'Mazak', 'QT-200'),
    ('SPINDLE-01', 'Lathe Spindle Assembly', 'CNC Machines', 'high', 'CNC-LATHE-01', 'Mazak', 'SP-200'),
    ('CNC-MILL-01', 'CNC Mill Bay 2', 'CNC Machines', 'critical', None, 'Haas', 'VF-2'),
    ('CONV-01', 'Main Line Conveyor', 'Conveyor Systems', 'high', None, 'Hytrol', 'TA-2'),
    ('HVAC-01', 'Production HVAC Unit', 'HVAC Equipment', 'medium', None, 'Carrier', '50TC'),
    ('COMP-01', 'Air Compressor 1', 'HVAC Equipment', 'high', None, 'Atlas Copco', 'GA22'),
]

PM_PLAN_SEED = [
    # (asset-suffix, name, trigger, freq_days, freq_meter, meter_type)
    ('CNC-LATHE-01', 'Quarterly Lubrication', 'calendar', 90, None, ''),
    ('CNC-MILL-01', 'Spindle Inspection', 'both', 60, Decimal('500'), 'hours'),
    ('PUMP-01', 'Monthly Vibration Check', 'calendar', 30, None, ''),
    ('CONV-01', 'Belt Tensioning', 'meter', None, Decimal('10000'), 'cycles'),
]

PM_TASK_TEMPLATES = {
    'Quarterly Lubrication': [
        ('Inspect oil level', False, 5),
        ('Top up lubricant', False, 10),
        ('Inspect grease points', True, 15),
        ('Verify oil pressure', True, 5),
    ],
    'Spindle Inspection': [
        ('Check spindle runout', True, 30),
        ('Inspect drawbar tension', True, 20),
        ('Verify coolant flow', False, 10),
    ],
    'Monthly Vibration Check': [
        ('Take vibration baseline', True, 10),
        ('Inspect bearings', True, 15),
        ('Document readings', False, 5),
    ],
    'Belt Tensioning': [
        ('Inspect belt wear', True, 10),
        ('Adjust tension', True, 20),
        ('Verify alignment', False, 15),
    ],
}

MONITORING_POINT_SEED = [
    # (asset-suffix, name, parameter, unit, low_alarm, high_alarm)
    ('CNC-LATHE-01', 'Spindle Bearing X', 'vibration', 'mm/s', None, Decimal('4.5')),
    ('CNC-LATHE-01', 'Spindle Bearing Y', 'vibration', 'mm/s', None, Decimal('4.5')),
    ('CNC-MILL-01', 'Spindle Temp', 'temperature', 'C', None, Decimal('70')),
    ('CNC-MILL-01', 'Coolant Pressure', 'pressure', 'bar', Decimal('2.5'), Decimal('5.0')),
    ('PUMP-01', 'Pump Bearing', 'vibration', 'mm/s', None, Decimal('5.0')),
    ('COMP-01', 'Output Pressure', 'pressure', 'bar', Decimal('6'), Decimal('9')),
]


def _get_admin(tenant):
    """Find a tenant admin user; fall back to any tenant user."""
    return (
        User.objects.filter(tenant=tenant, role='tenant_admin').first()
        or User.objects.filter(tenant=tenant).first()
    )


def _seed_categories(tenant, stdout):
    if AssetCategory.all_objects.filter(tenant=tenant).exists():
        stdout.write('  categories: skipped (already seeded)')
        return {c.name: c for c in AssetCategory.all_objects.filter(tenant=tenant)}
    cats = {}
    for name, parent_name in CATEGORY_SEED:
        parent = cats.get(parent_name) if parent_name else None
        c = AssetCategory.all_objects.create(
            tenant=tenant, name=name, parent=parent,
            description=f'{name} category.', is_active=True,
        )
        cats[name] = c
    stdout.write(f'  categories: created {len(cats)}')
    return cats


def _seed_assets(tenant, categories, stdout):
    if Asset.all_objects.filter(tenant=tenant).exists():
        stdout.write('  assets: skipped (already seeded)')
        return list(Asset.all_objects.filter(tenant=tenant).order_by('id'))

    assets_by_suffix = {}
    today = date.today()
    for suffix, name, cat_name, crit, parent_suffix, mfg, model in ASSET_SEED:
        parent = assets_by_suffix.get(parent_suffix) if parent_suffix else None
        asset = Asset.all_objects.create(
            tenant=tenant,
            name=name,
            category=categories.get(cat_name),
            parent=parent,
            manufacturer=mfg,
            model_number=model,
            serial_number=f'SN-{suffix}',
            installation_date=today - timedelta(days=365 * 3),
            commissioning_date=today - timedelta(days=365 * 3 - 30),
            criticality=crit,
            status='operational',
            purchase_cost=Decimal('25000.00'),
            current_value=Decimal('15000.00'),
            warranty_expiry=today + timedelta(days=180),
            is_active=True,
            notes='Seed asset.',
        )
        assets_by_suffix[suffix] = asset
    assets = list(assets_by_suffix.values())
    stdout.write(f'  assets: created {len(assets)}')
    return assets


def _seed_spare_parts(tenant, assets, stdout):
    if AssetSparePart.all_objects.filter(tenant=tenant).exists():
        stdout.write('  spare parts: skipped (already seeded)')
        return
    products = list(Product.all_objects.filter(tenant=tenant)[:6])
    if not products:
        stdout.write('  spare parts: skipped (no plm.Product records to link)')
        return
    rng = random.Random(42)
    count = 0
    for asset in assets:
        if asset.criticality not in ('high', 'critical'):
            continue
        chosen = rng.sample(products, min(2, len(products)))
        for p in chosen:
            try:
                AssetSparePart.all_objects.create(
                    tenant=tenant, asset=asset, product=p,
                    recommended_min_qty=Decimal('5'),
                    quantity_on_hand=Decimal('3'),
                    notes='Seed spare link.',
                )
                count += 1
            except Exception:
                continue
    stdout.write(f'  spare parts: created {count}')


def _seed_meter_readings(tenant, assets, stdout):
    if AssetMeterReading.all_objects.filter(tenant=tenant).exists():
        stdout.write('  meter readings: skipped (already seeded)')
        return
    rng = random.Random(7)
    count = 0
    metered = [a for a in assets if a.tag.startswith('ASSET-') and a.criticality in ('high', 'critical')]
    now = timezone.now()
    for asset in metered:
        running_hours = Decimal('1000')
        for d in range(30, 0, -1):
            running_hours += Decimal(rng.randint(8, 16))
            AssetMeterReading.all_objects.create(
                tenant=tenant,
                asset=asset,
                meter_type='hours',
                reading_value=running_hours,
                recorded_at=now - timedelta(days=d),
                notes='Seed daily reading.',
            )
            count += 1
    stdout.write(f'  meter readings: created {count}')


def _seed_pm_plans(tenant, assets, admin, stdout):
    if MaintenancePlan.all_objects.filter(tenant=tenant).exists():
        stdout.write('  PM plans: skipped (already seeded)')
        return
    by_suffix = {a.tag: a for a in assets}
    # Build a more useful suffix lookup since tags are auto-generated;
    # fall back to mapping via name match.
    name_to_asset = {a.name: a for a in assets}
    suffix_to_asset = {}
    for orig_suffix, name, *_ in ASSET_SEED:
        if name in name_to_asset:
            suffix_to_asset[orig_suffix] = name_to_asset[name]

    plan_count = 0
    task_count = 0
    today = date.today()
    for suffix, plan_name, trigger, freq_days, freq_meter, meter_type in PM_PLAN_SEED:
        asset = suffix_to_asset.get(suffix)
        if asset is None:
            continue
        plan = MaintenancePlan.all_objects.create(
            tenant=tenant, asset=asset, name=plan_name,
            description=f'{plan_name} for {asset.name}.',
            trigger_type=trigger,
            frequency_days=freq_days,
            frequency_meter=freq_meter,
            meter_type=meter_type,
            last_done_at=today - timedelta(days=freq_days or 30),
            next_due_at=today + timedelta(days=freq_days or 7),
            is_active=True,
            created_by=admin,
        )
        plan_count += 1
        for seq, (desc, critical, mins) in enumerate(PM_TASK_TEMPLATES.get(plan_name, []), start=1):
            MaintenanceTask.all_objects.create(
                tenant=tenant, plan=plan, sequence=seq * 10,
                description=desc, expected_minutes=Decimal(mins),
                is_critical=critical,
            )
            task_count += 1

        # Generate next 3 schedules.
        upcoming = generate_upcoming_pm(plan, horizon_days=120, max_count=3)
        for sched_date, sched_meter in upcoming:
            if sched_date is None:
                continue
            existing = PMSchedule.all_objects.filter(
                tenant=tenant, plan=plan, scheduled_date=sched_date,
            ).exists()
            if existing:
                continue
            PMSchedule.all_objects.create(
                tenant=tenant, plan=plan,
                scheduled_date=sched_date, scheduled_meter=sched_meter,
            )

    stdout.write(f'  PM plans: created {plan_count} (with {task_count} tasks)')


def _seed_condition_points_and_readings(tenant, assets, admin, stdout):
    if ConditionMonitoringPoint.all_objects.filter(tenant=tenant).exists():
        stdout.write('  condition points: skipped (already seeded)')
        return
    name_to_asset = {a.name: a for a in assets}
    suffix_to_asset = {}
    for orig_suffix, name, *_ in ASSET_SEED:
        if name in name_to_asset:
            suffix_to_asset[orig_suffix] = name_to_asset[name]

    point_count = 0
    reading_count = 0
    rng = random.Random(13)
    now = timezone.now()
    points_for_critical = []
    for suffix, name, parameter, unit, low, high in MONITORING_POINT_SEED:
        asset = suffix_to_asset.get(suffix)
        if asset is None:
            continue
        point = ConditionMonitoringPoint.all_objects.create(
            tenant=tenant, asset=asset, name=name,
            parameter=parameter, unit=unit,
            low_alarm=low, high_alarm=high,
            is_active=True,
        )
        point_count += 1
        # 25 normal readings + 1 deliberately critical on the first point.
        if not points_for_critical:
            points_for_critical.append(point)
        center = ((high or Decimal('0')) + (low or Decimal('0'))) / Decimal('2')
        if center == Decimal('0'):
            center = (high or Decimal('1')) / Decimal('2')
        for d in range(25, 0, -1):
            jitter = Decimal(rng.uniform(-0.4, 0.4)).quantize(Decimal('0.01'))
            value = (center + jitter)
            ConditionReading.all_objects.create(
                tenant=tenant, point=point, reading_value=value,
                recorded_at=now - timedelta(hours=d * 3),
                recorded_by=admin,
                status='normal',
            )
            reading_count += 1

    # Deliberately critical reading on the first point so the post-save
    # signal spawns a FailurePrediction. Skip if the point's high_alarm is
    # not set.
    for p in points_for_critical:
        if p.high_alarm is None:
            continue
        ConditionReading.all_objects.create(
            tenant=tenant, point=p,
            reading_value=p.high_alarm * Decimal('1.5'),
            recorded_at=now,
            recorded_by=admin,
            notes='Seed critical reading - triggers FailurePrediction.',
        )
        reading_count += 1
    stdout.write(f'  condition points: created {point_count} (with {reading_count} readings)')


def _seed_work_orders(tenant, assets, admin, stdout):
    if MaintenanceWorkOrder.all_objects.filter(tenant=tenant).exists():
        stdout.write('  work orders: skipped (already seeded)')
        return
    if not assets:
        return
    products = list(Product.all_objects.filter(tenant=tenant)[:3])
    now = timezone.now()
    pump = next((a for a in assets if 'Pump' in a.name), assets[0])
    cnc = next((a for a in assets if 'CNC' in a.name), assets[0])
    motor = next((a for a in assets if 'Motor' in a.name), assets[0])

    # 1) Completed breakdown WO
    mwo1 = MaintenanceWorkOrder.all_objects.create(
        tenant=tenant, asset=pump,
        wo_type='breakdown', priority='high',
        title=f'{pump.name} - bearing failure',
        problem_description='Unusual noise and vibration; pump output dropped.',
        status='completed',
        reported_by=admin, reported_at=now - timedelta(days=4),
        assigned_to=admin,
        started_at=now - timedelta(days=4, hours=-1),
        completed_at=now - timedelta(days=4, hours=-5),
        completed_by=admin,
        downtime_minutes=Decimal('240'),
        failure_code='BRG-01',
        root_cause='Bearing wear past life limit',
        resolution_notes='Replaced bearing assembly; tested under load; cleared to run.',
    )
    MWOLaborLog.all_objects.create(
        tenant=tenant, mwo=mwo1, technician=admin,
        started_at=now - timedelta(days=4, hours=-1),
        ended_at=now - timedelta(days=4, hours=-5),
        hourly_rate=Decimal('45.00'),
    )
    if products:
        MWOMaterialLog.all_objects.create(
            tenant=tenant, mwo=mwo1, product=products[0],
            quantity=Decimal('1'), unit_of_measure='EA',
            unit_cost=Decimal('120.00'),
            used_at=now - timedelta(days=4, hours=-2),
        )
    DowntimeEvent.all_objects.create(
        tenant=tenant, asset=pump, mwo=mwo1,
        started_at=now - timedelta(days=4, hours=2),
        ended_at=now - timedelta(days=4, hours=-2),
        downtime_type='unplanned',
        reason='Pump bearing failure',
    )

    # 2) Scheduled corrective WO
    MaintenanceWorkOrder.all_objects.create(
        tenant=tenant, asset=motor,
        wo_type='corrective', priority='medium',
        title=f'{motor.name} - replace seal',
        problem_description='Minor coolant leak observed at shaft seal.',
        status='scheduled',
        reported_by=admin, reported_at=now - timedelta(days=1),
        scheduled_start=now + timedelta(days=2),
        assigned_to=admin,
    )

    # 3) In-progress preventive WO
    MaintenanceWorkOrder.all_objects.create(
        tenant=tenant, asset=cnc,
        wo_type='preventive', priority='medium',
        title=f'{cnc.name} - quarterly lubrication',
        status='in_progress',
        reported_by=admin, reported_at=now - timedelta(hours=4),
        started_at=now - timedelta(hours=2),
        assigned_to=admin,
    )

    stdout.write('  work orders: created 3')


def _seed_tools(tenant, admin, stdout):
    if Tool.all_objects.filter(tenant=tenant).exists():
        stdout.write('  tools: skipped (already seeded)')
        return

    today = date.today()
    cutting = Tool.all_objects.create(
        tenant=tenant,
        name='Carbide End Mill 12mm',
        description='Solid carbide 4-flute, AlTiN coated.',
        tool_type='cutting_tool',
        category='Mill',
        location='Tool Crib A',
        status='available',
        purchase_date=today - timedelta(days=120),
        purchase_cost=Decimal('250.00'),
        expected_life_cycles=10000,
        current_cycles=2400,
        expected_life_hours=Decimal('600'),
        current_hours=Decimal('150.50'),
        last_sharpened_at=today - timedelta(days=20),
        next_sharpen_due=today + timedelta(days=10),
        is_active=True,
    )
    ToolMaintenanceRecord.all_objects.create(
        tenant=tenant, tool=cutting,
        record_type='sharpening',
        performed_at=today - timedelta(days=20),
        performed_by=admin,
        cost=Decimal('40.00'),
        notes='Standard regrind, edge restored.',
    )
    ToolUsageLog.all_objects.create(
        tenant=tenant, tool=cutting,
        used_at=timezone.now() - timedelta(days=2),
        cycles_added=200,
        hours_added=Decimal('5.0'),
        operator=admin,
        notes='Production run TX-100.',
    )

    mold = Tool.all_objects.create(
        tenant=tenant,
        name='Cover Plate Mold (4-cavity)',
        description='Steel injection mold for ABS covers.',
        tool_type='mold',
        category='Injection Mold',
        location='Mold Storage 1',
        status='in_use',
        purchase_date=today - timedelta(days=400),
        purchase_cost=Decimal('45000.00'),
        expected_life_cycles=500000,
        current_cycles=120000,
        expected_life_hours=Decimal('0'),
        current_hours=Decimal('0'),
        cavity_count=4,
        is_active=True,
    )
    for n in range(1, 5):
        MoldCavityHistory.all_objects.create(
            tenant=tenant, tool=mold,
            cavity_number=n,
            cycles=30000,
            last_inspected_at=today - timedelta(days=15),
            defect_count=2 if n == 4 else 0,
            status='active' if n != 4 else 'repaired',
            notes='Cavity 4 had a flash issue corrected last service.' if n == 4 else '',
        )
    ToolMaintenanceRecord.all_objects.create(
        tenant=tenant, tool=mold,
        record_type='cleaning',
        performed_at=today - timedelta(days=30),
        performed_by=admin,
        cost=Decimal('120.00'),
        notes='Quarterly mold cleaning.',
    )

    stdout.write('  tools: created 2 (1 cutting tool + 1 mold with 4 cavities)')


class Command(BaseCommand):
    help = 'Seed Module 10 - Equipment & Asset Management demo data per tenant.'

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Wipe + re-seed.')

    def handle(self, *args, **options):
        flush = options.get('flush', False)
        tenants = list(Tenant.objects.filter(is_active=True))
        if not tenants:
            self.stdout.write(self.style.WARNING(
                'No active tenants. Run seed_tenants first.'
            ))
            return

        if flush:
            self.stdout.write(self.style.WARNING('--flush: wiping EAM data'))
            for model in (
                ToolUsageLog, ToolMaintenanceRecord, MoldCavityHistory, Tool,
                MWOMaterialLog, MWOLaborLog, DowntimeEvent,
                PMTaskCompletion, PMSchedule, MaintenanceTask, MaintenancePlan,
                ConditionReading, ConditionMonitoringPoint,
                FailurePrediction, MaintenanceWorkOrder,
                AssetMeterReading, AssetSparePart, Asset, AssetCategory,
            ):
                model.all_objects.all().delete()

        for tenant in tenants:
            self.stdout.write(self.style.HTTP_INFO(f'-> Tenant: {tenant.name}'))
            admin = _get_admin(tenant)
            if admin is None:
                self.stdout.write(self.style.WARNING(
                    f'  no users for tenant {tenant.slug}; skipping EAM seed'
                ))
                continue
            cats = _seed_categories(tenant, self.stdout)
            assets = _seed_assets(tenant, cats, self.stdout)
            _seed_spare_parts(tenant, assets, self.stdout)
            _seed_meter_readings(tenant, assets, self.stdout)
            _seed_pm_plans(tenant, assets, admin, self.stdout)
            _seed_condition_points_and_readings(tenant, assets, admin, self.stdout)
            _seed_work_orders(tenant, assets, admin, self.stdout)
            _seed_tools(tenant, admin, self.stdout)

        self.stdout.write(self.style.SUCCESS('EAM seed complete.'))
        self.stdout.write(
            'Log in as a tenant admin (e.g. admin_acme / Welcome@123) to see EAM data.'
        )
        self.stdout.write(
            'Note: superuser "admin" has tenant=None - EAM pages will be empty for it.'
        )
