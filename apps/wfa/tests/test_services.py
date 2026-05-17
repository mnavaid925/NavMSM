"""Pure-function service tests."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.wfa import models as M
from apps.wfa.services import approval as approval_svc
from apps.wfa.services import bpmn_engine
from apps.wfa.services import notification as notif_svc
from apps.wfa.services import integration as int_svc
from apps.wfa.services import process_mining


pytestmark = pytest.mark.django_db


# ---- BPMN engine ----------------------------------------------------------

def test_safe_eval_rejects_import():
    with pytest.raises(bpmn_engine.FormulaError):
        bpmn_engine.evaluate_condition('__import__("os")', {})


def test_safe_eval_rejects_attribute_access():
    with pytest.raises(bpmn_engine.FormulaError):
        bpmn_engine.evaluate_condition('a.b', {'a': 1})


def test_safe_eval_rejects_lambda():
    with pytest.raises(bpmn_engine.FormulaError):
        bpmn_engine.evaluate_condition('(lambda: 1)()', {})


def test_safe_eval_rejects_pow_operator():
    with pytest.raises(bpmn_engine.FormulaError):
        bpmn_engine.evaluate_condition('2 ** 30', {})


def test_safe_eval_empty_is_true():
    assert bpmn_engine.evaluate_condition('', {}) is True
    assert bpmn_engine.evaluate_condition('   ', {}) is True


def test_safe_eval_comparisons():
    assert bpmn_engine.evaluate_condition('amount < 100', {'amount': 50}) is True
    assert bpmn_engine.evaluate_condition('amount >= 100', {'amount': 50}) is False
    assert bpmn_engine.evaluate_condition('status == "approve"', {'status': 'approve'}) is True


def test_safe_eval_boolean_ops():
    assert bpmn_engine.evaluate_condition('a and b', {'a': True, 'b': True}) is True
    assert bpmn_engine.evaluate_condition('a or b', {'a': False, 'b': True}) is True
    assert bpmn_engine.evaluate_condition('not a', {'a': False}) is True


def test_bpmn_next_node_picks_first_matching_transition(tenant_a, definition):
    inst = M.ProcessInstance.objects.create(
        tenant=tenant_a, definition=definition, status='running',
        current_node=definition.nodes.get(node_key='start'),
    )
    nxt = bpmn_engine.next_node(inst)
    assert nxt is not None
    assert nxt.node_key == 'task1'


def test_bpmn_next_node_returns_none_when_no_outgoing(tenant_a, definition):
    inst = M.ProcessInstance.objects.create(
        tenant=tenant_a, definition=definition, status='running',
        current_node=definition.nodes.get(node_key='end'),
    )
    assert bpmn_engine.next_node(inst) is None


# ---- Approval engine ------------------------------------------------------

def test_approval_submit_sets_status_and_due_at(tenant_a, policy, tenant_admin):
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='x',
        requested_by=tenant_admin,
    )
    approval_svc.submit(req, actor=tenant_admin)
    req.refresh_from_db()
    assert req.status == 'in_progress'
    assert req.due_at is not None
    assert req.action_logs.filter(decision='submit').exists()


def test_approval_approve_advances_level(tenant_a, policy, tenant_admin):
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='x',
        requested_by=tenant_admin,
    )
    approval_svc.submit(req, actor=tenant_admin)
    approval_svc.approve(req, actor=tenant_admin)
    req.refresh_from_db()
    assert req.status == 'in_progress'
    assert req.current_level_no == 2


def test_approval_approve_completes_on_final_level(tenant_a, policy, tenant_admin):
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='x',
        requested_by=tenant_admin,
    )
    approval_svc.submit(req, actor=tenant_admin)
    approval_svc.approve(req, actor=tenant_admin)
    approval_svc.approve(req, actor=tenant_admin)
    req.refresh_from_db()
    assert req.status == 'approved'
    assert req.decided_at is not None


def test_approval_reject_terminates(tenant_a, policy, tenant_admin):
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='x',
        requested_by=tenant_admin,
    )
    approval_svc.submit(req, actor=tenant_admin)
    approval_svc.reject(req, actor=tenant_admin, notes='nope')
    req.refresh_from_db()
    assert req.status == 'rejected'


def test_approval_recall_cancels(tenant_a, policy, tenant_admin):
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_a, policy=policy, subject='x',
        requested_by=tenant_admin,
    )
    approval_svc.submit(req, actor=tenant_admin)
    approval_svc.recall(req, actor=tenant_admin)
    req.refresh_from_db()
    assert req.status == 'cancelled'


def test_active_delegate_resolves(tenant_a, policy, tenant_admin, staff_user):
    M.ApprovalDelegation.objects.create(
        tenant=tenant_a, delegator=tenant_admin, delegate=staff_user,
        policy=policy, starts_at=timezone.localdate(),
        ends_at=timezone.localdate() + timedelta(days=7), is_active=True,
    )
    result = approval_svc.active_delegate_for(
        tenant=tenant_a, delegator=tenant_admin, policy=policy,
    )
    assert result == staff_user


# ---- Notification ---------------------------------------------------------

def test_notification_render_template():
    out = notif_svc.render_template('Hi {{ name }}', {'name': 'World'})
    assert out == 'Hi World'


def test_notification_dispatch_writes_delivery(tenant_a, rule, tenant_admin, channel):
    n = notif_svc.create_notification(
        tenant=tenant_a, rule=rule, recipient=tenant_admin,
        payload={'request_code': 'X', 'subject': 'Y'},
    )
    notif_svc.dispatch(n)
    n.refresh_from_db()
    assert n.status == 'sent'
    assert n.deliveries.filter(status='sent').count() == 1


# ---- Integration ----------------------------------------------------------

def test_execute_flow_log_step_completes(tenant_a, flow, tenant_admin):
    run = int_svc.execute_flow(flow, triggered_by=tenant_admin)
    assert run.status == 'completed'
    assert run.code.startswith('IR-')


# ---- Process mining -------------------------------------------------------

def test_classify_severity_thresholds():
    assert process_mining.classify_severity(Decimal('60')) == 'low'
    assert process_mining.classify_severity(Decimal('1900')) == 'medium'
    assert process_mining.classify_severity(Decimal('15000')) == 'high'
    assert process_mining.classify_severity(Decimal('90000')) == 'critical'


def test_compute_cycle_seconds(tenant_a, definition):
    started = timezone.now() - timedelta(hours=1)
    inst = M.ProcessInstance.objects.create(
        tenant=tenant_a, definition=definition, status='completed',
        started_at=started,
        completed_at=started + timedelta(seconds=3600),
    )
    assert process_mining.compute_cycle_seconds(inst) == Decimal('3600.0')


def test_cycle_time_stats_handles_empty():
    n, avg, p95, mn, mx = process_mining.cycle_time_stats([])
    assert n == 0 and avg == Decimal('0')
