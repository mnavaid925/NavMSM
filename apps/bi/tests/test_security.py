"""Multi-tenant IDOR + RBAC + anonymous-redirect smoke."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestAnonymousRedirect:
    """Every list URL redirects to login for an anonymous user."""

    @pytest.mark.parametrize('url_name', [
        'bi:index',
        'bi:kpi_definition_list',
        'bi:kpi_snapshot_list',
        'bi:dashboard_list',
        'bi:data_source_list',
        'bi:report_list',
        'bi:report_run_list',
        'bi:predictive_model_list',
        'bi:prediction_run_list',
        'bi:trend_list',
        'bi:mart_list',
        'bi:schedule_list',
        'bi:delivery_list',
        'bi:export_list',
    ])
    def test_anonymous_redirect(self, client, url_name):
        resp = client.get(reverse(url_name))
        assert resp.status_code in (302, 301)
        assert '/accounts/login' in resp.url or '/login' in resp.url


@pytest.mark.django_db
class TestCrossTenantIDOR:
    """Detail pages for tenant A's records 404 for tenant B's admin."""

    def test_dashboard_cross_tenant_404(self, globex_client, dashboard):
        resp = globex_client.get(reverse('bi:dashboard_detail', args=[dashboard.pk]))
        assert resp.status_code == 404

    def test_kpi_definition_cross_tenant_404(self, globex_client, oee_kpi):
        resp = globex_client.get(reverse('bi:kpi_definition_detail', args=[oee_kpi.pk]))
        assert resp.status_code == 404

    def test_report_cross_tenant_404(self, globex_client, report):
        resp = globex_client.get(reverse('bi:report_detail', args=[report.pk]))
        assert resp.status_code == 404

    def test_predictive_model_cross_tenant_404(self, globex_client, predictive_model):
        resp = globex_client.get(reverse('bi:predictive_model_detail', args=[predictive_model.pk]))
        assert resp.status_code == 404

    def test_mart_cross_tenant_404(self, globex_client, data_mart):
        resp = globex_client.get(reverse('bi:mart_detail', args=[data_mart.pk]))
        assert resp.status_code == 404

    def test_schedule_cross_tenant_404(self, globex_client, schedule):
        resp = globex_client.get(reverse('bi:schedule_detail', args=[schedule.pk]))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestRBACMatrix:
    """Admin-only POST endpoints must reject non-admin staff."""

    def test_staff_blocked_from_kpi_create(self, staff_client):
        resp = staff_client.get(reverse('bi:kpi_definition_create'))
        assert resp.status_code in (302, 403)

    def test_staff_blocked_from_dashboard_create(self, staff_client):
        resp = staff_client.get(reverse('bi:dashboard_create'))
        assert resp.status_code in (302, 403)

    def test_staff_blocked_from_mart_create(self, staff_client):
        resp = staff_client.get(reverse('bi:mart_create'))
        assert resp.status_code in (302, 403)

    def test_staff_blocked_from_schedule_create(self, staff_client):
        resp = staff_client.get(reverse('bi:schedule_create'))
        assert resp.status_code in (302, 403)

    def test_staff_can_view_dashboards(self, staff_client):
        resp = staff_client.get(reverse('bi:dashboard_list'))
        assert resp.status_code == 200
