"""Pytest fixtures for Module 20 - WFA tests."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import Tenant, set_current_tenant


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(name='Tenant A', slug='wfa-tenant-a')
    set_current_tenant(t)
    yield t
    set_current_tenant(None)


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name='Tenant B', slug='wfa-tenant-b')


@pytest.fixture
def tenant_admin(db, tenant_a):
    User = get_user_model()
    return User.objects.create_user(
        username='admin_wfa_a', password='pw', email='admin@example.com',
        tenant=tenant_a, is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def staff_user(db, tenant_a):
    User = get_user_model()
    return User.objects.create_user(
        username='staff_wfa_a', password='pw', email='staff@example.com',
        tenant=tenant_a, is_tenant_admin=False, role='operator',
    )


@pytest.fixture
def other_tenant_user(db, tenant_b):
    User = get_user_model()
    return User.objects.create_user(
        username='admin_wfa_b', password='pw', email='b@example.com',
        tenant=tenant_b, is_tenant_admin=True, role='tenant_admin',
    )


@pytest.fixture
def definition(db, tenant_a):
    from apps.wfa import models as M
    cat = M.ProcessCategory.objects.create(tenant=tenant_a, code='OPS', name='Ops')
    d = M.ProcessDefinition.objects.create(
        tenant=tenant_a, name='Sample Process', category=cat, status='active',
    )
    start = M.ProcessNode.objects.create(
        tenant=tenant_a, definition=d, node_key='start',
        node_type='start', name='Start', order=0,
    )
    middle = M.ProcessNode.objects.create(
        tenant=tenant_a, definition=d, node_key='task1',
        node_type='user_task', name='Task 1', order=1,
    )
    end = M.ProcessNode.objects.create(
        tenant=tenant_a, definition=d, node_key='end',
        node_type='end', name='End', order=2,
    )
    M.ProcessTransition.objects.create(
        tenant=tenant_a, definition=d, from_node=start, to_node=middle,
    )
    M.ProcessTransition.objects.create(
        tenant=tenant_a, definition=d, from_node=middle, to_node=end,
    )
    return d


@pytest.fixture
def policy(db, tenant_a):
    from apps.wfa import models as M
    p = M.ApprovalPolicy.objects.create(
        tenant=tenant_a, code='POL-1', name='Sample Policy',
        applies_to_type='procurement.PurchaseOrder', is_active=True,
    )
    M.ApprovalLevel.objects.create(
        tenant=tenant_a, policy=p, level_no=1, name='L1',
        approver_role='department_head', sla_hours=24,
    )
    M.ApprovalLevel.objects.create(
        tenant=tenant_a, policy=p, level_no=2, name='L2',
        approver_role='plant_manager', sla_hours=48,
    )
    return p


@pytest.fixture
def channel(db, tenant_a):
    from apps.wfa import models as M
    return M.NotificationChannel.objects.create(
        tenant=tenant_a, code='email', name='Email', is_active=True,
    )


@pytest.fixture
def template(db, tenant_a, channel):
    from apps.wfa import models as M
    return M.NotificationTemplate.objects.create(
        tenant=tenant_a, code='T1', name='Tmpl',
        event_type='approval.approved',
        subject_template='Subj {{ request_code }}',
        body_template='Body {{ subject }}',
        channels=['email'],
        is_active=True,
    )


@pytest.fixture
def rule(db, tenant_a, template):
    from apps.wfa import models as M
    return M.NotificationRule.objects.create(
        tenant=tenant_a, name='Approved Rule',
        event_type='approval.approved',
        template=template, is_active=True,
    )


@pytest.fixture
def connector(db, tenant_a):
    from apps.wfa import models as M
    return M.Connector.objects.create(
        tenant=tenant_a, name='Test API', connector_type='rest_api',
        base_url='https://example.com', auth_method='none', is_active=True,
    )


@pytest.fixture
def flow(db, tenant_a, connector):
    from apps.wfa import models as M
    f = M.IntegrationFlow.objects.create(
        tenant=tenant_a, code='FL-1', name='Test Flow',
        trigger_type='manual', is_active=True,
    )
    M.FlowStep.objects.create(
        tenant=tenant_a, flow=f, step_no=1, name='Log it',
        step_type='log', on_failure='continue',
    )
    return f
