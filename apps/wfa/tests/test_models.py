"""Model invariants - auto-numbering, computed fields, validators."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.wfa import models as M


pytestmark = pytest.mark.django_db


def test_process_definition_auto_code(tenant_a):
    d = M.ProcessDefinition.objects.create(tenant=tenant_a, name='X', status='draft')
    assert d.code.startswith('BPM-')
    assert d.code == f'BPM-{d.id:05d}'


def test_process_instance_auto_code(tenant_a, definition):
    inst = M.ProcessInstance.objects.create(
        tenant=tenant_a, definition=definition, status='running',
    )
    assert inst.code.startswith('PI-')


def test_approval_request_auto_code(tenant_a, policy):
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='Test',
    )
    assert req.code.startswith('APR-')


def test_notification_rule_auto_code(tenant_a, template):
    r = M.NotificationRule.objects.create(
        tenant=tenant_a, name='X', event_type='x', template=template,
    )
    assert r.code.startswith('NR-')


def test_notification_auto_code(tenant_a, rule, tenant_admin):
    n = M.Notification.objects.create(
        tenant=tenant_a, rule=rule, event_type='x',
        recipient=tenant_admin, subject='s', body='b',
    )
    assert n.code.startswith('NTF-')


def test_connector_auto_code(tenant_a):
    c = M.Connector.objects.create(
        tenant=tenant_a, name='X', connector_type='rest_api',
    )
    assert c.code.startswith('CON-')


def test_integration_run_auto_code(tenant_a, flow):
    r = M.IntegrationRun.objects.create(tenant=tenant_a, flow=flow, status='running')
    assert r.code.startswith('IR-')


def test_bottleneck_analysis_auto_code(tenant_a, definition):
    b = M.BottleneckAnalysis.objects.create(
        tenant=tenant_a, definition=definition,
        period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
    )
    assert b.code.startswith('BA-')


def test_optimization_suggestion_auto_code(tenant_a, definition):
    s = M.ProcessOptimizationSuggestion.objects.create(
        tenant=tenant_a, definition=definition,
        suggestion_type='reorder_steps', description='x',
    )
    assert s.code.startswith('POS-')


def test_cycle_time_report_auto_code(tenant_a, definition):
    r = M.CycleTimeReport.objects.create(
        tenant=tenant_a, definition=definition,
        period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
    )
    assert r.code.startswith('CTR-')


def test_approval_request_is_open(tenant_a, policy):
    r = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='x', status='pending',
    )
    assert r.is_open()
    r.status = 'approved'
    assert not r.is_open()


def test_approval_request_is_overdue(tenant_a, policy):
    r = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='x', status='in_progress',
        due_at=timezone.now() - timedelta(hours=1),
    )
    assert r.is_overdue()
    r.due_at = timezone.now() + timedelta(hours=1)
    assert not r.is_overdue()


def test_process_definition_is_editable(tenant_a):
    d = M.ProcessDefinition.objects.create(tenant=tenant_a, name='x', status='draft')
    assert d.is_editable()
    d.status = 'active'
    assert not d.is_editable()


def test_process_instance_is_active(tenant_a, definition):
    inst = M.ProcessInstance.objects.create(
        tenant=tenant_a, definition=definition, status='running',
    )
    assert inst.is_active()
    inst.status = 'completed'
    assert not inst.is_active()


def test_suggestion_expected_savings_validators(tenant_a, definition):
    s = M.ProcessOptimizationSuggestion(
        tenant=tenant_a, definition=definition,
        suggestion_type='reorder_steps', description='x',
        expected_savings_pct=Decimal('150'),
    )
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        s.full_clean()
