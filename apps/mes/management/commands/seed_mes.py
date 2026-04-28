"""Idempotent seeder for Shop Floor Control demo data.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush
  - Skips per-tenant if data already exists
  - Auto-numbered records (WO-, AND-, SOP-) check existence before creating

Per Lesson L-09, all stdout text is plain ASCII (no Unicode arrows / dots /
emoji - the Windows cp1252 console crashes on them).

Per tenant produces:
    - 5 ShopFloorOperator profiles (B0001 - B0005) linked to seeded staff users
    - Up to 6 MESWorkOrders (one per released / in-progress production order)
      with operations fanned out from the parent's routing
    - ~12 OperatorTimeLog rows across the in-progress + completed work orders
    - ~8 ProductionReport rows on the in-progress + completed ops
    - 4 AndonAlerts (open / acknowledged / resolved / cancelled)
    - 3 WorkInstructions with 1-2 versions each (one released, one draft)
      linked to seeded routing operations; one carries a video_url
    - 4 WorkInstructionAcknowledgement rows on the released versions
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.pps.models import ProductionOrder, WorkCenter

from apps.mes.models import (
    AndonAlert, MESWorkOrder, MESWorkOrderOperation, OperatorTimeLog,
    ProductionReport, ShopFloorOperator, WorkInstruction,
    WorkInstructionAcknowledgement, WorkInstructionVersion,
)
from apps.mes.services import dispatcher


_SEQ_RE = re.compile(r'^[A-Z]+-(\d+)$')


def _next_number(model, tenant, field, prefix, width=5):
    last = model.all_objects.filter(tenant=tenant).aggregate(Max(field))[f'{field}__max']
    n = 1
    if last:
        m = _SEQ_RE.match(str(last))
        if m:
            n = int(m.group(1)) + 1
        else:
            n = model.all_objects.filter(tenant=tenant).count() + 1
    return f'{prefix}-{n:0{width}d}'


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def _seed_operators(tenant, stdout):
    if ShopFloorOperator.all_objects.filter(tenant=tenant).exists():
        stdout.write('  operators: skipped (already seeded)')
        return list(ShopFloorOperator.all_objects.filter(tenant=tenant))
    staff_users = list(User.objects.filter(
        tenant=tenant, is_active=True, is_tenant_admin=False,
    )[:5])
    if not staff_users:
        stdout.write('  no staff users available; using tenant admin only')
        admin_user = User.objects.filter(tenant=tenant, is_tenant_admin=True).first()
        staff_users = [admin_user] if admin_user else []
    work_center = WorkCenter.all_objects.filter(tenant=tenant, is_active=True).first()
    operators = []
    for i, user in enumerate(staff_users, start=1):
        if user is None:
            continue
        operator, _ = ShopFloorOperator.all_objects.get_or_create(
            tenant=tenant, user=user,
            defaults={
                'badge_number': f'B{i:04d}',
                'default_work_center': work_center,
                'is_active': True,
                'notes': 'Seeded operator profile.',
            },
        )
        operators.append(operator)
    stdout.write(f'  operators: {len(operators)} created')
    return operators


# ---------------------------------------------------------------------------
# Work Orders (dispatch from existing PPS production orders)
# ---------------------------------------------------------------------------

def _seed_work_orders(tenant, admin_user, stdout):
    if MESWorkOrder.all_objects.filter(tenant=tenant).exists():
        stdout.write('  work orders: skipped (already seeded)')
        return list(MESWorkOrder.all_objects.filter(tenant=tenant))
    pos = list(ProductionOrder.all_objects.filter(
        tenant=tenant, status__in=('released', 'in_progress', 'completed'),
    ).select_related('routing'))
    work_orders = []
    skipped_no_routing = 0
    for po in pos[:6]:
        # Re-bump status to 'released' temporarily so dispatcher accepts it
        # (in_progress / completed still need a MESWorkOrder for demo purposes).
        original_status = po.status
        if original_status != 'released':
            ProductionOrder.all_objects.filter(pk=po.pk).update(status='released')
            po.refresh_from_db()
        if po.routing_id is None:
            skipped_no_routing += 1
            continue
        try:
            wo = dispatcher.dispatch_production_order(po, dispatched_by=admin_user)
        except dispatcher.DispatchError:
            skipped_no_routing += 1
            if original_status != 'released':
                ProductionOrder.all_objects.filter(pk=po.pk).update(status=original_status)
            continue
        # Restore the parent PPS order status so PPS list filters stay accurate
        if original_status != 'released':
            ProductionOrder.all_objects.filter(pk=po.pk).update(status=original_status)
        work_orders.append(wo)
    # Spread MES work order statuses to give a realistic dashboard
    if work_orders:
        spread = ['dispatched', 'dispatched', 'in_progress', 'in_progress', 'on_hold', 'completed']
        for wo, target in zip(work_orders, spread):
            if target == 'in_progress':
                MESWorkOrder.all_objects.filter(pk=wo.pk).update(status='in_progress')
            elif target == 'on_hold':
                MESWorkOrder.all_objects.filter(pk=wo.pk).update(status='on_hold')
            elif target == 'completed':
                MESWorkOrder.all_objects.filter(pk=wo.pk).update(
                    status='completed',
                    completed_at=timezone.now() - timedelta(days=1),
                    completed_by=admin_user,
                )
    stdout.write(f'  work orders: {len(work_orders)} created (skipped {skipped_no_routing} without routing)')
    return list(MESWorkOrder.all_objects.filter(tenant=tenant))


# ---------------------------------------------------------------------------
# Time logs + production reports for the in-progress + completed work orders
# ---------------------------------------------------------------------------

def _seed_time_logs_and_reports(tenant, work_orders, operators, admin_user, stdout):
    if not work_orders or not operators:
        return
    if OperatorTimeLog.all_objects.filter(tenant=tenant).exists():
        stdout.write('  time logs / reports: skipped (already seeded)')
        return
    log_count = 0
    report_count = 0
    primary_operator = operators[0]
    backup_operator = operators[1] if len(operators) > 1 else operators[0]
    now = timezone.now()
    # Clock-in for primary operator
    OperatorTimeLog.all_objects.create(
        tenant=tenant, operator=primary_operator,
        action='clock_in', recorded_at=now - timedelta(hours=4),
        notes='Seeded clock-in.',
    )
    log_count += 1
    OperatorTimeLog.all_objects.create(
        tenant=tenant, operator=backup_operator,
        action='clock_in', recorded_at=now - timedelta(hours=3),
        notes='Seeded clock-in.',
    )
    log_count += 1

    for wo in work_orders:
        if wo.status not in ('in_progress', 'completed'):
            continue
        ops = list(MESWorkOrderOperation.all_objects.filter(work_order=wo).order_by('sequence'))
        if not ops:
            continue
        first_op = ops[0]
        OperatorTimeLog.all_objects.create(
            tenant=tenant, operator=primary_operator,
            work_order_operation=first_op,
            action='start_job', recorded_at=now - timedelta(hours=3),
            notes=f'Seeded start on {first_op.operation_name}.',
        )
        log_count += 1
        target_status = 'completed' if wo.status == 'completed' else 'running'
        if target_status == 'completed':
            OperatorTimeLog.all_objects.create(
                tenant=tenant, operator=primary_operator,
                work_order_operation=first_op,
                action='stop_job', recorded_at=now - timedelta(hours=1),
                notes='Seeded stop.',
            )
            log_count += 1
            MESWorkOrderOperation.all_objects.filter(pk=first_op.pk).update(
                status='completed',
                started_at=now - timedelta(hours=3),
                completed_at=now - timedelta(hours=1),
                actual_minutes=Decimal('120.00'),
                total_good_qty=wo.quantity_to_build,
            )
            ProductionReport.all_objects.create(
                tenant=tenant, work_order_operation=first_op,
                good_qty=wo.quantity_to_build,
                scrap_qty=Decimal('1'),
                rework_qty=Decimal('0'),
                scrap_reason='material_defect',
                cycle_time_minutes=Decimal('1.5'),
                reported_by=admin_user,
                reported_at=now - timedelta(hours=1, minutes=5),
                notes='Seeded production report.',
            )
            report_count += 1
        else:
            MESWorkOrderOperation.all_objects.filter(pk=first_op.pk).update(
                status='running',
                started_at=now - timedelta(hours=3),
                actual_minutes=Decimal('60.00'),
                current_operator=primary_operator.user,
                total_good_qty=Decimal('0'),
            )
            ProductionReport.all_objects.create(
                tenant=tenant, work_order_operation=first_op,
                good_qty=Decimal('5'),
                scrap_qty=Decimal('0'),
                rework_qty=Decimal('0'),
                scrap_reason='',
                cycle_time_minutes=Decimal('1.2'),
                reported_by=admin_user,
                reported_at=now - timedelta(hours=2),
                notes='Seeded interim quantity report.',
            )
            report_count += 1
        # Roll the parent work order rollup
        agg_good = first_op.total_good_qty if target_status == 'completed' else Decimal('5')
        MESWorkOrder.all_objects.filter(pk=wo.pk).update(
            quantity_completed=agg_good,
            quantity_scrapped=Decimal('1') if target_status == 'completed' else Decimal('0'),
        )
    stdout.write(f'  time logs: {log_count} · production reports: {report_count}')


# ---------------------------------------------------------------------------
# Andon alerts
# ---------------------------------------------------------------------------

def _seed_andon(tenant, work_orders, admin_user, stdout):
    if AndonAlert.all_objects.filter(tenant=tenant).exists():
        stdout.write('  andon alerts: skipped (already seeded)')
        return
    work_centers = list(WorkCenter.all_objects.filter(tenant=tenant, is_active=True)[:3])
    if not work_centers:
        stdout.write('  andon: no work centers - skipped')
        return
    fixtures = [
        ('quality', 'high', 'Surface defect on output', 'open'),
        ('material', 'medium', 'Stock running low - awaiting replenishment', 'acknowledged'),
        ('equipment', 'critical', 'Spindle vibration above threshold', 'resolved'),
        ('safety', 'low', 'Safety line tape faded - needs refresh', 'cancelled'),
    ]
    now = timezone.now()
    created = 0
    for i, (atype, sev, title, status) in enumerate(fixtures):
        wc = work_centers[i % len(work_centers)]
        wo = work_orders[i % len(work_orders)] if work_orders else None
        number = _next_number(AndonAlert, tenant, 'alert_number', 'AND')
        alert = AndonAlert.all_objects.create(
            tenant=tenant, alert_number=number,
            alert_type=atype, severity=sev,
            title=title,
            message=f'Seeded demo {atype} alert raised at {wc.code}.',
            work_center=wc, work_order=wo,
            status=status,
            raised_by=admin_user,
            raised_at=now - timedelta(hours=3 + i),
        )
        if status == 'acknowledged':
            AndonAlert.all_objects.filter(pk=alert.pk).update(
                acknowledged_by=admin_user,
                acknowledged_at=now - timedelta(hours=2),
            )
        elif status == 'resolved':
            AndonAlert.all_objects.filter(pk=alert.pk).update(
                acknowledged_by=admin_user,
                acknowledged_at=now - timedelta(hours=2),
                resolved_by=admin_user,
                resolved_at=now - timedelta(hours=1),
                resolution_notes='Seeded resolution note.',
            )
        created += 1
    stdout.write(f'  andon alerts: {created} created')


# ---------------------------------------------------------------------------
# Work Instructions
# ---------------------------------------------------------------------------

def _seed_work_instructions(tenant, admin_user, stdout):
    if WorkInstruction.all_objects.filter(tenant=tenant).exists():
        stdout.write('  work instructions: skipped (already seeded)')
        return
    from apps.pps.models import RoutingOperation
    from apps.plm.models import Product
    rops = list(RoutingOperation.all_objects.filter(tenant=tenant)[:3])
    products = list(Product.all_objects.filter(tenant=tenant, status='active')[:3])
    fixtures = [
        ('Standard Setup Procedure', 'sop',
         'Follow the standard setup steps before starting any job. Calibrate tooling per spec sheet.'),
        ('Quality Inspection Checklist', 'quality_check',
         'Perform first-piece inspection per drawing tolerances. Record measurements in the report.'),
        ('Safety Lockout Procedure', 'safety',
         'Lock out energy sources before any maintenance. Verify with the lock log before reset.'),
    ]
    created_wi = 0
    created_v = 0
    created_ack = 0
    for i, (title, doc_type, content) in enumerate(fixtures):
        rop = rops[i] if i < len(rops) else None
        product = products[i] if i < len(products) and rop is None else None
        if rop is None and product is None and rops:
            rop = rops[0]
        number = _next_number(WorkInstruction, tenant, 'instruction_number', 'SOP')
        wi = WorkInstruction.all_objects.create(
            tenant=tenant,
            instruction_number=number,
            title=title,
            doc_type=doc_type,
            routing_operation=rop,
            product=product,
            status='draft',
            created_by=admin_user,
        )
        created_wi += 1
        v1 = WorkInstructionVersion.all_objects.create(
            tenant=tenant, instruction=wi, version='1.0',
            content=content,
            video_url='https://example.com/video' if i == 0 else '',
            change_notes='Initial seeded version.',
            status='released',
            uploaded_by=admin_user,
        )
        created_v += 1
        WorkInstruction.all_objects.filter(pk=wi.pk).update(
            current_version=v1, status='released',
            released_by=admin_user, released_at=timezone.now(),
        )
        if i == 0:
            WorkInstructionVersion.all_objects.create(
                tenant=tenant, instruction=wi, version='1.1',
                content=content + '\n\nDraft revision: clarify torque spec.',
                change_notes='Clarify torque spec (draft).',
                status='draft',
                uploaded_by=admin_user,
            )
            created_v += 1
        # Seed two acks on the first instruction
        if i == 0:
            staff = list(User.objects.filter(tenant=tenant, is_tenant_admin=False)[:2])
            for s in staff:
                WorkInstructionAcknowledgement.all_objects.create(
                    tenant=tenant, instruction=wi,
                    instruction_version=v1.version,
                    user=s,
                    signature_text=s.get_full_name() or s.username,
                )
                created_ack += 1
    stdout.write(
        f'  work instructions: {created_wi} created, {created_v} versions, {created_ack} acks'
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Seed Shop Floor Control (MES) demo data per active tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Wipe MES data for the 3 demo tenants and re-seed.',
        )

    def handle(self, *args, **options):
        if options['flush']:
            slugs = ['acme', 'globex', 'stark']
            tenants = Tenant.objects.filter(slug__in=slugs)
            self.stdout.write(self.style.WARNING(
                f'Flushing MES data for {tenants.count()} demo tenants...'
            ))
            for model in (
                WorkInstructionAcknowledgement, WorkInstructionVersion, WorkInstruction,
                AndonAlert, ProductionReport, OperatorTimeLog,
                MESWorkOrderOperation, MESWorkOrder, ShopFloorOperator,
            ):
                model.all_objects.filter(tenant__in=tenants).delete()

        for tenant in Tenant.objects.filter(is_active=True):
            self.stdout.write(self.style.HTTP_INFO(f'\n-> Tenant: {tenant.name}'))
            admin_user = User.objects.filter(
                tenant=tenant, is_tenant_admin=True,
            ).first()
            if admin_user is None:
                self.stdout.write('  no tenant admin - skipping')
                continue

            operators = _seed_operators(tenant, self.stdout)
            work_orders = _seed_work_orders(tenant, admin_user, self.stdout)
            _seed_time_logs_and_reports(tenant, work_orders, operators, admin_user, self.stdout)
            _seed_andon(tenant, work_orders, admin_user, self.stdout)
            _seed_work_instructions(tenant, admin_user, self.stdout)

        self.stdout.write(self.style.SUCCESS('\nMES seed complete.'))
        self.stdout.write(self.style.WARNING(
            'Reminder: superuser "admin" has tenant=None - log in as a tenant '
            'admin (e.g. admin_acme / Welcome@123) to see MES data.'
        ))
