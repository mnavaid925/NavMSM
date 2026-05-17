"""HTTP smoke tests for list / detail / workflow handlers."""
import pytest
from django.urls import reverse

from apps.wfa import models as M


pytestmark = pytest.mark.django_db


def test_dashboard_renders(client, tenant_admin):
    client.force_login(tenant_admin)
    r = client.get(reverse('wfa:index'))
    assert r.status_code == 200


@pytest.mark.parametrize('name', [
    'wfa:category_list', 'wfa:process_list', 'wfa:instance_list',
    'wfa:policy_list', 'wfa:request_list', 'wfa:my_requests',
    'wfa:delegation_list',
    'wfa:channel_list', 'wfa:template_list', 'wfa:rule_list',
    'wfa:notification_list', 'wfa:delivery_list', 'wfa:sms_list',
    'wfa:connector_list', 'wfa:flow_list', 'wfa:run_list', 'wfa:outbox_list',
    'wfa:bottleneck_list', 'wfa:suggestion_list', 'wfa:cycle_time_list',
])
def test_list_pages_render(client, tenant_admin, name):
    client.force_login(tenant_admin)
    r = client.get(reverse(name))
    assert r.status_code == 200


def test_process_detail_renders(client, tenant_admin, definition):
    client.force_login(tenant_admin)
    r = client.get(reverse('wfa:process_detail', args=[definition.pk]))
    assert r.status_code == 200


def test_policy_detail_renders(client, tenant_admin, policy):
    client.force_login(tenant_admin)
    r = client.get(reverse('wfa:policy_detail', args=[policy.pk]))
    assert r.status_code == 200


def test_request_detail_renders(client, tenant_admin, policy):
    client.force_login(tenant_admin)
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_admin.tenant, policy=policy, subject='x',
        requested_by=tenant_admin, status='in_progress',
    )
    r = client.get(reverse('wfa:request_detail', args=[req.pk]))
    assert r.status_code == 200


def test_approve_workflow_walk(client, tenant_admin, policy):
    client.force_login(tenant_admin)
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_admin.tenant, policy=policy, subject='x',
        requested_by=tenant_admin, status='in_progress',
    )
    # Level 1 approve - should advance to level 2.
    r = client.post(reverse('wfa:request_approve', args=[req.pk]), {'notes': 'ok'})
    assert r.status_code == 302
    req.refresh_from_db()
    assert req.current_level_no == 2
    # Level 2 approve - should complete.
    r = client.post(reverse('wfa:request_approve', args=[req.pk]), {'notes': 'ok'})
    req.refresh_from_db()
    assert req.status == 'approved'


def test_reject_requires_notes(client, tenant_admin, policy):
    client.force_login(tenant_admin)
    req = M.ApprovalRequest.objects.create(
        tenant=tenant_admin.tenant, policy=policy, subject='x',
        requested_by=tenant_admin, status='in_progress',
    )
    r = client.post(reverse('wfa:request_reject', args=[req.pk]), {'notes': ''})
    assert r.status_code == 302
    req.refresh_from_db()
    assert req.status == 'in_progress'


def test_flow_run_creates_run(client, tenant_admin, flow):
    client.force_login(tenant_admin)
    r = client.post(reverse('wfa:flow_run', args=[flow.pk]))
    assert r.status_code == 302
    assert M.IntegrationRun.objects.filter(flow=flow).exists()


def test_process_create_with_admin(client, tenant_admin):
    client.force_login(tenant_admin)
    r = client.post(reverse('wfa:process_create'), {
        'name': 'Brand New', 'version': '1.0', 'status': 'draft', 'is_default': False,
        'description': '', 'category': '', 'owner': '',
    })
    # 302 on success, 200 if validation error.
    assert M.ProcessDefinition.objects.filter(name='Brand New').exists()


def test_instance_advance(client, tenant_admin, definition):
    client.force_login(tenant_admin)
    start_node = definition.nodes.get(node_key='start')
    inst = M.ProcessInstance.objects.create(
        tenant=tenant_admin.tenant, definition=definition,
        status='running', current_node=start_node,
    )
    r = client.post(reverse('wfa:instance_advance', args=[inst.pk]))
    assert r.status_code == 302
    inst.refresh_from_db()
    assert inst.current_node.node_key == 'task1'
