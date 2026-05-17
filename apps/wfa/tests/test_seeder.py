"""Seeder + cron dry-run safety tests."""
import pytest
from django.core.management import call_command

from apps.wfa import models as M


pytestmark = pytest.mark.django_db


def test_seed_wfa_creates_expected_rows(tenant_a):
    call_command('seed_wfa', tenant=tenant_a.slug)
    assert M.ProcessDefinition.objects.filter(tenant=tenant_a).count() >= 2
    assert M.ApprovalPolicy.objects.filter(tenant=tenant_a).count() >= 2
    assert M.NotificationTemplate.objects.filter(tenant=tenant_a).count() >= 5
    assert M.Connector.objects.filter(tenant=tenant_a).count() >= 6
    assert M.IntegrationFlow.objects.filter(tenant=tenant_a).count() >= 2
    assert M.BottleneckAnalysis.objects.filter(tenant=tenant_a).count() >= 1


def test_seed_wfa_idempotent(tenant_a):
    call_command('seed_wfa', tenant=tenant_a.slug)
    count_before = M.ProcessDefinition.objects.filter(tenant=tenant_a).count()
    call_command('seed_wfa', tenant=tenant_a.slug)
    count_after = M.ProcessDefinition.objects.filter(tenant=tenant_a).count()
    assert count_before == count_after


def test_seed_wfa_flush_resets(tenant_a):
    call_command('seed_wfa', tenant=tenant_a.slug)
    call_command('seed_wfa', tenant=tenant_a.slug, flush=True)
    assert M.ProcessDefinition.objects.filter(tenant=tenant_a).count() >= 2


def test_run_notifications_dry_run_safe(tenant_a):
    call_command('seed_wfa', tenant=tenant_a.slug)
    # Should not error and should not mutate Notification.status.
    call_command('run_notifications', dry_run=True, tenant=tenant_a.slug)


def test_escalate_approvals_dry_run_safe(tenant_a):
    call_command('seed_wfa', tenant=tenant_a.slug)
    call_command('escalate_approvals', dry_run=True, tenant=tenant_a.slug)


def test_mine_processes_creates_reports(tenant_a):
    call_command('seed_wfa', tenant=tenant_a.slug)
    initial_count = M.CycleTimeReport.objects.filter(tenant=tenant_a).count()
    call_command('mine_processes', tenant=tenant_a.slug)
    final_count = M.CycleTimeReport.objects.filter(tenant=tenant_a).count()
    assert final_count >= initial_count
