"""Idempotent seeder for Quality Management (QMS) demo data.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush
  - Skips per-tenant if data already exists
  - Auto-numbered records check existence before creating

Per Lesson L-09, all stdout text is plain ASCII (no Unicode arrows / emoji).
Per Lesson L-08, horizons aligned to existing PPS / MES data so the dashboard
shows non-zero counts immediately.

Per tenant produces:
    - 3 IQC plans + 6 inspections (mix accepted / rejected / pending) + 12 measurements
    - 3 IPQC plans pinned to existing routing operations + 8 inspections
      + 1 SPC chart with 25 control chart points (one OOC)
    - 2 FQC plans + 5 inspections (mix passed / failed / pending) + 2 CoA records
    - 4 NCRs (one per source: iqc, ipqc, fqc, customer) with RCA + 1-2 CAs + 1-2 PAs
    - 6 measurement equipment items (one due in 5 days, one overdue, four healthy)
    - 8 calibration records distributed across equipment
    - 3 calibration standards
"""
import random
import re
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.mes.models import MESWorkOrder, MESWorkOrderOperation
from apps.plm.models import Product
from apps.pps.models import RoutingOperation, WorkCenter

from apps.qms.models import (
    CalibrationRecord, CalibrationStandard, CertificateOfAnalysis,
    ControlChartPoint, CorrectiveAction, FinalInspection, FinalInspectionPlan,
    FinalTestResult, FinalTestSpec, IncomingInspection, IncomingInspectionPlan,
    InspectionCharacteristic, InspectionMeasurement, MeasurementEquipment,
    NCRAttachment, NonConformanceReport, PreventiveAction, ProcessInspection,
    ProcessInspectionPlan, RootCauseAnalysis, SPCChart, ToleranceVerification,
)
from apps.qms.services import aql as aql_service
from apps.qms.services import spc as spc_service


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
# 7.1  IQC
# ---------------------------------------------------------------------------

def _seed_iqc(tenant, admin_user, stdout):
    if IncomingInspectionPlan.all_objects.filter(tenant=tenant).exists():
        stdout.write('  iqc: skipped (already seeded)')
        return
    raw_components = list(Product.objects.filter(
        tenant=tenant, product_type__in=('raw_material', 'component'),
    )[:3])
    if not raw_components:
        stdout.write('  iqc: no raw_material / component products - skipping')
        return

    plan_count = 0
    char_count = 0
    inspection_count = 0
    measurement_count = 0

    for i, product in enumerate(raw_components):
        plan = IncomingInspectionPlan.all_objects.create(
            tenant=tenant,
            product=product,
            aql_level='II',
            aql_value=Decimal('2.5'),
            sample_method='single',
            version='1.0',
            description=f'Incoming inspection plan for {product.sku}.',
            is_active=True,
        )
        plan_count += 1
        # 3 characteristics per plan
        for j, (name, ctype, nominal, usl, lsl, uom) in enumerate([
            ('Length', 'dimensional', Decimal('100.000'), Decimal('100.500'), Decimal('99.500'), 'mm'),
            ('Surface finish', 'visual', None, None, None, ''),
            ('Hardness', 'mechanical', Decimal('45.0'), Decimal('48.0'), Decimal('42.0'), 'HRC'),
        ], start=1):
            InspectionCharacteristic.all_objects.create(
                tenant=tenant, plan=plan, sequence=j * 10,
                name=name, characteristic_type=ctype,
                nominal=nominal, usl=usl, lsl=lsl, unit_of_measure=uom,
                is_critical=(j == 3),
            )
            char_count += 1

    # 6 inspections - 2 per plan, mixed statuses
    statuses = [
        ('accepted', timedelta(days=5)),
        ('rejected', timedelta(days=3)),
        ('accepted_with_deviation', timedelta(days=2)),
        ('pending', timedelta(days=1)),
        ('in_inspection', timedelta(hours=4)),
        ('accepted', timedelta(hours=12)),
    ]
    for k, (status, age) in enumerate(statuses):
        plan = IncomingInspectionPlan.all_objects.filter(tenant=tenant)[k % plan_count]
        try:
            aql_plan = aql_service.lookup_plan(500, 2.5, 'II')
            sample_size = aql_plan.sample_size
            ac = aql_plan.accept_number
            re_ = aql_plan.reject_number
        except (ValueError, KeyError):
            sample_size, ac, re_ = 50, 5, 6
        ts = timezone.now() - age
        rejected = Decimal('5') if status == 'rejected' else Decimal('0')
        accepted = Decimal('495') if status in ('accepted', 'accepted_with_deviation') else Decimal('0')
        inspection = IncomingInspection.all_objects.create(
            tenant=tenant,
            inspection_number=_next_number(IncomingInspection, tenant, 'inspection_number', 'IQC'),
            product=plan.product,
            plan=plan,
            supplier_name=f'Supplier {chr(65 + k)} Co.',
            po_reference=f'PO-DEMO-{1000 + k}',
            lot_number=f'LOT-{ts:%Y%m%d}-{k:03d}',
            received_qty=Decimal('500'),
            sample_size=sample_size,
            accept_number=ac,
            reject_number=re_,
            accepted_qty=accepted,
            rejected_qty=rejected,
            status=status,
            inspected_by=admin_user if status not in ('pending',) else None,
            inspected_at=ts if status not in ('pending',) else None,
            deviation_notes='Slight surface scratches noted - released with deviation.' if status == 'accepted_with_deviation' else '',
        )
        inspection_count += 1
        # Measurements only for accepted / rejected
        if status not in ('pending', 'in_inspection'):
            for c in plan.characteristics.all()[:2]:
                InspectionMeasurement.all_objects.create(
                    tenant=tenant,
                    inspection=inspection,
                    characteristic=c,
                    measured_value=c.nominal if c.nominal else None,
                    is_pass=(status != 'rejected' or c.sequence == 30),
                )
                measurement_count += 1

    stdout.write(
        f'  iqc: {plan_count} plans, {char_count} chars, '
        f'{inspection_count} inspections, {measurement_count} measurements'
    )


# ---------------------------------------------------------------------------
# 7.2  IPQC + SPC
# ---------------------------------------------------------------------------

def _seed_ipqc(tenant, admin_user, stdout):
    if ProcessInspectionPlan.all_objects.filter(tenant=tenant).exists():
        stdout.write('  ipqc: skipped (already seeded)')
        return
    routing_ops = list(RoutingOperation.objects.filter(tenant=tenant).select_related('routing__product')[:3])
    if not routing_ops:
        stdout.write('  ipqc: no routing operations - skipping')
        return

    plan_count = 0
    inspection_count = 0
    spc_chart = None

    for i, op in enumerate(routing_ops):
        plan = ProcessInspectionPlan.all_objects.create(
            tenant=tenant,
            product=op.routing.product,
            routing_operation=op,
            name=f'IPQC for {op.operation_name}',
            frequency='every_n_parts',
            frequency_value=10,
            chart_type='x_bar_r' if i == 0 else 'none',
            subgroup_size=5,
            nominal=Decimal('100.000'),
            usl=Decimal('100.500'),
            lsl=Decimal('99.500'),
            unit_of_measure='mm',
            is_active=True,
        )
        plan_count += 1
        if plan.chart_type == 'x_bar_r':
            spc_chart = SPCChart.all_objects.create(
                tenant=tenant,
                plan=plan,
                chart_type='x_bar_r',
                subgroup_size=5,
            )

    # 8 inspections, mostly on the first plan (so SPC chart has data)
    plans = list(ProcessInspectionPlan.all_objects.filter(tenant=tenant))
    chart_plan = plans[0]
    rng = random.Random(42)  # deterministic
    for j in range(8):
        plan = chart_plan if j < 6 else plans[1 % len(plans)]
        # Inject one outlier at index 5 to demonstrate OOC
        if j == 5:
            value = Decimal('103.5')  # well outside the limits
            result = 'fail'
        else:
            value = Decimal(str(round(100.0 + rng.uniform(-0.4, 0.4), 3)))
            result = 'pass' if abs(float(value) - 100) < 0.5 else 'borderline'
        ProcessInspection.all_objects.create(
            tenant=tenant,
            inspection_number=_next_number(ProcessInspection, tenant, 'inspection_number', 'IPQC'),
            plan=plan,
            inspected_at=timezone.now() - timedelta(hours=j * 2),
            inspector=admin_user,
            subgroup_index=j + 1,
            measured_value=value,
            result=result,
            notes='Routine in-process check.',
        )
        inspection_count += 1

    # Compute SPC chart limits + populate ControlChartPoints
    points_added = 0
    if spc_chart is not None:
        # Build 25 synthetic subgroups for limit computation
        subgroups = []
        for s in range(25):
            subgroups.append([
                Decimal(str(round(100.0 + rng.uniform(-0.3, 0.3), 3)))
                for _ in range(5)
            ])
        try:
            limits = spc_service.compute_xbar_r(subgroups)
            spc_chart.cl = limits.cl
            spc_chart.ucl = limits.ucl
            spc_chart.lcl = limits.lcl
            spc_chart.cl_r = limits.cl_r
            spc_chart.ucl_r = limits.ucl_r
            spc_chart.lcl_r = limits.lcl_r
            spc_chart.sample_size_used = limits.sample_size_used
            spc_chart.recomputed_at = timezone.now()
            spc_chart.save()
            # 25 control chart points - mostly near CL, one outlier
            base_inspections = list(
                ProcessInspection.all_objects.filter(tenant=tenant, plan=chart_plan).order_by('subgroup_index')
            )
            for s in range(25):
                value = Decimal(str(round(100.0 + rng.uniform(-0.3, 0.3), 3)))
                if s == 12:
                    value = Decimal('103.0')  # OOC
                violations_list = spc_service.check_western_electric(
                    [float(value)], cl=limits.cl, ucl=limits.ucl, lcl=limits.lcl,
                )
                violations = violations_list[0] if violations_list else []
                is_ooc = spc_service.is_out_of_control(violations)
                inspection_link = base_inspections[s] if s < len(base_inspections) else None
                ControlChartPoint.all_objects.create(
                    tenant=tenant,
                    chart=spc_chart,
                    inspection=inspection_link,
                    subgroup_index=s + 1,
                    value=value,
                    is_out_of_control=is_ooc,
                    rule_violations=violations,
                    recorded_at=timezone.now() - timedelta(hours=(25 - s)),
                )
                points_added += 1
        except ValueError as exc:
            stdout.write(f'  ipqc: SPC limit computation skipped ({exc})')

    stdout.write(
        f'  ipqc: {plan_count} plans, {inspection_count} inspections, '
        f'{points_added} chart points'
    )


# ---------------------------------------------------------------------------
# 7.3  FQC + CoA
# ---------------------------------------------------------------------------

def _seed_fqc(tenant, admin_user, stdout):
    if FinalInspectionPlan.all_objects.filter(tenant=tenant).exists():
        stdout.write('  fqc: skipped (already seeded)')
        return
    finished_goods = list(Product.objects.filter(
        tenant=tenant, product_type='finished_good',
    )[:2])
    if not finished_goods:
        stdout.write('  fqc: no finished_good products - skipping')
        return

    plan_count = 0
    spec_count = 0
    inspection_count = 0
    coa_count = 0

    for i, product in enumerate(finished_goods):
        plan = FinalInspectionPlan.all_objects.create(
            tenant=tenant,
            product=product,
            name=f'Final Inspection - {product.sku}',
            version='1.0',
            description='Standard finished-goods test protocol.',
            is_active=True,
        )
        plan_count += 1
        # 3 test specs per plan
        for s, (name, method, nominal, usl, lsl, critical) in enumerate([
            ('Visual inspection', 'visual', None, None, None, False),
            ('Dimensional check', 'dimensional', Decimal('100.000'), Decimal('100.500'), Decimal('99.500'), True),
            ('Functional test', 'functional', None, None, None, True),
        ], start=1):
            FinalTestSpec.all_objects.create(
                tenant=tenant, plan=plan, sequence=s * 10,
                test_name=name, test_method=method,
                nominal=nominal, usl=usl, lsl=lsl,
                unit_of_measure='mm' if method == 'dimensional' else '',
                is_critical=critical,
            )
            spec_count += 1

    # 5 final inspections - 3 passed, 1 failed, 1 pending; tie to MES work orders if available
    work_orders = list(MESWorkOrder.objects.filter(tenant=tenant)[:5])
    plans = list(FinalInspectionPlan.all_objects.filter(tenant=tenant))
    statuses = [
        ('passed', timedelta(days=4)),
        ('passed', timedelta(days=2)),
        ('failed', timedelta(days=1)),
        ('released_with_deviation', timedelta(hours=8)),
        ('pending', timedelta(hours=2)),
    ]
    for k, (status, age) in enumerate(statuses):
        plan = plans[k % len(plans)]
        wo = work_orders[k] if k < len(work_orders) else None
        ts = timezone.now() - age
        accepted = Decimal('100') if status in ('passed', 'released_with_deviation') else Decimal('0')
        rejected = Decimal('100') if status == 'failed' else Decimal('0')
        inspection = FinalInspection.all_objects.create(
            tenant=tenant,
            inspection_number=_next_number(FinalInspection, tenant, 'inspection_number', 'FQC'),
            plan=plan,
            work_order=wo,
            lot_number=f'LOT-FG-{ts:%Y%m%d}-{k:03d}',
            quantity_tested=Decimal('100'),
            accepted_qty=accepted,
            rejected_qty=rejected,
            status=status,
            inspected_by=admin_user if status != 'pending' else None,
            inspected_at=ts if status != 'pending' else None,
            deviation_notes='Lot accepted with minor visual flaw.' if status == 'released_with_deviation' else '',
        )
        inspection_count += 1
        # Test results for non-pending
        if status != 'pending':
            for spec in plan.specs.all():
                FinalTestResult.all_objects.create(
                    tenant=tenant,
                    inspection=inspection,
                    spec=spec,
                    measured_value=spec.nominal if spec.nominal else None,
                    measured_text='Within spec' if spec.nominal is None else '',
                    is_pass=(status != 'failed'),
                )
        # CoA for passed / released_with_deviation
        if status in ('passed', 'released_with_deviation'):
            CertificateOfAnalysis.all_objects.create(
                tenant=tenant,
                inspection=inspection,
                coa_number=_next_number(CertificateOfAnalysis, tenant, 'coa_number', 'COA'),
                issued_at=ts,
                issued_by=admin_user,
                customer_name=f'Customer {chr(65 + k)}',
                customer_reference=f'PO-CUST-{2000 + k}',
                released_to_customer=(status == 'passed' and k == 0),
                released_at=ts if (status == 'passed' and k == 0) else None,
                released_by=admin_user if (status == 'passed' and k == 0) else None,
            )
            coa_count += 1

    stdout.write(
        f'  fqc: {plan_count} plans, {spec_count} specs, '
        f'{inspection_count} inspections, {coa_count} CoAs'
    )


# ---------------------------------------------------------------------------
# 7.4  NCR + CAPA
# ---------------------------------------------------------------------------

def _seed_ncrs(tenant, admin_user, stdout):
    if NonConformanceReport.all_objects.filter(tenant=tenant).exists():
        stdout.write('  ncrs: skipped (already seeded)')
        return

    iqc_inspection = IncomingInspection.all_objects.filter(
        tenant=tenant, status='rejected',
    ).first()
    ipqc_inspection = ProcessInspection.all_objects.filter(
        tenant=tenant, result='fail',
    ).first()
    fqc_inspection = FinalInspection.all_objects.filter(
        tenant=tenant, status='failed',
    ).first()
    product = Product.objects.filter(tenant=tenant).first()

    ncr_specs = [
        ('iqc', 'major', 'open',
         'IQC reject - dimensional out of tolerance',
         'Lot rejected at incoming inspection. 5 of 50 samples failed dimensional check.',
         iqc_inspection, None, None),
        ('ipqc', 'major', 'investigating',
         'IPQC drift detected on op',
         'Process drift observed during routine in-process inspection. SPC chart shows out-of-control point.',
         None, ipqc_inspection, None),
        ('fqc', 'critical', 'awaiting_capa',
         'FQC fail - functional test',
         'Finished goods lot failed functional test at final inspection. Customer impact possible.',
         None, None, fqc_inspection),
        ('customer', 'minor', 'closed',
         'Customer complaint - minor packaging defect',
         'Customer reported minor packaging damage on shipment. Resolved with replacement.',
         None, None, None),
    ]
    ncr_count = 0
    rca_count = 0
    ca_count = 0
    pa_count = 0
    for k, (source, severity, status, title, desc, iqc, ipqc, fqc) in enumerate(ncr_specs):
        ts = timezone.now() - timedelta(days=k + 1)
        closed_at = timezone.now() - timedelta(hours=12) if status == 'closed' else None
        ncr = NonConformanceReport.all_objects.create(
            tenant=tenant,
            ncr_number=_next_number(NonConformanceReport, tenant, 'ncr_number', 'NCR'),
            source=source,
            severity=severity,
            status=status,
            title=title,
            description=desc,
            product=product,
            lot_number=f'LOT-NCR-{ts:%Y%m%d}',
            quantity_affected=Decimal('5') if severity == 'major' else Decimal('100'),
            iqc_inspection=iqc,
            ipqc_inspection=ipqc,
            fqc_inspection=fqc,
            reported_by=admin_user,
            reported_at=ts,
            assigned_to=admin_user,
            closed_by=admin_user if status == 'closed' else None,
            closed_at=closed_at,
            resolution_summary='Replacement shipment dispatched. Customer satisfied.' if status == 'closed' else '',
        )
        ncr_count += 1
        # RCA
        RootCauseAnalysis.all_objects.create(
            tenant=tenant, ncr=ncr,
            method='five_why',
            analysis_text='Why 1: defect noticed.\nWhy 2: spec exceeded.\nWhy 3: tool worn.\nWhy 4: missed PM.\nWhy 5: schedule lapse.',
            root_cause_summary='Tool wear due to missed preventive maintenance schedule.',
            analyzed_by=admin_user if status != 'open' else None,
            analyzed_at=ts + timedelta(hours=2) if status != 'open' else None,
        )
        rca_count += 1
        # 1-2 Corrective Actions
        for ca_seq, action in enumerate([
            'Replace worn tooling.',
            'Re-inspect last 5 lots produced with same tooling.',
        ][:1 + (k % 2)], start=1):
            CorrectiveAction.all_objects.create(
                tenant=tenant, ncr=ncr,
                sequence=ca_seq * 10,
                action_text=action,
                owner=admin_user,
                due_date=(ts + timedelta(days=7)).date(),
                status='completed' if status == 'closed' else ('in_progress' if status in ('investigating', 'awaiting_capa') else 'open'),
                completed_at=ts + timedelta(days=2) if status == 'closed' else None,
                completed_by=admin_user if status == 'closed' else None,
                effectiveness_verified=(status == 'closed'),
            )
            ca_count += 1
        # 1-2 Preventive Actions
        for pa_seq, action in enumerate([
            'Update PM schedule frequency.',
            'Add tool-life tracking to MES dashboard.',
        ][:1 + (k % 2)], start=1):
            PreventiveAction.all_objects.create(
                tenant=tenant, ncr=ncr,
                sequence=pa_seq * 10,
                action_text=action,
                owner=admin_user,
                due_date=(ts + timedelta(days=14)).date(),
                status='completed' if status == 'closed' else 'open',
                completed_at=ts + timedelta(days=5) if status == 'closed' else None,
                completed_by=admin_user if status == 'closed' else None,
                effectiveness_verified=(status == 'closed'),
            )
            pa_count += 1

    stdout.write(
        f'  ncrs: {ncr_count} NCRs, {rca_count} RCAs, {ca_count} CAs, {pa_count} PAs'
    )


# ---------------------------------------------------------------------------
# 7.5  Calibration: Standards, Equipment, Records
# ---------------------------------------------------------------------------

def _seed_calibration_standards(tenant, stdout):
    if CalibrationStandard.all_objects.filter(tenant=tenant).exists():
        stdout.write('  standards: skipped (already seeded)')
        return list(CalibrationStandard.all_objects.filter(tenant=tenant))
    standards_data = [
        ('STD-NIST-001', 'NIST gauge block set', 'NIST'),
        ('STD-NIST-002', 'NIST master scale', 'NIST'),
        ('STD-INT-001', 'Internal reference torque wrench', 'Internal'),
    ]
    standards = []
    for sn, name, traceable in standards_data:
        s = CalibrationStandard.all_objects.create(
            tenant=tenant, name=name,
            standard_number=sn, traceable_to=traceable,
            description=f'{name} reference standard.',
            expiry_date=(timezone.now() + timedelta(days=730)).date(),
            is_active=True,
        )
        standards.append(s)
    stdout.write(f'  standards: {len(standards)} created')
    return standards


def _seed_equipment(tenant, stdout):
    if MeasurementEquipment.all_objects.filter(tenant=tenant).exists():
        stdout.write('  equipment: skipped (already seeded)')
        return list(MeasurementEquipment.all_objects.filter(tenant=tenant))
    work_centers = list(WorkCenter.objects.filter(tenant=tenant)[:3])
    now = timezone.now()
    equipment_data = [
        # (name, type, serial, mfr, model, range, uom, tolerance, days_since_cal, interval_days)
        ('Digital caliper 0-150mm', 'caliper', 'CALIPER-001', 'Mitutoyo', 'CD-15CSX',
         (Decimal('0'), Decimal('150')), 'mm', Decimal('0.020'), 360, 365),  # due in 5 days
        ('Micrometer 0-25mm', 'micrometer', 'MIC-002', 'Mitutoyo', 'MDC-25MX',
         (Decimal('0'), Decimal('25')), 'mm', Decimal('0.001'), 380, 365),  # overdue
        ('Pin gauge set', 'gauge', 'GAUGE-003', 'Vermont', 'PG-SET-A',
         (Decimal('1'), Decimal('10')), 'mm', Decimal('0.005'), 90, 365),
        ('Bench scale 30kg', 'scale', 'SCALE-004', 'A&D', 'GP-30K',
         (Decimal('0'), Decimal('30000')), 'g', Decimal('5.0'), 30, 365),
        ('Digital thermometer', 'thermometer', 'THERM-005', 'Fluke', 'F50',
         (Decimal('-50'), Decimal('500')), 'C', Decimal('0.5'), 60, 365),
        ('Multimeter 5-digit', 'multimeter', 'DMM-006', 'Keysight', '34465A',
         (Decimal('0'), Decimal('1000')), 'V', Decimal('0.01'), 120, 365),
    ]
    equipment = []
    for i, (name, etype, serial, mfr, model, (rmin, rmax), uom, tol, since_cal_days, interval) in enumerate(equipment_data):
        last = now - timedelta(days=since_cal_days)
        next_due = last + timedelta(days=interval)
        eq = MeasurementEquipment.all_objects.create(
            tenant=tenant,
            equipment_number=_next_number(MeasurementEquipment, tenant, 'equipment_number', 'EQP'),
            name=name,
            equipment_type=etype,
            serial_number=serial,
            manufacturer=mfr,
            model_number=model,
            assigned_work_center=work_centers[i % len(work_centers)] if work_centers else None,
            range_min=rmin,
            range_max=rmax,
            unit_of_measure=uom,
            tolerance=tol,
            calibration_interval_days=interval,
            last_calibrated_at=last,
            next_due_at=next_due,
            status='active',
            is_active=True,
        )
        equipment.append(eq)
    stdout.write(f'  equipment: {len(equipment)} items')
    return equipment


def _pin_equipment_due_dates(equipment, stdout):
    """After calibrations have been bulk-seeded, force the first two
    equipment items into deliberate due-soon / overdue states for the
    dashboard demo (Lesson L-16: post_save signal on CalibrationRecord
    overwrites the parent equipment's denorm fields, so we must use
    .update() AFTER the children exist to bypass the signal).
    """
    if len(equipment) < 2:
        return
    now = timezone.now()
    # Equipment 1 -> due in 5 days (yellow row)
    MeasurementEquipment.all_objects.filter(pk=equipment[0].pk).update(
        last_calibrated_at=now - timedelta(days=360),
        next_due_at=now + timedelta(days=5),
    )
    # Equipment 2 -> overdue 15 days (red row)
    MeasurementEquipment.all_objects.filter(pk=equipment[1].pk).update(
        last_calibrated_at=now - timedelta(days=380),
        next_due_at=now - timedelta(days=15),
    )
    stdout.write('  equipment due-dates: pinned 1 due-in-5d, 1 overdue')


def _seed_calibrations(tenant, equipment, standards, admin_user, stdout):
    if CalibrationRecord.all_objects.filter(tenant=tenant).exists():
        stdout.write('  calibrations: skipped (already seeded)')
        return
    if not equipment:
        return
    record_count = 0
    check_count = 0
    results_cycle = ['pass', 'pass', 'pass_with_adjustment', 'pass', 'fail', 'pass', 'pass', 'pass']
    standard = standards[0] if standards else None
    for i in range(8):
        eq = equipment[i % len(equipment)]
        result = results_cycle[i]
        cal_at = timezone.now() - timedelta(days=180 - i * 14)
        next_due = cal_at + timedelta(days=eq.calibration_interval_days)
        rec = CalibrationRecord.all_objects.create(
            tenant=tenant,
            record_number=_next_number(CalibrationRecord, tenant, 'record_number', 'CAL'),
            equipment=eq,
            calibrated_at=cal_at,
            calibrated_by=admin_user,
            external_lab_name='External Cal Lab Inc.' if i % 3 == 0 else '',
            standard=standard,
            result=result,
            next_due_at=next_due,
            notes='Calibration deviates by 0.025 mm - tool flagged for repair.' if result == 'fail' else 'Calibrated against reference standard.',
        )
        record_count += 1
        # 1-2 tolerance checks per record
        for s in range(1, 3):
            ToleranceVerification.all_objects.create(
                tenant=tenant,
                record=rec,
                sequence=s * 10,
                description=f'Check point {s} at {(s) * 50} {eq.unit_of_measure}',
                nominal=Decimal(str(s * 50)),
                as_found=Decimal(str(s * 50 + 0.005)),
                as_left=Decimal(str(s * 50)),
                tolerance=eq.tolerance or Decimal('0.05'),
                is_within_tolerance=(result != 'fail'),
                unit_of_measure=eq.unit_of_measure,
            )
            check_count += 1
    stdout.write(f'  calibrations: {record_count} records, {check_count} tolerance checks')


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = 'Seed Quality Management (QMS) demo data per active tenant.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Wipe QMS data for the 3 demo tenants and re-seed.',
        )

    def handle(self, *args, **options):
        if options['flush']:
            slugs = ['acme', 'globex', 'stark']
            tenants = Tenant.objects.filter(slug__in=slugs)
            self.stdout.write(self.style.WARNING(
                f'Flushing QMS data for {tenants.count()} demo tenants...'
            ))
            for model in (
                NCRAttachment, PreventiveAction, CorrectiveAction,
                RootCauseAnalysis, NonConformanceReport,
                ToleranceVerification, CalibrationRecord,
                CertificateOfAnalysis, FinalTestResult, FinalInspection,
                FinalTestSpec, FinalInspectionPlan,
                ControlChartPoint, SPCChart, ProcessInspection,
                ProcessInspectionPlan,
                InspectionMeasurement, IncomingInspection,
                InspectionCharacteristic, IncomingInspectionPlan,
                MeasurementEquipment, CalibrationStandard,
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

            _seed_iqc(tenant, admin_user, self.stdout)
            _seed_ipqc(tenant, admin_user, self.stdout)
            _seed_fqc(tenant, admin_user, self.stdout)
            _seed_ncrs(tenant, admin_user, self.stdout)
            standards = _seed_calibration_standards(tenant, self.stdout)
            equipment = _seed_equipment(tenant, self.stdout)
            _seed_calibrations(tenant, equipment, standards, admin_user, self.stdout)
            _pin_equipment_due_dates(equipment, self.stdout)

        self.stdout.write(self.style.SUCCESS('\nQMS seed complete.'))
        self.stdout.write(self.style.WARNING(
            'Reminder: superuser "admin" has tenant=None - log in as a tenant '
            'admin (e.g. admin_acme / Welcome@123) to see QMS data.'
        ))
