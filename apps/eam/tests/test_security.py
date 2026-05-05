"""RBAC matrix + multi-tenant IDOR + anonymous redirect (Lesson L-10)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.eam import models as eam_m


# ---------- Anonymous redirect ----------

@pytest.mark.django_db
class TestAnonymousRedirect:
    URLS = [
        ('eam:index', None),
        ('eam:asset_list', None),
        ('eam:asset_create', None),
        ('eam:pmplan_list', None),
        ('eam:mwo_list', None),
        ('eam:tool_list', None),
        ('eam:condition_point_list', None),
        ('eam:prediction_list', None),
        ('eam:downtime_list', None),
        ('eam:meter_reading_list', None),
        ('eam:tool_maintenance_list', None),
    ]

    @pytest.mark.parametrize('name', [u for u, _ in URLS])
    def test_anonymous_get_redirects_to_login(self, client, name):
        r = client.get(reverse(name))
        assert r.status_code in (302, 301)


# ---------- RBAC matrix: non-admin staff blocked from admin actions ----------

@pytest.mark.django_db
class TestRBACMatrix:
    """Per Lesson L-10, every state-changing surface must require admin role."""

    def test_staff_cannot_create_asset(self, staff_client, acme, category):
        before = eam_m.Asset.all_objects.count()
        r = staff_client.post(reverse('eam:asset_create'), data={
            'name': 'X', 'category': category.pk, 'criticality': 'low',
            'status': 'operational', 'purchase_cost': '0', 'current_value': '0',
            'is_active': 'on',
        })
        assert r.status_code == 302  # redirected away
        assert eam_m.Asset.all_objects.count() == before

    def test_staff_cannot_delete_asset(self, staff_client, acme, asset):
        r = staff_client.post(reverse('eam:asset_delete', args=[asset.pk]))
        assert r.status_code == 302
        assert eam_m.Asset.all_objects.filter(pk=asset.pk).exists()

    def test_staff_cannot_retire_asset(self, staff_client, asset):
        r = staff_client.post(reverse('eam:asset_retire', args=[asset.pk]))
        assert r.status_code == 302
        asset.refresh_from_db()
        assert asset.status != 'retired'

    def test_staff_cannot_create_pmplan(self, staff_client, asset):
        before = eam_m.MaintenancePlan.all_objects.count()
        staff_client.post(reverse('eam:pmplan_create'), data={
            'name': 'Bad', 'asset': asset.pk, 'trigger_type': 'calendar',
            'frequency_days': '30', 'is_active': 'on',
        })
        assert eam_m.MaintenancePlan.all_objects.count() == before

    def test_staff_cannot_create_mwo(self, staff_client, asset):
        before = eam_m.MaintenanceWorkOrder.all_objects.count()
        staff_client.post(reverse('eam:mwo_create'), data={
            'asset': asset.pk, 'wo_type': 'corrective',
            'priority': 'medium', 'title': 'X',
        })
        assert eam_m.MaintenanceWorkOrder.all_objects.count() == before

    def test_staff_cannot_cancel_mwo(self, staff_client, mwo):
        r = staff_client.post(reverse('eam:mwo_cancel', args=[mwo.pk]))
        assert r.status_code == 302
        mwo.refresh_from_db()
        assert mwo.status != 'cancelled'

    def test_staff_cannot_resolve_prediction(self, staff_client, acme, asset):
        p = eam_m.FailurePrediction.objects.create(
            tenant=acme, asset=asset, summary='X', status='open',
        )
        r = staff_client.post(reverse('eam:prediction_resolve', args=[p.pk]), data={
            'outcome': 'resolved', 'resolution_notes': 'attempt',
        })
        assert r.status_code == 302
        p.refresh_from_db()
        assert p.status == 'open'

    def test_staff_cannot_retire_tool(self, staff_client, tool):
        r = staff_client.post(reverse('eam:tool_retire', args=[tool.pk]))
        assert r.status_code == 302
        tool.refresh_from_db()
        assert tool.status != 'retired'

    def test_staff_can_record_meter_reading(self, staff_client, asset):
        """Recording readings is a non-privileged action - any tenant user can do it."""
        r = staff_client.post(
            reverse('eam:asset_reading_create', args=[asset.pk]),
            data={
                'meter_type': 'hours', 'reading_value': '10',
                'recorded_at': timezone.now().strftime('%Y-%m-%dT%H:%M'),
                'notes': '',
            },
        )
        assert r.status_code == 302
        assert eam_m.AssetMeterReading.all_objects.filter(asset=asset).exists()

    def test_staff_can_start_mwo(self, staff_client, mwo):
        """Operators can start work; only admins can cancel/delete."""
        r = staff_client.post(reverse('eam:mwo_start', args=[mwo.pk]))
        assert r.status_code == 302
        mwo.refresh_from_db()
        assert mwo.status == 'in_progress'


# ---------- Multi-tenant IDOR (cross-tenant 404) ----------

@pytest.mark.django_db
class TestMultiTenantIDOR:
    def test_globex_admin_cannot_view_acme_asset(self, globex_client, asset):
        r = globex_client.get(reverse('eam:asset_detail', args=[asset.pk]))
        assert r.status_code == 404

    def test_globex_admin_cannot_edit_acme_asset(self, globex_client, asset):
        r = globex_client.post(reverse('eam:asset_edit', args=[asset.pk]), data={
            'name': 'Pwn', 'criticality': 'low',
            'status': 'operational',
            'purchase_cost': '0', 'current_value': '0', 'is_active': 'on',
        })
        assert r.status_code == 404
        asset.refresh_from_db()
        assert asset.name != 'Pwn'

    def test_globex_admin_cannot_delete_acme_mwo(self, globex_client, mwo):
        r = globex_client.post(reverse('eam:mwo_delete', args=[mwo.pk]))
        assert r.status_code == 404
        assert eam_m.MaintenanceWorkOrder.all_objects.filter(pk=mwo.pk).exists()

    def test_globex_admin_cannot_retire_acme_tool(self, globex_client, tool):
        r = globex_client.post(reverse('eam:tool_retire', args=[tool.pk]))
        assert r.status_code == 404
        tool.refresh_from_db()
        assert tool.status != 'retired'

    def test_globex_list_excludes_acme_assets(self, globex_client, asset):
        r = globex_client.get(reverse('eam:asset_list'))
        assert r.status_code == 200
        assert asset.tag.encode() not in r.content
