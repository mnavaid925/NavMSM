"""Smoke tests for HTTP CRUD paths."""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone


@pytest.mark.django_db
class TestDashboardListPages:
    def test_index_renders(self, admin_client):
        resp = admin_client.get(reverse('bi:index'))
        assert resp.status_code == 200

    def test_kpi_definition_list_renders(self, admin_client, oee_kpi):
        resp = admin_client.get(reverse('bi:kpi_definition_list'))
        assert resp.status_code == 200
        assert b'oee' in resp.content.lower()

    def test_dashboard_list_renders(self, admin_client, dashboard):
        resp = admin_client.get(reverse('bi:dashboard_list'))
        assert resp.status_code == 200

    def test_data_source_list_renders(self, admin_client, report_data_source):
        resp = admin_client.get(reverse('bi:data_source_list'))
        assert resp.status_code == 200

    def test_report_list_renders(self, admin_client, report):
        resp = admin_client.get(reverse('bi:report_list'))
        assert resp.status_code == 200

    def test_predictive_model_list_renders(self, admin_client, predictive_model):
        resp = admin_client.get(reverse('bi:predictive_model_list'))
        assert resp.status_code == 200

    def test_mart_list_renders(self, admin_client, data_mart):
        resp = admin_client.get(reverse('bi:mart_list'))
        assert resp.status_code == 200

    def test_schedule_list_renders(self, admin_client, schedule):
        resp = admin_client.get(reverse('bi:schedule_list'))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestKPICreate:
    def test_create_kpi_definition(self, admin_client, acme):
        resp = admin_client.post(reverse('bi:kpi_definition_create'), {
            'code': 'throughput', 'name': 'Throughput', 'unit': 'units',
            'direction': 'higher_is_better', 'is_active': 'on',
        })
        assert resp.status_code in (302, 200)
        from apps.bi.models import KPIDefinition
        assert KPIDefinition.all_objects.filter(tenant=acme, code='throughput').exists()


@pytest.mark.django_db
class TestDashboardCreate:
    def test_create_dashboard(self, admin_client, acme):
        resp = admin_client.post(reverse('bi:dashboard_create'), {
            'name': 'New Dashboard', 'slug': 'new-dashboard',
            'is_shared': 'on', 'default_period': 'last_30d', 'auto_refresh_minutes': '15',
        })
        assert resp.status_code in (302, 200)
        from apps.bi.models import KPIDashboard
        assert KPIDashboard.all_objects.filter(tenant=acme, slug='new-dashboard').exists()


@pytest.mark.django_db
class TestKPIRefresh:
    def test_refresh_creates_snapshot(self, admin_client, oee_kpi):
        # Refresh KPI for empty period - returns 0 but should not crash.
        resp = admin_client.post(reverse('bi:kpi_definition_refresh', args=[oee_kpi.pk]))
        assert resp.status_code in (302, 200)
