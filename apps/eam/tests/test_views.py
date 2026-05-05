"""View smoke tests: full CRUD happy paths + workflow transitions."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.eam import models as eam_m


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard_loads(self, admin_client, acme):
        r = admin_client.get(reverse('eam:index'))
        assert r.status_code == 200


@pytest.mark.django_db
class TestAssetCRUD:
    def test_list(self, admin_client, asset):
        r = admin_client.get(reverse('eam:asset_list'))
        assert r.status_code == 200
        assert asset.tag.encode() in r.content

    def test_create(self, admin_client, acme, category):
        r = admin_client.post(reverse('eam:asset_create'), data={
            'name': 'New Pump', 'category': category.pk,
            'criticality': 'medium', 'status': 'operational',
            'purchase_cost': '0', 'current_value': '0',
            'is_active': 'on',
        })
        assert r.status_code == 302
        assert eam_m.Asset.objects.filter(tenant=acme, name='New Pump').exists()

    def test_detail(self, admin_client, asset):
        r = admin_client.get(reverse('eam:asset_detail', args=[asset.pk]))
        assert r.status_code == 200

    def test_edit(self, admin_client, acme, asset):
        r = admin_client.post(reverse('eam:asset_edit', args=[asset.pk]), data={
            'name': 'Renamed', 'category': asset.category_id,
            'criticality': 'high', 'status': 'operational',
            'purchase_cost': '0', 'current_value': '0',
            'is_active': 'on',
        })
        assert r.status_code == 302
        asset.refresh_from_db()
        assert asset.name == 'Renamed'

    def test_delete(self, admin_client, acme):
        a = eam_m.Asset.objects.create(tenant=acme, name='Tmp', criticality='low')
        r = admin_client.post(reverse('eam:asset_delete', args=[a.pk]))
        assert r.status_code == 302
        assert not eam_m.Asset.all_objects.filter(pk=a.pk).exists()

    def test_retire(self, admin_client, asset):
        r = admin_client.post(reverse('eam:asset_retire', args=[asset.pk]))
        assert r.status_code == 302
        asset.refresh_from_db()
        assert asset.status == 'retired'

    def test_reactivate(self, admin_client, asset):
        eam_m.Asset.all_objects.filter(pk=asset.pk).update(status='retired', is_active=False)
        r = admin_client.post(reverse('eam:asset_reactivate', args=[asset.pk]))
        assert r.status_code == 302
        asset.refresh_from_db()
        assert asset.status == 'operational'


@pytest.mark.django_db
class TestAssetCategoryCRUD:
    def test_list_create_delete(self, admin_client, acme):
        # Create
        r = admin_client.post(reverse('eam:category_create'), data={
            'name': 'Tools', 'is_active': 'on',
        })
        assert r.status_code == 302
        c = eam_m.AssetCategory.objects.get(tenant=acme, name='Tools')
        # List
        r = admin_client.get(reverse('eam:category_list'))
        assert r.status_code == 200
        # Delete
        r = admin_client.post(reverse('eam:category_delete', args=[c.pk]))
        assert r.status_code == 302


@pytest.mark.django_db
class TestPMPlanFlow:
    def test_create_and_generate(self, admin_client, acme, asset):
        r = admin_client.post(reverse('eam:pmplan_create'), data={
            'name': 'Quarterly', 'asset': asset.pk,
            'trigger_type': 'calendar', 'frequency_days': '90',
            'next_due_at': (date.today() + timedelta(days=10)).isoformat(),
            'is_active': 'on',
        })
        assert r.status_code == 302
        plan = eam_m.MaintenancePlan.objects.get(tenant=acme, name='Quarterly')
        # Generate upcoming.
        r = admin_client.post(reverse('eam:pmplan_generate', args=[plan.pk]))
        assert r.status_code == 302
        assert eam_m.PMSchedule.all_objects.filter(plan=plan).count() >= 1


@pytest.mark.django_db
class TestPMScheduleWorkflow:
    def test_start_and_complete(self, admin_client, acme, pm_plan, pm_schedule):
        # Tasks not required to test start; complete needs at least one task result if tasks exist.
        # Add one task and one completion to satisfy the L-14 form.
        task = eam_m.MaintenanceTask.objects.create(
            tenant=acme, plan=pm_plan, sequence=10, description='Check',
        )
        # Start
        r = admin_client.post(reverse('eam:pmschedule_start', args=[pm_schedule.pk]))
        assert r.status_code == 302
        pm_schedule.refresh_from_db()
        assert pm_schedule.status == 'in_progress'
        # Record a completion
        r = admin_client.post(reverse('eam:pmschedule_task_create', args=[pm_schedule.pk]), data={
            'task': task.pk, 'result': 'pass', 'comments': 'ok',
        })
        assert r.status_code == 302
        # Complete
        r = admin_client.post(reverse('eam:pmschedule_complete', args=[pm_schedule.pk]), data={
            'notes': 'Done.',
        })
        assert r.status_code == 302
        pm_schedule.refresh_from_db()
        assert pm_schedule.status == 'completed'

    def test_complete_without_task_result_blocked(self, admin_client, acme, pm_plan, pm_schedule):
        eam_m.MaintenanceTask.objects.create(
            tenant=acme, plan=pm_plan, sequence=10, description='X',
        )
        admin_client.post(reverse('eam:pmschedule_start', args=[pm_schedule.pk]))
        # Try to complete with no task results.
        r = admin_client.post(reverse('eam:pmschedule_complete', args=[pm_schedule.pk]), data={
            'notes': '',
        })
        assert r.status_code == 302
        pm_schedule.refresh_from_db()
        assert pm_schedule.status != 'completed'


@pytest.mark.django_db
class TestMWOWorkflow:
    def test_full_lifecycle(self, admin_client, acme, mwo):
        # draft -> scheduled
        r = admin_client.post(reverse('eam:mwo_schedule', args=[mwo.pk]))
        assert r.status_code == 302
        mwo.refresh_from_db()
        assert mwo.status == 'scheduled'
        # scheduled -> in_progress
        admin_client.post(reverse('eam:mwo_start', args=[mwo.pk]))
        mwo.refresh_from_db()
        assert mwo.status == 'in_progress'
        # in_progress -> on_hold
        admin_client.post(reverse('eam:mwo_hold', args=[mwo.pk]))
        mwo.refresh_from_db()
        assert mwo.status == 'on_hold'
        # on_hold -> in_progress
        admin_client.post(reverse('eam:mwo_resume', args=[mwo.pk]))
        mwo.refresh_from_db()
        assert mwo.status == 'in_progress'
        # complete (requires resolution_notes)
        r = admin_client.post(reverse('eam:mwo_complete', args=[mwo.pk]), data={
            'resolution_notes': 'Replaced bearing',
            'root_cause': 'Worn bearing',
        })
        assert r.status_code == 302
        mwo.refresh_from_db()
        assert mwo.status == 'completed'

    def test_complete_without_notes_blocked(self, admin_client, mwo):
        admin_client.post(reverse('eam:mwo_start', args=[mwo.pk]))
        r = admin_client.post(reverse('eam:mwo_complete', args=[mwo.pk]), data={
            'resolution_notes': '   ', 'root_cause': '',
        })
        assert r.status_code == 302
        mwo.refresh_from_db()
        assert mwo.status != 'completed'

    def test_cancel(self, admin_client, mwo):
        r = admin_client.post(reverse('eam:mwo_cancel', args=[mwo.pk]))
        assert r.status_code == 302
        mwo.refresh_from_db()
        assert mwo.status == 'cancelled'


@pytest.mark.django_db
class TestFailurePredictionWorkflow:
    def test_investigate_then_resolve(self, admin_client, acme, asset):
        p = eam_m.FailurePrediction.objects.create(
            tenant=acme, asset=asset, summary='X', status='open',
        )
        admin_client.post(reverse('eam:prediction_investigate', args=[p.pk]))
        p.refresh_from_db()
        assert p.status == 'investigating'
        r = admin_client.post(reverse('eam:prediction_resolve', args=[p.pk]), data={
            'outcome': 'resolved',
            'resolution_notes': 'Replaced bearing.',
        })
        assert r.status_code == 302
        p.refresh_from_db()
        assert p.status == 'resolved'

    def test_resolve_without_notes_blocked(self, admin_client, acme, asset):
        p = eam_m.FailurePrediction.objects.create(
            tenant=acme, asset=asset, summary='X', status='open',
        )
        r = admin_client.post(reverse('eam:prediction_resolve', args=[p.pk]), data={
            'outcome': 'resolved', 'resolution_notes': '   ',
        })
        assert r.status_code == 302
        p.refresh_from_db()
        assert p.status == 'open'


@pytest.mark.django_db
class TestToolFlow:
    def test_create_and_retire(self, admin_client, acme):
        r = admin_client.post(reverse('eam:tool_create'), data={
            'name': 'Mill', 'tool_type': 'cutting_tool', 'status': 'available',
            'purchase_cost': '100', 'expected_life_cycles': 1000,
            'expected_life_hours': '100', 'cavity_count': 0,
            'is_active': 'on',
        })
        assert r.status_code == 302
        t = eam_m.Tool.objects.get(tenant=acme, name='Mill')
        # Log usage (bumps denorm).
        admin_client.post(reverse('eam:tool_usage_create', args=[t.pk]), data={
            'used_at': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'cycles_added': 50, 'hours_added': '2', 'notes': '',
        })
        t.refresh_from_db()
        assert t.current_cycles == 50
        # Retire.
        admin_client.post(reverse('eam:tool_retire', args=[t.pk]))
        t.refresh_from_db()
        assert t.status == 'retired'


@pytest.mark.django_db
class TestConditionReadingFlow:
    def test_record_reading(self, admin_client, acme, monitoring_point):
        r = admin_client.post(
            reverse('eam:condition_reading_create', args=[monitoring_point.pk]),
            data={
                'point': monitoring_point.pk,
                'reading_value': '2.0',
                'recorded_at': timezone.now().strftime('%Y-%m-%dT%H:%M'),
                'notes': '',
            },
        )
        assert r.status_code == 302
        assert eam_m.ConditionReading.objects.filter(point=monitoring_point).exists()


@pytest.mark.django_db
class TestNullableFKRendersGracefully:
    """Regression for BUG-01 (manual walkthrough 2026-05-06).

    When a nullable User FK on a model is None (e.g. ``PMSchedule.assignee``
    when the schedule was auto-generated by ``generate_pm_schedules`` — no
    one assigned yet), the template MUST render a placeholder rather than
    blow up trying to access ``None.username`` via a chained ``|default:``
    filter. The original template chain
    ``{{ s.assignee.get_full_name|default:s.assignee.username|default:"-" }}``
    raises ``VariableDoesNotExist`` on render because the second ``default``
    operand evaluates ``None.username``.
    """

    def test_pm_schedule_list_renders_with_null_assignee(self, admin_client, pm_schedule):
        # pm_schedule fixture has no assignee set.
        assert pm_schedule.assignee is None
        r = admin_client.get(reverse('eam:pmschedule_list'))
        assert r.status_code == 200
        # Template should render the dash placeholder.
        assert pm_schedule.schedule_number.encode() in r.content

    def test_pm_schedule_detail_renders_with_null_assignee(self, admin_client, pm_schedule):
        r = admin_client.get(reverse('eam:pmschedule_detail', args=[pm_schedule.pk]))
        assert r.status_code == 200
        assert b'Unassigned' in r.content

    def test_mwo_detail_renders_with_null_reported_by(self, admin_client, acme, asset):
        # Build an MWO with no reported_by set (edge case: import / API path).
        m = eam_m.MaintenanceWorkOrder.all_objects.create(
            tenant=acme, asset=asset, wo_type='corrective',
            priority='medium', title='Null reporter',
            reported_by=None, reported_at=timezone.now(),
        )
        r = admin_client.get(reverse('eam:mwo_detail', args=[m.pk]))
        assert r.status_code == 200

    def test_failure_prediction_detail_renders_with_null_resolved_by(
        self, admin_client, acme, asset,
    ):
        p = eam_m.FailurePrediction.objects.create(
            tenant=acme, asset=asset, summary='X', status='resolved',
            resolved_at=timezone.now(), resolved_by=None,
            resolution_notes='Auto-resolved by import job.',
        )
        r = admin_client.get(reverse('eam:prediction_detail', args=[p.pk]))
        assert r.status_code == 200
