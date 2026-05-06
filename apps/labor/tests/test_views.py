"""Smoke tests - dashboard + every list / detail / form GET succeeds for an admin."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestSmokeGet:
    @pytest.mark.parametrize('name', [
        'index', 'department_list', 'position_list', 'employee_list',
        'skill_list', 'skills_matrix', 'certification_list',
        'shift_list', 'roster_list', 'attendance_list',
        'leave_type_list', 'leave_request_list', 'holiday_list',
        'cost_center_list', 'labor_rate_list',
        'labor_booking_list', 'labor_booking_summary',
        'program_list', 'plan_list', 'session_list',
        'assessment_list',
        'scheme_list', 'period_list', 'run_list',
    ])
    def test_list_pages(self, admin_client, name):
        resp = admin_client.get(reverse(f'labor:{name}'))
        assert resp.status_code == 200, name

    def test_employee_detail(self, admin_client, employee):
        resp = admin_client.get(reverse('labor:employee_detail', kwargs={'pk': employee.pk}))
        assert resp.status_code == 200

    def test_employee_create_get(self, admin_client):
        resp = admin_client.get(reverse('labor:employee_create'))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestLeaveWorkflow:
    def test_submit_then_approve(self, admin_client, acme_admin, employee, leave_type):
        from apps.labor import models as L
        lr = L.LeaveRequest.objects.create(
            tenant=acme_admin.tenant, employee=employee, leave_type=leave_type,
            start_date=date.today(), end_date=date.today() + timedelta(days=2),
            days_requested=Decimal('3'),
        )
        # Submit (any tenant user)
        resp = admin_client.post(reverse('labor:leave_request_submit', kwargs={'pk': lr.pk}))
        assert resp.status_code == 302
        lr.refresh_from_db()
        assert lr.status == 'submitted'
        # Approve (admin)
        resp = admin_client.post(reverse('labor:leave_request_approve', kwargs={'pk': lr.pk}))
        assert resp.status_code == 302
        lr.refresh_from_db()
        assert lr.status == 'approved'

    def test_reject_requires_notes(self, admin_client, acme_admin, employee, leave_type):
        from apps.labor import models as L
        lr = L.LeaveRequest.objects.create(
            tenant=acme_admin.tenant, employee=employee, leave_type=leave_type,
            start_date=date.today(), end_date=date.today() + timedelta(days=1),
            days_requested=Decimal('2'),
            status='submitted',
        )
        # Empty notes should re-render the form, status unchanged
        resp = admin_client.post(
            reverse('labor:leave_request_reject', kwargs={'pk': lr.pk}),
            data={'decision_notes': ''},
        )
        assert resp.status_code == 200
        lr.refresh_from_db()
        assert lr.status == 'submitted'
        # With notes - status flips to rejected
        resp = admin_client.post(
            reverse('labor:leave_request_reject', kwargs={'pk': lr.pk}),
            data={'decision_notes': 'denied'},
        )
        assert resp.status_code == 302
        lr.refresh_from_db()
        assert lr.status == 'rejected'


@pytest.mark.django_db
class TestEmployeeWorkflow:
    def test_terminate_then_reactivate(self, admin_client, employee):
        # Terminate
        resp = admin_client.post(reverse('labor:employee_terminate', kwargs={'pk': employee.pk}))
        assert resp.status_code == 302
        employee.refresh_from_db()
        assert employee.status == 'terminated'
        assert employee.termination_date is not None
        # Reactivate
        resp = admin_client.post(reverse('labor:employee_reactivate', kwargs={'pk': employee.pk}))
        assert resp.status_code == 302
        employee.refresh_from_db()
        assert employee.status == 'active'
        assert employee.termination_date is None
