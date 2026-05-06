"""Model invariants, auto-numbering, decimal validators, denorm computations."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.labor import models as L


# ---------- auto-numbering ----------

class TestAutoNumbering:
    @pytest.mark.django_db
    def test_employee_number_starts_at_one(self, employee):
        assert employee.employee_number == 'EMP-00001'

    @pytest.mark.django_db
    def test_employee_number_increments(self, acme, department, position):
        L.Employee.objects.create(
            tenant=acme, first_name='A', last_name='1',
            department=department, position=position, hire_date=date.today(),
        )
        e2 = L.Employee.objects.create(
            tenant=acme, first_name='B', last_name='2',
            department=department, position=position, hire_date=date.today(),
        )
        assert e2.employee_number == 'EMP-00002'

    @pytest.mark.django_db
    def test_leave_request_number(self, employee, leave_type):
        lr = L.LeaveRequest.objects.create(
            tenant=employee.tenant, employee=employee, leave_type=leave_type,
            start_date=date.today(), end_date=date.today() + timedelta(days=2),
            days_requested=Decimal('3'),
        )
        assert lr.request_number.startswith('LR-')

    @pytest.mark.django_db
    def test_labor_booking_number(self, acme, employee, cost_center):
        b = L.LaborBooking.objects.create(
            tenant=acme, employee=employee, cost_center=cost_center,
            kind='direct', worked_at=timezone.now(), minutes=60,
            hourly_rate_snapshot=Decimal('20.00'),
        )
        assert b.booking_number == 'LB-00001'

    @pytest.mark.django_db
    def test_training_session_number(self, training_program):
        s = L.TrainingSession.objects.create(
            tenant=training_program.tenant, program=training_program,
            start_at=timezone.now(), end_at=timezone.now() + timedelta(hours=2),
            capacity=10,
        )
        assert s.session_number == 'TS-00001'

    @pytest.mark.django_db
    def test_competency_assessment_number(self, employee, position):
        ca = L.CompetencyAssessment.objects.create(
            tenant=employee.tenant, employee=employee, position=position,
            assessed_at=date.today(),
        )
        assert ca.assessment_number == 'CA-00001'

    @pytest.mark.django_db
    def test_incentive_run_number(self, incentive_period, incentive_scheme):
        r = L.IncentiveRun.objects.create(
            tenant=incentive_period.tenant, period=incentive_period, scheme=incentive_scheme,
        )
        assert r.run_number == 'INC-00001'


# ---------- denorm computations ----------

class TestDenorms:
    @pytest.mark.django_db
    def test_labor_booking_total_cost(self, acme, employee, cost_center):
        b = L.LaborBooking.objects.create(
            tenant=acme, employee=employee, cost_center=cost_center,
            kind='direct', worked_at=timezone.now(), minutes=120,
            hourly_rate_snapshot=Decimal('30.00'),
        )
        # 120 min * 30/hr / 60 = 60.00
        assert b.total_cost == Decimal('60.00')

    @pytest.mark.django_db
    def test_incentive_line_amount(self, acme, employee, incentive_period, incentive_scheme):
        run = L.IncentiveRun.objects.create(
            tenant=acme, period=incentive_period, scheme=incentive_scheme,
        )
        line = L.IncentiveLine.objects.create(
            tenant=acme, run=run, employee=employee,
            qualifying_units=Decimal('100'), rate_applied=Decimal('1.5000'),
        )
        assert line.amount == Decimal('150.00')

    @pytest.mark.django_db
    def test_competency_result_gap(self, employee, position, skill):
        ca = L.CompetencyAssessment.objects.create(
            tenant=employee.tenant, employee=employee, position=position,
            assessed_at=date.today(),
        )
        r = L.CompetencyResult.objects.create(
            tenant=employee.tenant, assessment=ca, skill=skill,
            expected_level=4, actual_level=2,
        )
        assert r.gap == 2

    @pytest.mark.django_db
    def test_employee_certification_expiring_soon(self, employee, certification):
        ec = L.EmployeeCertification.objects.create(
            tenant=employee.tenant, employee=employee, certification=certification,
            certificate_number='C-1', issued_at=date.today() - timedelta(days=350),
            expires_at=date.today() + timedelta(days=15),
        )
        assert ec.status == 'expiring_soon'

    @pytest.mark.django_db
    def test_employee_certification_expired(self, employee, certification):
        ec = L.EmployeeCertification.objects.create(
            tenant=employee.tenant, employee=employee, certification=certification,
            certificate_number='C-2', issued_at=date.today() - timedelta(days=400),
            expires_at=date.today() - timedelta(days=5),
        )
        assert ec.status == 'expired'

    @pytest.mark.django_db
    def test_employee_certification_active(self, employee, certification):
        ec = L.EmployeeCertification.objects.create(
            tenant=employee.tenant, employee=employee, certification=certification,
            certificate_number='C-3', issued_at=date.today(),
            expires_at=date.today() + timedelta(days=300),
        )
        assert ec.status == 'active'


# ---------- decimal validators (L-02) ----------

class TestDecimalValidators:
    @pytest.mark.django_db
    def test_labor_rate_must_be_positive(self, acme, employee):
        rate = L.LaborRate(
            tenant=acme, employee=employee, hourly_rate=Decimal('0.00'),
            overtime_multiplier=Decimal('1.50'),
            effective_from=date.today(),
        )
        with pytest.raises(ValidationError):
            rate.full_clean()

    @pytest.mark.django_db
    def test_overtime_multiplier_capped_at_three(self, acme, employee):
        rate = L.LaborRate(
            tenant=acme, employee=employee, hourly_rate=Decimal('20'),
            overtime_multiplier=Decimal('5.00'),
            effective_from=date.today(),
        )
        with pytest.raises(ValidationError):
            rate.full_clean()

    @pytest.mark.django_db
    def test_employee_skill_proficiency_range(self, acme, employee, skill):
        es = L.EmployeeSkill(
            tenant=acme, employee=employee, skill=skill, proficiency=6,
        )
        with pytest.raises(ValidationError):
            es.full_clean()

    @pytest.mark.django_db
    def test_training_attendance_score_clamped(self, training_program, employee):
        sess = L.TrainingSession.objects.create(
            tenant=employee.tenant, program=training_program,
            start_at=timezone.now(), end_at=timezone.now() + timedelta(hours=2),
            capacity=10,
        )
        att = L.TrainingAttendance(
            tenant=employee.tenant, session=sess, employee=employee,
            attended=True, score=Decimal('150.00'),
        )
        with pytest.raises(ValidationError):
            att.full_clean()

    @pytest.mark.django_db
    def test_leave_days_minimum_half(self, employee, leave_type):
        lr = L.LeaveRequest(
            tenant=employee.tenant, employee=employee, leave_type=leave_type,
            start_date=date.today(), end_date=date.today(),
            days_requested=Decimal('0.0'),
        )
        with pytest.raises(ValidationError):
            lr.full_clean()


# ---------- L-01 unique constraints (model-level) ----------

class TestUniqueTogether:
    @pytest.mark.django_db
    def test_unique_department_code_per_tenant(self, acme, globex):
        L.Department.objects.create(tenant=acme, code='HR', name='HR1')
        # globex can also have HR
        L.Department.objects.create(tenant=globex, code='HR', name='HR2')
        # but acme cannot create another HR
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            L.Department.objects.create(tenant=acme, code='HR', name='HR-dup')

    @pytest.mark.django_db
    def test_unique_employee_skill(self, employee, skill):
        L.EmployeeSkill.objects.create(
            tenant=employee.tenant, employee=employee, skill=skill, proficiency=3,
        )
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            L.EmployeeSkill.objects.create(
                tenant=employee.tenant, employee=employee, skill=skill, proficiency=5,
            )
