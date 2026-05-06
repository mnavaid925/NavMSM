"""Security-aligned tests: RBAC, multi-tenant IDOR, anonymous redirects."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse


pytestmark = [pytest.mark.django_db, pytest.mark.security]


# ---------- Anonymous redirect ----------

ANON_URLS = [
    'cost:index',
    'cost:version_list',
    'cost:standard_cost_list',
    'cost:actual_cost_list',
    'cost:variance_list',
    'cost:job_list',
    'cost:wip_list',
    'cost:driver_list',
    'cost:pool_list',
    'cost:rate_list',
    'cost:driver_actuals_list',
    'cost:allocation_list',
    'cost:period_list',
    'cost:cogm_list',
    'cost:margin_list',
    'cost:pnl_list',
    'cost:version_compare',
]


@pytest.mark.parametrize('name', ANON_URLS)
def test_anonymous_redirected(client, name):
    r = client.get(reverse(name))
    assert r.status_code in (302, 301)


# ---------- Multi-tenant IDOR ----------

def test_globex_admin_cannot_view_acme_version(globex_client, acme):
    from apps.cost import models as C
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V', effective_from=date(2026, 1, 1),
    )
    r = globex_client.get(reverse('cost:version_detail', args=[v.pk]))
    assert r.status_code == 404


def test_globex_admin_cannot_view_acme_period(globex_client, acp_open):
    r = globex_client.get(reverse('cost:period_detail', args=[acp_open.pk]))
    assert r.status_code == 404


def test_globex_admin_cannot_view_acme_job(globex_client, job):
    r = globex_client.get(reverse('cost:job_detail', args=[job.pk]))
    assert r.status_code == 404


def test_globex_admin_cannot_delete_acme_version(globex_client, acme):
    from apps.cost import models as C
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V', effective_from=date(2026, 1, 1),
    )
    r = globex_client.post(reverse('cost:version_delete', args=[v.pk]))
    assert r.status_code == 404


# ---------- RBAC matrix: admin-only POST endpoints ----------

ADMIN_ONLY_GET_URLS = [
    ('cost:version_create', None),
    ('cost:driver_create', None),
    ('cost:pool_create', None),
    ('cost:rate_create', None),
    ('cost:driver_actuals_create', None),
    ('cost:period_create', None),
    ('cost:job_create', None),
    ('cost:wip_create', None),
    ('cost:variance_create', None),
]


@pytest.mark.parametrize('name,arg', ADMIN_ONLY_GET_URLS)
def test_staff_blocked_from_admin_only_get(staff_client, name, arg):
    args = [arg] if arg is not None else []
    r = staff_client.get(reverse(name, args=args))
    assert r.status_code in (302, 403)


def test_admin_can_load_admin_only(admin_client):
    r = admin_client.get(reverse('cost:version_create'))
    assert r.status_code == 200


def test_staff_blocked_from_period_lock_post(staff_client, acp_open):
    r = staff_client.post(reverse('cost:period_lock', args=[acp_open.pk]),
                          data={'confirm': 'on'})
    # Either 302 (login redirect) or 403 — must NOT mutate
    assert r.status_code in (302, 403)
    acp_open.refresh_from_db()
    assert acp_open.status == 'open'


def test_staff_blocked_from_version_approve(staff_client, acme):
    from apps.cost import models as C
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V', effective_from=date(2026, 1, 1), status='draft',
    )
    r = staff_client.post(reverse('cost:version_approve', args=[v.pk]),
                          data={'notes': 'ok'})
    assert r.status_code in (302, 403)
    v.refresh_from_db()
    assert v.status == 'draft'


# ---------- Workflow gating ----------

def test_cannot_edit_approved_version(admin_client, acme):
    from apps.cost import models as C
    v = C.StandardCostVersion.objects.create(
        tenant=acme, name='V', effective_from=date(2026, 1, 1), status='approved',
    )
    r = admin_client.get(reverse('cost:version_edit', args=[v.pk]))
    # Should redirect with warning
    assert r.status_code in (302, 200)
    if r.status_code == 200:
        # If not redirected, ensure page rendered as detail-like (no edit form)
        assert b'form' not in r.content.lower() or b'cannot' in r.content.lower()


def test_period_close_only_from_locked(admin_client, acp_open):
    r = admin_client.post(reverse('cost:period_close', args=[acp_open.pk]))
    acp_open.refresh_from_db()
    assert acp_open.status == 'open'  # Refused
