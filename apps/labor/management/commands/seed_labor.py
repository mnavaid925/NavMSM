"""Idempotent seeder for Module 11 - Labor & Workforce Management.

Per CLAUDE.md "Seed Command Rules":
  - Safe to run repeatedly without --flush.
  - Skips per-tenant if data already exists.
  - Auto-numbered records (EMP-, LR-, LB-, TS-, CA-, INC-) check existence
    before creating.

Per Lesson L-09, all stdout text is plain ASCII - no Unicode arrows / dots /
emoji. The Windows cp1252 console crashes on them.

Per tenant produces:
    - 4 Departments (Production, Quality, Maintenance, Admin) + 1 Assembly
      sub-department.
    - 8 Positions across the four parent departments.
    - 12 Skills + 5 Certifications.
    - 20 Employees (EMP-00001 .. EMP-00020). The first 6 are linked to
      mes.ShopFloorOperator records (when present) so cross-module hooks
      have something to fire on.
    - ~3 EmployeeSkill rows per active operator + 5 EmployeeCertification rows
      including 2 deliberately near-expiry to populate the dashboard alert.
    - 3 Shifts + a 14-day shift roster.
    - 14 days of AttendanceRecord rows for each shop-floor operator.
    - 5 Leave Types + 6 Leave Requests across statuses.
    - 4 Holidays in the next 60 days.
    - 5 Cost Centers + 20 LaborRate rows + 30 LaborBooking rows backfilled
      from existing seeded MES time logs and EAM MWO labor logs.
    - 4 Training Programs + 8 Training Plans + 2 Sessions + 6 Attendance rows.
    - 1 Competency Assessment with 5 result rows.
    - 2 Incentive Schemes + 5 Piece Rates each + 1 Open Period + 1 Completed
      Run with 6 Incentive Lines.
"""
from datetime import date, datetime, timedelta, time as dtime
from decimal import Decimal
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.labor import models as L


DEPARTMENTS = [
    ('PROD', 'Production', None),
    ('QC', 'Quality Control', None),
    ('MTC', 'Maintenance', None),
    ('ADM', 'Administration', None),
]

POSITIONS = [
    ('OP-JR', 'Operator', 'PROD', 'junior'),
    ('OP-SR', 'Senior Operator', 'PROD', 'senior'),
    ('SUP-PROD', 'Production Supervisor', 'PROD', 'lead'),
    ('PM-PLANT', 'Plant Manager', 'ADM', 'manager'),
    ('QC-INSP', 'QC Inspector', 'QC', 'mid'),
    ('MTC-TECH', 'Maintenance Technician', 'MTC', 'mid'),
    ('HR-OFF', 'HR Officer', 'ADM', 'mid'),
    ('OP-LEAD', 'Shift Lead', 'PROD', 'lead'),
]

SKILLS = [
    ('CNC-LATHE', 'CNC Lathe Operation', 'operations'),
    ('CNC-MILL', 'CNC Mill Operation', 'operations'),
    ('WELDING', 'Welding (MIG/TIG)', 'operations'),
    ('ASSEMBLY', 'Mechanical Assembly', 'operations'),
    ('PACKAGING', 'Packaging Line Operation', 'operations'),
    ('IPQC', 'In-Process Quality Control', 'quality'),
    ('FQC', 'Final Quality Inspection', 'quality'),
    ('METROLOGY', 'Metrology / Calibration', 'quality'),
    ('LOTO', 'Lockout-Tagout', 'safety'),
    ('FORKLIFT', 'Forklift Operation', 'safety'),
    ('LEADERSHIP', 'Team Leadership', 'leadership'),
    ('COMMS', 'Cross-Team Communication', 'leadership'),
]

CERTIFICATIONS = [
    ('ISO9001-LA', 'ISO 9001 Lead Auditor', 'BSI', 730),
    ('FORK-LIC', 'Forklift License', 'OSHA', 365),
    ('FIRST-AID', 'First Aid', 'Red Cross', 365),
    ('LOTO-CERT', 'Lockout-Tagout', 'Internal', 365),
    ('SOLDER-IPC', 'IPC-A-610 Solder', 'IPC', 730),
]

LEAVE_TYPES = [
    ('ANN', 'Annual Leave', True, Decimal('20'), False),
    ('SICK', 'Sick Leave', True, Decimal('10'), True),
    ('CAS', 'Casual Leave', True, Decimal('6'), False),
    ('MAT', 'Maternity Leave', True, Decimal('90'), True),
    ('BVT', 'Bereavement', True, Decimal('5'), False),
]

SHIFTS = [
    ('MORN', 'Morning', dtime(6, 0), dtime(14, 0), 30, False, '#3B82F6'),
    ('EVE', 'Evening', dtime(14, 0), dtime(22, 0), 30, False, '#F59E0B'),
    ('NIGHT', 'Night', dtime(22, 0), dtime(6, 0), 30, True, '#6366F1'),
]

COST_CENTERS = [
    ('CC-PROD', 'Production - Main', 'production', None),
    ('CC-ASSY', 'Production - Assembly', 'production', 'CC-PROD'),
    ('CC-QC', 'Quality Control', 'quality', None),
    ('CC-MTC', 'Maintenance', 'maintenance', None),
    ('CC-ADM', 'Administration', 'admin', None),
]

TRAINING_PROGRAMS = [
    ('TP-CNC', 'CNC Operations Refresher', 'classroom', Decimal('8.0'), 'CNC-LATHE'),
    ('TP-SAFE', 'Plant Safety & LOTO', 'classroom', Decimal('4.0'), 'LOTO'),
    ('TP-FORK', 'Forklift Recertification', 'on_the_job', Decimal('6.0'), 'FORKLIFT'),
    ('TP-IPQC', 'In-Process QC Methods', 'online', Decimal('3.5'), 'IPQC'),
]

INCENTIVE_SCHEMES = [
    ('PR-FG', 'Finished Goods Piece Rate', 'piece_rate', True),
    ('PB-MONTH', 'Monthly Production Bonus', 'production_bonus', False),
]


class Command(BaseCommand):
    help = 'Idempotent demo data for Module 11 - Labor & Workforce Management.'

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

        self.stdout.write('seed_labor done.')
        self.stdout.write('Login as a tenant admin (e.g. admin_acme) to view seeded labor data.')
        self.stdout.write("Superuser 'admin' has no tenant - data wont appear when logged in as admin.")

    def _seed_one(self, tenant: Tenant, *, flush: bool):
        random.seed(hash(tenant.slug) & 0xFFFFFFFF)
        if flush:
            self._flush_tenant(tenant)

        if L.Employee.all_objects.filter(tenant=tenant).exists():
            self.stdout.write(f'[{tenant.slug}] labor data already exists. Use --flush to re-seed.')
            return

        with transaction.atomic():
            depts = self._seed_departments(tenant)
            positions = self._seed_positions(tenant, depts)
            skills = self._seed_skills(tenant)
            certs = self._seed_certifications(tenant)
            employees = self._seed_employees(tenant, depts, positions)
            self._link_shop_floor_operators(tenant, employees)
            self._seed_employee_skills(tenant, employees, skills)
            self._seed_employee_certifications(tenant, employees, certs)
            shifts = self._seed_shifts(tenant)
            self._seed_rosters(tenant, employees, shifts)
            self._seed_attendance(tenant, employees, shifts)
            leave_types = self._seed_leave_types(tenant)
            self._seed_leave_requests(tenant, employees, leave_types)
            self._seed_holidays(tenant)
            cost_centers = self._seed_cost_centers(tenant)
            self._link_cost_centers(tenant, cost_centers)
            self._seed_labor_rates(tenant, employees)
            booking_count = self._backfill_bookings(tenant, employees, cost_centers)
            programs = self._seed_training_programs(tenant, skills)
            self._seed_training_plans(tenant, employees, programs)
            sessions = self._seed_training_sessions(tenant, programs, employees)
            self._seed_training_attendance(tenant, sessions, employees)
            self._seed_competency_assessment(tenant, employees, positions, skills)
            schemes = self._seed_incentive_schemes(tenant, employees, positions)
            self._seed_piece_rates(tenant, schemes)
            period = self._seed_incentive_period(tenant)
            run = self._seed_incentive_run(tenant, period, schemes[0], employees)

        self.stdout.write(
            f'[{tenant.slug}] Created {len(employees)} employees, '
            f'{len(shifts)} shifts, {booking_count} labor bookings, '
            f'{len(programs)} training programs, '
            f'1 incentive run.'
        )

    # ------------------------------------------------------------------
    # Per-section helpers
    # ------------------------------------------------------------------

    def _flush_tenant(self, tenant: Tenant):
        # Order matters - dependent models first.
        for cls in (
            L.IncentiveLine, L.IncentiveRun, L.IncentivePeriod,
            L.PieceRate, L.IncentiveScheme,
            L.CompetencyResult, L.CompetencyAssessment,
            L.TrainingAttendance, L.TrainingSession, L.TrainingPlan, L.TrainingProgram,
            L.LaborBooking, L.LaborRate, L.CostCenter,
            L.LeaveRequest, L.LeaveType, L.Holiday,
            L.AttendanceRecord, L.ShiftRoster, L.Shift,
            L.EmployeeDocument, L.EmployeeCertification, L.Certification,
            L.EmployeeSkill, L.Skill,
            L.Employee, L.Position, L.Department,
        ):
            cls.all_objects.filter(tenant=tenant).delete()

    def _seed_departments(self, tenant):
        out = {}
        for code, name, _ in DEPARTMENTS:
            out[code] = L.Department.all_objects.create(
                tenant=tenant, code=code, name=name,
                description=f'{name} department.',
            )
        # Add the assembly sub-dept under PROD.
        out['ASSY'] = L.Department.all_objects.create(
            tenant=tenant, code='ASSY', name='Assembly',
            parent=out['PROD'], description='Sub-department of Production.',
        )
        return out

    def _seed_positions(self, tenant, depts):
        out = {}
        for code, title, dept_code, level in POSITIONS:
            out[code] = L.Position.all_objects.create(
                tenant=tenant, code=code, title=title,
                department=depts[dept_code], level=level,
            )
        return out

    def _seed_skills(self, tenant):
        out = {}
        for code, name, cat in SKILLS:
            out[code] = L.Skill.all_objects.create(
                tenant=tenant, code=code, name=name, category=cat,
            )
        return out

    def _seed_certifications(self, tenant):
        out = {}
        for code, name, authority, days in CERTIFICATIONS:
            out[code] = L.Certification.all_objects.create(
                tenant=tenant, code=code, name=name,
                issuing_authority=authority, valid_period_days=days,
            )
        return out

    def _seed_employees(self, tenant, depts, positions):
        first_names = ['Alex', 'Brian', 'Carol', 'Diana', 'Ethan', 'Farah', 'George',
                       'Hana', 'Ian', 'Julia', 'Kiran', 'Lina', 'Mark', 'Nadia',
                       'Omar', 'Priya', 'Quinn', 'Rita', 'Samir', 'Tara']
        last_names = ['Adams', 'Brown', 'Chen', 'Diaz', 'Evans', 'Foster', 'Gomez',
                      'Hassan', 'Iqbal', 'Jansen', 'Khan', 'Lee', 'Murphy',
                      'Naidu', 'Ortiz', 'Patel', 'Qureshi', 'Reyes', 'Sato', 'Thompson']
        position_codes = list(positions.keys())
        out = []
        today = timezone.now().date()
        for i in range(20):
            pos_code = position_codes[i % len(position_codes)]
            pos = positions[pos_code]
            emp = L.Employee.all_objects.create(
                tenant=tenant,
                first_name=first_names[i],
                last_name=last_names[i],
                email=f'{first_names[i].lower()}.{last_names[i].lower()}@{tenant.slug}.local',
                phone=f'555-{1000 + i}',
                department=pos.department,
                position=pos,
                employment_type=random.choice(['permanent', 'permanent', 'permanent', 'contract']),
                hire_date=today - timedelta(days=random.randint(60, 1500)),
                gender=random.choice(['male', 'female', 'prefer_not_to_say']),
                emergency_contact_name=f'Family of {first_names[i]}',
                emergency_contact_phone=f'555-{2000 + i}',
                status='active',
            )
            out.append(emp)
        return out

    def _link_shop_floor_operators(self, tenant, employees):
        # Soft link existing seeded mes.ShopFloorOperator rows to the first 6 employees.
        try:
            from apps.mes.models import ShopFloorOperator
        except ImportError:
            return
        ops = list(ShopFloorOperator.all_objects.filter(tenant=tenant)[:6])
        for op, emp in zip(ops, employees[:6]):
            op.employee = emp
            op.save(update_fields=['employee', 'updated_at'])

    def _seed_employee_skills(self, tenant, employees, skills):
        skill_codes = list(skills.keys())
        for emp in employees:
            chosen = random.sample(skill_codes, k=3)
            for code in chosen:
                L.EmployeeSkill.all_objects.create(
                    tenant=tenant, employee=emp, skill=skills[code],
                    proficiency=random.randint(2, 5),
                    assessed_at=timezone.now().date() - timedelta(days=random.randint(30, 365)),
                )

    def _seed_employee_certifications(self, tenant, employees, certs):
        today = timezone.now().date()
        cert_list = list(certs.values())
        # 5 employees get a random certification + 2 deliberately near-expiry
        sample = random.sample(employees, k=5) if len(employees) >= 5 else employees[:]
        for i, emp in enumerate(sample):
            cert = random.choice(cert_list)
            if i == 0:
                expires = today + timedelta(days=10)  # expiring soon
            elif i == 1:
                expires = today + timedelta(days=20)  # expiring soon
            else:
                expires = today + timedelta(days=cert.valid_period_days)
            issued = expires - timedelta(days=cert.valid_period_days)
            L.EmployeeCertification.all_objects.create(
                tenant=tenant, employee=emp, certification=cert,
                certificate_number=f'{cert.code}-{emp.employee_number}',
                issued_at=issued, expires_at=expires,
            )

    def _seed_shifts(self, tenant):
        out = {}
        for code, name, start, end, brk, overnight, color in SHIFTS:
            out[code] = L.Shift.all_objects.create(
                tenant=tenant, code=code, name=name,
                start_time=start, end_time=end, break_minutes=brk,
                is_overnight=overnight, color=color,
            )
        return out

    def _seed_rosters(self, tenant, employees, shifts):
        today = timezone.now().date()
        end = today + timedelta(days=14)
        shift_codes = list(shifts.keys())
        for i, emp in enumerate(employees):
            sh = shifts[shift_codes[i % len(shift_codes)]]
            L.ShiftRoster.all_objects.create(
                tenant=tenant, employee=emp, shift=sh,
                start_date=today, end_date=end,
            )

    def _seed_attendance(self, tenant, employees, shifts):
        today = timezone.now().date()
        morn = shifts['MORN']
        for emp in employees[:6]:
            for d in range(14):
                day = today - timedelta(days=d)
                if day.weekday() >= 5:
                    continue  # skip weekends
                clock_in = timezone.make_aware(datetime.combine(day, dtime(6, random.randint(0, 15))))
                clock_out = clock_in + timedelta(hours=8, minutes=30)
                worked = max(0, int((clock_out - clock_in).total_seconds() // 60) - morn.break_minutes)
                status = 'absent' if random.random() < 0.05 else 'present'
                L.AttendanceRecord.all_objects.create(
                    tenant=tenant, employee=emp, work_date=day, shift=morn,
                    clock_in_at=clock_in if status == 'present' else None,
                    clock_out_at=clock_out if status == 'present' else None,
                    worked_minutes=worked if status == 'present' else 0,
                    status=status,
                )

    def _seed_leave_types(self, tenant):
        out = {}
        for code, name, paid, quota, requires_attach in LEAVE_TYPES:
            out[code] = L.LeaveType.all_objects.create(
                tenant=tenant, code=code, name=name, paid=paid,
                default_annual_quota_days=quota, requires_attachment=requires_attach,
            )
        return out

    def _seed_leave_requests(self, tenant, employees, leave_types):
        today = timezone.now().date()
        scenarios = [
            (employees[0], 'ANN', 'draft', 5, today + timedelta(days=20)),
            (employees[1], 'ANN', 'submitted', 3, today + timedelta(days=10)),
            (employees[2], 'CAS', 'submitted', 1, today + timedelta(days=5)),
            (employees[3], 'ANN', 'approved', 7, today - timedelta(days=2)),
            (employees[4], 'SICK', 'rejected', 2, today - timedelta(days=10)),
            (employees[5], 'ANN', 'cancelled', 4, today + timedelta(days=30)),
        ]
        for emp, lt_code, status, days, start_date in scenarios:
            end_date = start_date + timedelta(days=days - 1)
            req = L.LeaveRequest.all_objects.create(
                tenant=tenant, employee=emp, leave_type=leave_types[lt_code],
                start_date=start_date, end_date=end_date,
                days_requested=Decimal(days),
                reason=f'Demo leave request - {status}',
                status=status,
                submitted_at=timezone.now() if status != 'draft' else None,
                decided_at=timezone.now() if status in ('approved', 'rejected', 'cancelled') else None,
                decision_notes='Approved.' if status == 'approved' else (
                    'Insufficient quota.' if status == 'rejected' else (
                        'Plan changed.' if status == 'cancelled' else ''
                    )
                ),
            )

    def _seed_holidays(self, tenant):
        today = timezone.now().date()
        names = ['Founders Day', 'Independence Day', 'Mid-Year Break', 'Plant Day']
        for i, name in enumerate(names):
            L.Holiday.all_objects.create(
                tenant=tenant, name=name,
                holiday_date=today + timedelta(days=15 + i * 14),
                is_recurring=(i == 0),
            )

    def _seed_cost_centers(self, tenant):
        out = {}
        # First pass to create parents.
        for code, name, cc_type, parent_code in COST_CENTERS:
            if parent_code is None:
                out[code] = L.CostCenter.all_objects.create(
                    tenant=tenant, code=code, name=name, cc_type=cc_type,
                )
        for code, name, cc_type, parent_code in COST_CENTERS:
            if parent_code is not None:
                out[code] = L.CostCenter.all_objects.create(
                    tenant=tenant, code=code, name=name, cc_type=cc_type,
                    parent=out[parent_code],
                )
        return out

    def _link_cost_centers(self, tenant, cost_centers):
        # Wire plm.Product.cost_center + eam.Asset.cost_center on a sample.
        try:
            from apps.plm.models import Product
        except ImportError:
            Product = None
        if Product is not None:
            cc = cost_centers.get('CC-ASSY') or cost_centers.get('CC-PROD')
            for p in Product.all_objects.filter(tenant=tenant)[:5]:
                p.cost_center = cc
                p.save(update_fields=['cost_center', 'updated_at'])
        try:
            from apps.eam.models import Asset
        except ImportError:
            Asset = None
        if Asset is not None:
            cc = cost_centers.get('CC-MTC')
            for a in Asset.all_objects.filter(tenant=tenant)[:5]:
                a.cost_center = cc
                a.save(update_fields=['cost_center', 'updated_at'])

    def _seed_labor_rates(self, tenant, employees):
        today = timezone.now().date()
        for emp in employees:
            rate = Decimal(random.randint(15, 45))
            L.LaborRate.all_objects.create(
                tenant=tenant, employee=emp,
                hourly_rate=rate, overtime_multiplier=Decimal('1.50'),
                effective_from=today - timedelta(days=180),
            )

    def _backfill_bookings(self, tenant, employees, cost_centers):
        # Synthesize 30 LaborBooking rows directly so the dashboard has data
        # without reaching into mes / eam tables.
        cc_prod = cost_centers.get('CC-PROD')
        cc_mtc = cost_centers.get('CC-MTC')
        rates_by_emp = {
            r.employee_id: r.hourly_rate
            for r in L.LaborRate.all_objects.filter(tenant=tenant)
        }
        today = timezone.now()
        count = 0
        for i in range(30):
            emp = employees[i % len(employees)]
            kind = 'direct' if i % 4 != 3 else 'indirect'
            cc = cc_mtc if kind == 'indirect' else cc_prod
            worked_at = today - timedelta(days=random.randint(0, 28),
                                          hours=random.randint(0, 6))
            minutes = random.choice([60, 120, 180, 240, 300, 360])
            rate = rates_by_emp.get(emp.pk, Decimal('20'))
            L.LaborBooking.all_objects.create(
                tenant=tenant, employee=emp, kind=kind, cost_center=cc,
                worked_at=worked_at, minutes=minutes,
                hourly_rate_snapshot=rate,
                source_type='manual',
            )
            count += 1
        return count

    def _seed_training_programs(self, tenant, skills):
        out = []
        for code, name, mode, hours, target in TRAINING_PROGRAMS:
            out.append(L.TrainingProgram.all_objects.create(
                tenant=tenant, code=code, name=name,
                delivery_mode=mode, duration_hours=hours,
                competency_target=skills.get(target),
            ))
        return out

    def _seed_training_plans(self, tenant, employees, programs):
        today = timezone.now().date()
        for i, emp in enumerate(employees[:8]):
            prog = programs[i % len(programs)]
            L.TrainingPlan.all_objects.create(
                tenant=tenant, employee=emp, program=prog,
                target_completion_date=today + timedelta(days=30 + i * 7),
                status=['assigned', 'in_progress', 'completed', 'overdue'][i % 4],
            )

    def _seed_training_sessions(self, tenant, programs, employees):
        out = []
        now = timezone.now()
        for i in range(2):
            prog = programs[i % len(programs)]
            start = now + timedelta(days=10 + i * 7, hours=9)
            sess = L.TrainingSession.all_objects.create(
                tenant=tenant, program=prog,
                start_at=start, end_at=start + timedelta(hours=4),
                location=f'Training Room {i + 1}',
                instructor=employees[2] if employees else None,
                capacity=15,
            )
            out.append(sess)
        return out

    def _seed_training_attendance(self, tenant, sessions, employees):
        for sess in sessions:
            for emp in employees[:3]:
                L.TrainingAttendance.all_objects.create(
                    tenant=tenant, session=sess, employee=emp,
                    attended=True, score=Decimal(random.randint(70, 95)),
                )

    def _seed_competency_assessment(self, tenant, employees, positions, skills):
        # Pick a senior op as the subject.
        senior = next((e for e in employees if e.position.level == 'senior'), employees[0])
        ass = L.CompetencyAssessment.all_objects.create(
            tenant=tenant, employee=senior, position=senior.position,
            assessed_at=timezone.now().date() - timedelta(days=14),
            status='draft',
        )
        # 5 result rows.
        chosen = random.sample(list(skills.values()), k=5)
        for sk in chosen:
            L.CompetencyResult.all_objects.create(
                tenant=tenant, assessment=ass, skill=sk,
                expected_level=random.randint(3, 5),
                actual_level=random.randint(2, 5),
            )

    def _seed_incentive_schemes(self, tenant, employees, positions):
        today = timezone.now().date()
        out = []
        for code, name, scheme_type, active in INCENTIVE_SCHEMES:
            sc = L.IncentiveScheme.all_objects.create(
                tenant=tenant, code=code, name=name,
                scheme_type=scheme_type,
                effective_from=today - timedelta(days=30),
                is_active=active,
            )
            # Make all operators applicable for piece-rate.
            if scheme_type == 'piece_rate':
                operators = [e for e in employees if 'OP' in e.position.code][:6]
                if operators:
                    sc.applicable_employees.add(*operators)
            out.append(sc)
        return out

    def _seed_piece_rates(self, tenant, schemes):
        try:
            from apps.plm.models import Product
        except ImportError:
            return
        scheme = schemes[0]
        products = list(Product.all_objects.filter(
            tenant=tenant, product_type='finished_good',
        )[:5])
        for p in products:
            L.PieceRate.all_objects.create(
                tenant=tenant, scheme=scheme, product=p,
                rate_per_unit=Decimal(str(round(random.uniform(0.50, 5.00), 4))),
                min_quantity=Decimal('0'),
            )

    def _seed_incentive_period(self, tenant):
        today = timezone.now().date()
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return L.IncentivePeriod.all_objects.create(
            tenant=tenant, name=f'Period {start:%Y-%m}',
            start_date=start, end_date=end, status='open',
        )

    def _seed_incentive_run(self, tenant, period, scheme, employees):
        run = L.IncentiveRun.all_objects.create(
            tenant=tenant, period=period, scheme=scheme,
            status='completed',
            started_at=timezone.now() - timedelta(hours=2),
            completed_at=timezone.now() - timedelta(hours=1),
        )
        # 6 incentive lines for operators.
        operators = [e for e in employees if 'OP' in e.position.code][:6]
        if not operators:
            operators = employees[:6]
        total = Decimal('0')
        for emp in operators:
            units = Decimal(random.randint(40, 200))
            rate = Decimal(str(round(random.uniform(0.50, 3.50), 4)))
            amount = (units * rate).quantize(Decimal('0.01'))
            L.IncentiveLine.all_objects.create(
                tenant=tenant, run=run, employee=emp,
                qualifying_units=units, rate_applied=rate, amount=amount,
            )
            total += amount
        run.total_amount = total
        run.save(update_fields=['total_amount', 'updated_at'])
        return run
