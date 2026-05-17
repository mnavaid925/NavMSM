"""Multi-tenant IDOR + RBAC matrix."""
import pytest
from django.urls import reverse

from apps.wfa import models as M


pytestmark = [pytest.mark.django_db, pytest.mark.security]


def test_anonymous_redirected_from_dashboard(client):
    r = client.get(reverse('wfa:index'))
    assert r.status_code in (302, 301)


@pytest.mark.parametrize('name', [
    'wfa:process_list', 'wfa:instance_list', 'wfa:policy_list',
    'wfa:request_list', 'wfa:connector_list', 'wfa:flow_list',
    'wfa:suggestion_list',
])
def test_anonymous_redirected_from_lists(client, name):
    r = client.get(reverse(name))
    assert r.status_code in (302, 301)


def test_cross_tenant_process_404(client, tenant_admin, other_tenant_user, tenant_b):
    from apps.core.models import set_current_tenant
    set_current_tenant(tenant_b)
    other_def = M.ProcessDefinition.objects.create(
        tenant=tenant_b, name='Foreign', status='active',
    )
    set_current_tenant(tenant_admin.tenant)
    client.force_login(tenant_admin)
    r = client.get(reverse('wfa:process_detail', args=[other_def.pk]))
    assert r.status_code == 404


def test_cross_tenant_policy_404(client, tenant_admin, tenant_b):
    from apps.core.models import set_current_tenant
    set_current_tenant(tenant_b)
    other = M.ApprovalPolicy.objects.create(tenant=tenant_b, code='X', name='X')
    set_current_tenant(tenant_admin.tenant)
    client.force_login(tenant_admin)
    r = client.get(reverse('wfa:policy_detail', args=[other.pk]))
    assert r.status_code == 404


def test_staff_blocked_from_policy_create(client, staff_user):
    client.force_login(staff_user)
    r = client.post(reverse('wfa:policy_create'), {
        'name': 'X', 'code': 'X', 'is_active': True, 'applies_to_type': '', 'description': '',
    })
    # The decorator redirects to dashboard with a flash error.
    assert r.status_code in (302, 301)
    assert not M.ApprovalPolicy.objects.filter(code='X').exists()


def test_staff_blocked_from_process_delete(client, staff_user, definition):
    client.force_login(staff_user)
    r = client.post(reverse('wfa:process_delete', args=[definition.pk]))
    assert r.status_code in (302, 301)
    assert M.ProcessDefinition.objects.filter(pk=definition.pk).exists()


def test_staff_blocked_from_connector_create(client, staff_user):
    client.force_login(staff_user)
    r = client.post(reverse('wfa:connector_create'), {
        'name': 'X', 'connector_type': 'rest_api',
        'base_url': '', 'auth_method': 'none', 'auth_secret_hash': '',
        'is_active': False, 'description': '',
    })
    assert r.status_code in (302, 301)
    assert not M.Connector.objects.filter(name='X').exists()
