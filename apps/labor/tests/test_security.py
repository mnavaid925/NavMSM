"""RBAC + multi-tenant IDOR + anonymous-redirect coverage."""
from datetime import date, timedelta

import pytest
from django.urls import reverse


ADMIN_ONLY_URLS = [
    ('department_create', {}),
    ('position_create', {}),
    ('employee_create', {}),
    ('skill_create', {}),
    ('certification_create', {}),
    ('shift_create', {}),
    ('roster_create', {}),
    ('attendance_create', {}),
    ('leave_type_create', {}),
    ('holiday_create', {}),
    ('cost_center_create', {}),
    ('labor_rate_create', {}),
    ('labor_booking_create', {}),
    ('program_create', {}),
    ('plan_create', {}),
    ('session_create', {}),
    ('assessment_create', {}),
    ('scheme_create', {}),
    ('period_create', {}),
    ('run_create', {}),
]


@pytest.mark.django_db
class TestRBACMatrix:
    """Staff (non-admin) cannot reach admin-only create pages."""
    @pytest.mark.parametrize('name,kw', ADMIN_ONLY_URLS)
    def test_staff_blocked(self, staff_client, name, kw):
        resp = staff_client.get(reverse(f'labor:{name}', kwargs=kw))
        # TenantAdminRequiredMixin redirects to dashboard.
        assert resp.status_code == 302

    @pytest.mark.parametrize('name,kw', ADMIN_ONLY_URLS)
    def test_admin_allowed(self, admin_client, name, kw):
        resp = admin_client.get(reverse(f'labor:{name}', kwargs=kw))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestAnonymousRedirect:
    @pytest.mark.parametrize('name', [
        'index', 'employee_list', 'leave_request_list',
        'labor_booking_list', 'scheme_list',
    ])
    def test_anonymous_redirect_to_login(self, client, name):
        resp = client.get(reverse(f'labor:{name}'))
        assert resp.status_code == 302
        assert '/accounts/login/' in resp.url


@pytest.mark.django_db
class TestMultiTenantIDOR:
    def test_cross_tenant_employee_404(self, admin_client, globex_employee):
        """An acme admin cannot read a globex employee."""
        resp = admin_client.get(reverse('labor:employee_detail',
                                        kwargs={'pk': globex_employee.pk}))
        assert resp.status_code == 404

    def test_cross_tenant_employee_terminate_404(self, admin_client, globex_employee):
        resp = admin_client.post(reverse('labor:employee_terminate',
                                         kwargs={'pk': globex_employee.pk}))
        assert resp.status_code == 404
