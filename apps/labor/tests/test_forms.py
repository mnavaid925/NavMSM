"""Form-level validation - L-01 unique_together, L-02 decimal bounds, L-14 per-workflow."""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from apps.labor import forms, models as L


@pytest.mark.django_db
class TestL01UniqueTogether:
    def test_department_code_dupe_blocked(self, acme):
        L.Department.objects.create(tenant=acme, code='HR', name='HR1')
        f = forms.DepartmentForm(
            data={'code': 'HR', 'name': 'HR2', 'is_active': True},
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'code' in f.errors

    def test_skill_code_dupe_blocked(self, acme):
        L.Skill.objects.create(tenant=acme, code='X', name='X', category='operations')
        f = forms.SkillForm(
            data={'code': 'X', 'name': 'X2', 'category': 'operations', 'is_active': True},
            tenant=acme,
        )
        assert not f.is_valid()

    def test_holiday_date_dupe_blocked(self, acme):
        d = date.today() + timedelta(days=10)
        L.Holiday.objects.create(tenant=acme, holiday_date=d, name='X')
        f = forms.HolidayForm(
            data={'holiday_date': d.isoformat(), 'name': 'Y'},
            tenant=acme,
        )
        assert not f.is_valid()

    def test_employee_skill_dedup_blocked(self, acme, employee, skill):
        L.EmployeeSkill.objects.create(
            tenant=acme, employee=employee, skill=skill, proficiency=3,
        )
        f = forms.EmployeeSkillForm(
            data={'skill': skill.pk, 'proficiency': 4},
            tenant=acme, employee=employee,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestL02DecimalBounds:
    def test_labor_rate_must_be_positive(self, acme, employee):
        f = forms.LaborRateForm(
            data={
                'employee': employee.pk,
                'hourly_rate': '0',
                'overtime_multiplier': '1.5',
                'effective_from': date.today().isoformat(),
            },
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'hourly_rate' in f.errors

    def test_labor_rate_overtime_capped(self, acme, employee):
        f = forms.LaborRateForm(
            data={
                'employee': employee.pk,
                'hourly_rate': '20',
                'overtime_multiplier': '5.0',
                'effective_from': date.today().isoformat(),
            },
            tenant=acme,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestL14PerWorkflowRequired:
    def test_leave_reject_requires_notes(self):
        f = forms.LeaveDecisionForm(data={'decision_notes': ''}, mode='reject')
        assert not f.is_valid()

    def test_leave_reject_with_notes_ok(self):
        f = forms.LeaveDecisionForm(data={'decision_notes': 'reason'}, mode='reject')
        assert f.is_valid()

    def test_cancel_approved_requires_notes(self):
        f = forms.LeaveDecisionForm(
            data={'decision_notes': ''}, mode='cancel', was_approved=True,
        )
        assert not f.is_valid()

    def test_cancel_draft_no_notes_required(self):
        f = forms.LeaveDecisionForm(
            data={'decision_notes': ''}, mode='cancel', was_approved=False,
        )
        assert f.is_valid()

    def test_training_plan_waive_requires_notes(self):
        f = forms.TrainingPlanWaiveForm(data={'notes': ''})
        assert not f.is_valid()

    def test_competency_complete_requires_results(self):
        f = forms.CompetencyAssessmentCompleteForm(data={}, has_results=False)
        assert not f.is_valid()
        f2 = forms.CompetencyAssessmentCompleteForm(data={}, has_results=True)
        assert f2.is_valid()


@pytest.mark.django_db
class TestPieceRateValidation:
    def test_piece_rate_requires_product_or_operation(self, acme, incentive_scheme):
        f = forms.PieceRateForm(
            data={
                'product': '', 'operation': '',
                'rate_per_unit': '1.0',
                'min_quantity': '0',
            },
            tenant=acme, scheme=incentive_scheme,
        )
        assert not f.is_valid()

    def test_piece_rate_max_must_exceed_min(self, acme, incentive_scheme):
        # plm.Product import to avoid circular: make a minimal product directly
        from apps.plm.models import Product
        p = Product.objects.create(
            tenant=acme, sku='X1', name='X', product_type='finished_good',
            unit_of_measure='ea', status='active',
        )
        f = forms.PieceRateForm(
            data={
                'product': p.pk, 'operation': '',
                'rate_per_unit': '1.0',
                'min_quantity': '100',
                'max_quantity': '50',
            },
            tenant=acme, scheme=incentive_scheme,
        )
        assert not f.is_valid()


@pytest.mark.django_db
class TestLeaveRequestForm:
    def test_end_before_start_blocked(self, acme, employee, leave_type):
        f = forms.LeaveRequestForm(
            data={
                'employee': employee.pk, 'leave_type': leave_type.pk,
                'start_date': '2026-05-10', 'end_date': '2026-05-01',
                'days_requested': '1',
                'reason': 'x',
            },
            tenant=acme,
        )
        assert not f.is_valid()

    def test_attachment_required_when_type_demands(self, acme, employee):
        lt = L.LeaveType.objects.create(
            tenant=acme, code='MED', name='Medical',
            paid=True, requires_attachment=True,
        )
        f = forms.LeaveRequestForm(
            data={
                'employee': employee.pk, 'leave_type': lt.pk,
                'start_date': '2026-05-01', 'end_date': '2026-05-02',
                'days_requested': '2',
                'reason': 'x',
            },
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'attachment' in f.errors
