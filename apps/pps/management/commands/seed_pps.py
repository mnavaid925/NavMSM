"""Idempotent seeder for Production Planning & Scheduling demo data.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush
  - Skips per-tenant if data already exists
  - Auto-numbered records (MPS-00001, ROUT-00001, PO-00001) check for the
    business-natural unique key (tenant + product + version, etc.) before
    creating, never by raw number

Per tenant produces:
    4 work centers (machine/labor/cell/assembly_line) + Mon-Fri 08:00-17:00
    1 routing per seeded finished_good with 3-5 operations
    8 demand forecasts spanning 4 weeks across 4 products
    1 MPS (released) covering 4 weeks with 8 lines
    6 production orders in mixed statuses; released ones get scheduled ops
    1 capacity load snapshot computed via services/scheduler.compute_load
    1 scenario with 2 changes + completed result
    1 default optimization objective + 1 completed run with result
"""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.bom.models import BillOfMaterials
from apps.core.models import Tenant, set_current_tenant
from apps.plm.models import Product
from apps.pps.models import (
    CapacityCalendar, CapacityLoad, DemandForecast, MasterProductionSchedule,
    MPSLine, OptimizationObjective, OptimizationResult, OptimizationRun,
    ProductionOrder, Routing, RoutingOperation, Scenario, ScenarioChange,
    ScenarioResult, ScheduledOperation, WorkCenter,
)
from apps.pps.services import optimizer as optimizer_service
from apps.pps.services import scheduler as scheduler_service


WORK_CENTERS = [
    ('CNC-01', 'CNC Machining Cell', 'machine', '4', '92', '85'),
    ('LBR-01', 'Assembly Labor Pool', 'labor', '6', '88', '40'),
    ('CELL-01', 'Electronics Cell', 'cell', '5', '90', '60'),
    ('LINE-01', 'Final Assembly Line', 'assembly_line', '3', '95', '95'),
]

# Routing fixtures keyed by SKU. Each entry is a list of:
# (sequence, op_name, wc_code, setup_min, run_per_unit, queue_min, move_min)
ROUTING_FIXTURES = {
    'SKU-4001': [
        (10, 'Mill housing', 'CNC-01', '15', '6.5', '5', '3'),
        (20, 'Assemble PCBs', 'CELL-01', '10', '4.0', '5', '3'),
        (30, 'Wire harness', 'LBR-01', '5', '8.0', '5', '3'),
        (40, 'Final assembly', 'LINE-01', '5', '12.0', '5', '3'),
    ],
    'SKU-4002': [
        (10, 'Cut frame', 'CNC-01', '20', '5.5', '5', '3'),
        (20, 'Assemble drive', 'LBR-01', '10', '10.0', '5', '3'),
        (30, 'QC + label', 'LINE-01', '5', '4.0', '5', '3'),
    ],
    'SKU-4003': [
        (10, 'Mill joint', 'CNC-01', '25', '8.0', '5', '3'),
        (20, 'Assemble servo', 'CELL-01', '15', '7.0', '5', '3'),
        (30, 'Calibrate', 'LBR-01', '10', '5.0', '5', '3'),
        (40, 'Pack', 'LINE-01', '5', '3.5', '5', '3'),
    ],
    'SKU-4004': [
        (10, 'Form chassis', 'CNC-01', '15', '6.0', '5', '3'),
        (20, 'Mount panel', 'LBR-01', '10', '6.0', '5', '3'),
        (30, 'Assemble', 'LINE-01', '5', '5.0', '5', '3'),
    ],
    'SKU-4005': [
        (10, 'Sub-assembly prep', 'LBR-01', '8', '4.5', '5', '3'),
        (20, 'Final assembly', 'LINE-01', '5', '6.0', '5', '3'),
    ],
}


def _next_number(model, tenant, field, prefix, width=5):
    last = model.objects.filter(tenant=tenant).aggregate(Max(field))[f'{field}__max']
    n = 1
    if last:
        import re
        m = re.match(rf'^{prefix}-(\d+)$', str(last))
        if m:
            n = int(m.group(1)) + 1
        else:
            n = model.objects.filter(tenant=tenant).count() + 1
    return f'{prefix}-{n:0{width}d}'


def _seed_work_centers(tenant, stdout):
    created = 0
    for code, name, wc_type, cap_h, eff, cost_h in WORK_CENTERS:
        wc, was = WorkCenter.objects.get_or_create(
            tenant=tenant, code=code,
            defaults={
                'name': name, 'work_center_type': wc_type,
                'capacity_per_hour': Decimal(cap_h),
                'efficiency_pct': Decimal(eff),
                'cost_per_hour': Decimal(cost_h),
                'description': f'Seeded {wc_type} for demo planning.',
                'is_active': True,
            },
        )
        if was:
            created += 1
            for dow in range(5):  # Mon-Fri
                CapacityCalendar.objects.get_or_create(
                    tenant=tenant, work_center=wc,
                    day_of_week=dow, shift_start=time(8, 0),
                    defaults={'shift_end': time(17, 0), 'is_working': True},
                )
    stdout.write(f'  work centers: {created} created')


def _seed_routings(tenant, products_by_sku, admin_user, work_centers_by_code, stdout):
    created = 0
    for sku, ops in ROUTING_FIXTURES.items():
        product = products_by_sku.get(sku)
        if product is None:
            continue
        existing = Routing.objects.filter(
            tenant=tenant, product=product, version='A',
        ).first()
        if existing is not None:
            continue
        routing = Routing(
            tenant=tenant, product=product, version='A',
            routing_number=_next_number(Routing, tenant, 'routing_number', 'ROUT'),
            name=f'{product.sku} primary routing',
            status='active', is_default=True,
            description=f'Seeded routing for {product.sku}.',
            created_by=admin_user,
        )
        routing.save()
        for seq, op_name, wc_code, setup, run_unit, queue_, move in ops:
            wc = work_centers_by_code.get(wc_code)
            if wc is None:
                continue
            RoutingOperation.objects.create(
                tenant=tenant, routing=routing,
                sequence=seq, operation_name=op_name,
                work_center=wc,
                setup_minutes=Decimal(setup),
                run_minutes_per_unit=Decimal(run_unit),
                queue_minutes=Decimal(queue_),
                move_minutes=Decimal(move),
                instructions=f'Seeded operation for {product.sku}.',
            )
        created += 1
    stdout.write(f'  routings: {created} created')


def _seed_forecasts(tenant, products_by_sku, stdout):
    targets = ['SKU-4001', 'SKU-4002', 'SKU-4003', 'SKU-4004']
    created = 0
    base = date.today().replace(day=1)
    for sku in targets:
        product = products_by_sku.get(sku)
        if product is None:
            continue
        for wk in range(2):
            ps = base + timedelta(weeks=wk)
            pe = ps + timedelta(days=6)
            _, was = DemandForecast.objects.get_or_create(
                tenant=tenant, product=product, period_start=ps,
                defaults={
                    'period_end': pe,
                    'forecast_qty': Decimal(str(50 + wk * 10 + random.randint(0, 20))),
                    'source': random.choice(['manual', 'historical', 'sales_order']),
                    'confidence_pct': Decimal(str(70 + random.randint(0, 25))),
                    'notes': f'Seeded forecast — week {wk + 1}.',
                },
            )
            if was:
                created += 1
    stdout.write(f'  forecasts: {created} created')


def _seed_mps(tenant, products_by_sku, admin_user, stdout):
    if MasterProductionSchedule.objects.filter(tenant=tenant).exists():
        return None
    horizon_start = date.today().replace(day=1)
    horizon_end = horizon_start + timedelta(days=27)
    mps = MasterProductionSchedule(
        tenant=tenant,
        mps_number=_next_number(MasterProductionSchedule, tenant, 'mps_number', 'MPS'),
        name=f'Q-MPS {horizon_start:%b %Y}',
        horizon_start=horizon_start, horizon_end=horizon_end,
        time_bucket='week', status='released',
        description='Seeded demo MPS covering a 4-week rolling horizon.',
        created_by=admin_user, approved_by=admin_user,
        approved_at=timezone.now(), released_at=timezone.now(),
    )
    mps.save()
    targets = ['SKU-4001', 'SKU-4002', 'SKU-4003', 'SKU-4004']
    line_count = 0
    for wk in range(2):
        ps = horizon_start + timedelta(weeks=wk)
        pe = ps + timedelta(days=6)
        for sku in targets:
            product = products_by_sku.get(sku)
            if product is None:
                continue
            forecast = Decimal(str(50 + wk * 10 + random.randint(0, 20)))
            firm = forecast - Decimal('5')
            scheduled = firm - Decimal('2')
            atp = scheduled - Decimal('1')
            MPSLine.objects.create(
                tenant=tenant, mps=mps, product=product,
                period_start=ps, period_end=pe,
                forecast_qty=forecast, firm_planned_qty=firm,
                scheduled_qty=scheduled, available_to_promise=atp,
            )
            line_count += 1
    stdout.write(f'  MPS lines: {line_count} created (mps {mps.mps_number})')
    return mps


def _calendars_dict(tenant):
    out = {}
    for cal in CapacityCalendar.objects.filter(tenant=tenant).select_related('work_center'):
        out.setdefault(cal.work_center_id, {}).setdefault(cal.day_of_week, []).append(
            (cal.shift_start, cal.shift_end, cal.is_working)
        )
    return out


def _seed_orders(tenant, products_by_sku, mps, admin_user, stdout):
    """6 production orders in mixed statuses. Released ones get scheduled ops."""
    fixtures = [
        # (sku, qty, status, priority, method, days_offset)
        ('SKU-4001', 25, 'released', 'high', 'forward', 1),
        ('SKU-4001', 10, 'in_progress', 'rush', 'forward', 0),
        ('SKU-4002', 30, 'released', 'normal', 'backward', 4),
        ('SKU-4003', 12, 'planned', 'normal', 'forward', 7),
        ('SKU-4004', 20, 'completed', 'normal', 'forward', -3),
        ('SKU-4005', 8, 'planned', 'low', 'infinite', 10),
    ]
    cals = _calendars_dict(tenant)
    routings_by_product = {
        r.product_id: r
        for r in Routing.objects.filter(tenant=tenant).prefetch_related('operations__work_center')
    }
    boms_by_product = {
        b.product_id: b
        for b in BillOfMaterials.objects.filter(tenant=tenant, is_default=True)
    }
    mps_lines_by_product = {
        l.product_id: l
        for l in (mps.lines.all() if mps else [])
    }
    created = 0
    today = timezone.now()
    for sku, qty, status, priority, method, day_off in fixtures:
        product = products_by_sku.get(sku)
        if product is None:
            continue
        existing = ProductionOrder.objects.filter(
            tenant=tenant, product=product, quantity=Decimal(str(qty)), status=status,
        ).first()
        if existing is not None:
            continue
        routing = routings_by_product.get(product.pk)
        bom = boms_by_product.get(product.pk)
        requested_start = today + timedelta(days=day_off)
        requested_end = requested_start + timedelta(days=2)
        order = ProductionOrder(
            tenant=tenant,
            order_number=_next_number(ProductionOrder, tenant, 'order_number', 'PO'),
            product=product, routing=routing, bom=bom,
            mps_line=mps_lines_by_product.get(product.pk),
            quantity=Decimal(str(qty)), status=status,
            priority=priority, scheduling_method=method,
            requested_start=requested_start, requested_end=requested_end,
            created_by=admin_user,
        )
        if status in ('released', 'in_progress', 'completed'):
            order.scheduled_start = requested_start
            order.scheduled_end = requested_end
        if status == 'in_progress':
            order.actual_start = today
        if status == 'completed':
            order.actual_start = today - timedelta(days=4)
            order.actual_end = today - timedelta(days=2)
        order.save()
        created += 1

        # For released / in_progress, lay scheduled operations onto the calendar.
        if status in ('released', 'in_progress') and routing is not None:
            ops = list(routing.operations.all().order_by('sequence'))
            requests_ = [
                scheduler_service.OperationRequest(
                    sequence=op.sequence, operation_name=op.operation_name,
                    work_center_id=op.work_center_id,
                    work_center_code=op.work_center.code,
                    setup_minutes=Decimal(str(op.setup_minutes)),
                    run_minutes_per_unit=Decimal(str(op.run_minutes_per_unit)),
                    queue_minutes=Decimal(str(op.queue_minutes)),
                    move_minutes=Decimal(str(op.move_minutes)),
                ) for op in ops
            ]
            slots = scheduler_service.schedule_forward(
                requests_, start=requested_start, quantity=Decimal(str(qty)),
                calendars=cals,
            )
            op_by_seq = {op.sequence: op for op in ops}
            for slot in slots:
                ScheduledOperation.objects.create(
                    tenant=tenant, production_order=order,
                    routing_operation=op_by_seq.get(slot.sequence),
                    work_center_id=slot.work_center_id,
                    sequence=slot.sequence,
                    operation_name=slot.operation_name,
                    planned_start=slot.planned_start,
                    planned_end=slot.planned_end,
                    planned_minutes=slot.planned_minutes,
                    status='in_progress' if status == 'in_progress' and slot.sequence == ops[0].sequence else 'pending',
                )
            if slots:
                ProductionOrder.objects.filter(pk=order.pk).update(
                    scheduled_start=slots[0].planned_start,
                    scheduled_end=slots[-1].planned_end,
                )
    stdout.write(f'  production orders: {created} created (with scheduled operations)')


def _seed_capacity_load(tenant, stdout):
    """Snapshot 14 days of load per active work center."""
    today = date.today()
    horizon = [today + timedelta(days=i) for i in range(14)]
    cals = _calendars_dict(tenant)
    sched_qs = ScheduledOperation.objects.filter(
        tenant=tenant,
        planned_start__date__gte=today,
        planned_start__date__lte=today + timedelta(days=13),
    )
    per_wc_per_date: dict = {}
    for s in sched_qs:
        d = s.planned_start.date()
        per_wc_per_date.setdefault(s.work_center_id, {}).setdefault(d, 0)
        per_wc_per_date[s.work_center_id][d] += s.planned_minutes
    snapshots = 0
    for wc in WorkCenter.objects.filter(tenant=tenant, is_active=True):
        available = {}
        for d in horizon:
            shifts = cals.get(wc.pk, {}).get(d.weekday(), [])
            mins = sum(
                int((datetime.combine(d, e) - datetime.combine(d, s)).total_seconds() // 60)
                for s, e, working in shifts if working
            )
            available[d] = mins
        scheduled = per_wc_per_date.get(wc.pk, {})
        summary = scheduler_service.compute_load(scheduled, available)
        for d, info in summary.items():
            CapacityLoad.objects.update_or_create(
                tenant=tenant, work_center=wc, period_date=d,
                defaults={
                    'planned_minutes': info['planned_minutes'],
                    'available_minutes': info['available_minutes'],
                    'utilization_pct': info['utilization_pct'],
                    'is_bottleneck': info['is_bottleneck'],
                    'computed_at': timezone.now(),
                },
            )
            snapshots += 1
    stdout.write(f'  capacity load: {snapshots} day snapshots')


def _seed_scenario(tenant, mps, admin_user, stdout):
    if mps is None or Scenario.objects.filter(tenant=tenant).exists():
        return
    scenario = Scenario(
        tenant=tenant, name='Rush order scenario — Q+10%',
        description='Adds two rush orders and bumps one MPS line +10% to test capacity headroom.',
        base_mps=mps, status='completed', ran_at=timezone.now(),
        created_by=admin_user,
    )
    scenario.save()
    first_line = mps.lines.first()
    target_ref = f'mps_line:{first_line.pk}' if first_line else 'mps_line:0'
    ScenarioChange.objects.create(
        tenant=tenant, scenario=scenario, sequence=10,
        change_type='change_qty', target_ref=target_ref,
        payload={'forecast_qty': str(int(first_line.forecast_qty) + 10) if first_line else '60'},
        notes='Bump first line forecast +10 units to model upside.',
    )
    ScenarioChange.objects.create(
        tenant=tenant, scenario=scenario, sequence=20,
        change_type='change_priority', target_ref=target_ref,
        payload={'priority': 'rush'},
        notes='Promote first line to rush.',
    )
    ScenarioResult.objects.create(
        tenant=tenant, scenario=scenario,
        on_time_pct=Decimal('92.50'),
        total_load_minutes=8400,
        total_idle_minutes=2200,
        bottleneck_count=1,
        summary_json={
            'lines_in': mps.lines.count(),
            'lines_after': mps.lines.count(),
            'rush_lines': 1,
            'changes_applied': 2,
        },
        computed_at=timezone.now(),
    )
    stdout.write('  scenario: 1 created (with 2 changes + result)')


def _seed_optimization(tenant, mps, admin_user, stdout):
    if mps is None:
        return
    if OptimizationObjective.objects.filter(tenant=tenant).exists():
        objective = OptimizationObjective.objects.filter(tenant=tenant, is_default=True).first() \
            or OptimizationObjective.objects.filter(tenant=tenant).first()
    else:
        objective = OptimizationObjective.objects.create(
            tenant=tenant, name='Balanced (default)',
            description='Default seeded objective: balanced weighting toward minimizing changeovers and lateness.',
            weight_changeovers=Decimal('1.5'),
            weight_idle=Decimal('1.0'),
            weight_lateness=Decimal('2.0'),
            weight_priority=Decimal('1.5'),
            is_default=True,
        )
        stdout.write('  objective: 1 created (default)')

    if OptimizationRun.objects.filter(tenant=tenant).exists():
        return
    run = OptimizationRun.objects.create(
        tenant=tenant, name=f'Initial run on {mps.mps_number}',
        mps=mps, objective=objective,
        status='running', started_at=timezone.now(), started_by=admin_user,
    )
    # Pull candidate orders and run the heuristic.
    orders = []
    for o in ProductionOrder.objects.filter(
        tenant=tenant, status__in=('planned', 'released'),
    ).select_related('product'):
        orders.append({
            'id': o.pk, 'product_id': o.product_id,
            'priority': o.priority, 'requested_end': o.requested_end,
            'minutes': 60 * int(o.quantity),
        })
    if not orders:
        OptimizationRun.objects.filter(pk=run.pk).update(
            status='failed', error_message='No candidate orders to optimize',
            finished_at=timezone.now(),
        )
        return
    payload = optimizer_service.run_optimization(run, orders=orders)
    OptimizationResult.objects.create(
        tenant=tenant, run=run,
        before_total_minutes=payload['before_total_minutes'],
        after_total_minutes=payload['after_total_minutes'],
        before_changeovers=payload['before_changeovers'],
        after_changeovers=payload['after_changeovers'],
        before_lateness=payload['before_lateness'],
        after_lateness=payload['after_lateness'],
        improvement_pct=payload['improvement_pct'],
        suggestion_json=payload['suggestion_json'],
    )
    OptimizationRun.objects.filter(pk=run.pk).update(
        status='completed', finished_at=timezone.now(),
    )
    stdout.write(f'  optimization run: 1 completed ({payload["improvement_pct"]}% gain)')


class Command(BaseCommand):
    help = 'Seed Production Planning & Scheduling demo data per tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete existing PPS data for demo tenants before seeding.',
        )

    def handle(self, *args, **options):
        flush = options.get('flush', False)
        random.seed(42)
        tenants = Tenant.objects.filter(is_active=True).exclude(slug='')
        for tenant in tenants:
            self.stdout.write(self.style.HTTP_INFO(f'\n-> {tenant.name} ({tenant.slug})'))
            set_current_tenant(tenant)

            if flush:
                self.stdout.write('  flushing existing PPS data...')
                ScheduledOperation.all_objects.filter(tenant=tenant).delete()
                OptimizationResult.all_objects.filter(tenant=tenant).delete()
                OptimizationRun.all_objects.filter(tenant=tenant).delete()
                OptimizationObjective.all_objects.filter(tenant=tenant).delete()
                ScenarioResult.all_objects.filter(tenant=tenant).delete()
                ScenarioChange.all_objects.filter(tenant=tenant).delete()
                Scenario.all_objects.filter(tenant=tenant).delete()
                CapacityLoad.all_objects.filter(tenant=tenant).delete()
                ProductionOrder.all_objects.filter(tenant=tenant).delete()
                MPSLine.all_objects.filter(tenant=tenant).delete()
                MasterProductionSchedule.all_objects.filter(tenant=tenant).delete()
                DemandForecast.all_objects.filter(tenant=tenant).delete()
                RoutingOperation.all_objects.filter(tenant=tenant).delete()
                Routing.all_objects.filter(tenant=tenant).delete()
                CapacityCalendar.all_objects.filter(tenant=tenant).delete()
                WorkCenter.all_objects.filter(tenant=tenant).delete()

            if MasterProductionSchedule.objects.filter(tenant=tenant).exists() and not flush:
                self.stdout.write(self.style.WARNING(
                    '  PPS data already exists — skipping. Use --flush to re-seed.',
                ))
                continue

            admin_user = User.objects.filter(
                tenant=tenant, is_tenant_admin=True,
            ).first()
            if admin_user is None:
                self.stdout.write(self.style.WARNING(
                    f'  No tenant admin found for {tenant.slug} — skipping.',
                ))
                continue

            products_by_sku = {p.sku: p for p in Product.objects.filter(tenant=tenant)}
            if not products_by_sku:
                self.stdout.write(self.style.WARNING(
                    f'  No products found for {tenant.slug} — run seed_plm first.',
                ))
                continue

            _seed_work_centers(tenant, self.stdout)
            wcs = {wc.code: wc for wc in WorkCenter.objects.filter(tenant=tenant)}
            _seed_routings(tenant, products_by_sku, admin_user, wcs, self.stdout)
            _seed_forecasts(tenant, products_by_sku, self.stdout)
            mps = _seed_mps(tenant, products_by_sku, admin_user, self.stdout)
            _seed_orders(tenant, products_by_sku, mps, admin_user, self.stdout)
            _seed_capacity_load(tenant, self.stdout)
            _seed_scenario(tenant, mps, admin_user, self.stdout)
            _seed_optimization(tenant, mps, admin_user, self.stdout)

        set_current_tenant(None)
        self.stdout.write(self.style.SUCCESS('\nPPS seeding complete.'))
        self.stdout.write(self.style.WARNING(
            'Reminder: log in as a tenant admin (e.g. admin_acme / Welcome@123) to see PPS data — '
            'the Django superuser has tenant=None and will see empty pages.',
        ))
