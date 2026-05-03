"""Security tests: RBAC matrix, multi-tenant IDOR, anonymous redirects."""
import pytest
from django.urls import reverse

from apps.inventory import models as inv_models


pytestmark = [pytest.mark.django_db, pytest.mark.security]


# ---------- Anonymous users redirect to login ----------

@pytest.mark.parametrize('name', [
    'inventory:index',
    'inventory:warehouse_list',
    'inventory:grn_list',
    'inventory:movement_list',
])
def test_anonymous_redirect(client, name):
    resp = client.get(reverse(name))
    assert resp.status_code == 302
    assert '/accounts/login/' in resp.url


# ---------- RBAC: admin-only endpoints reject staff ----------

@pytest.mark.parametrize('name,kwargs', [
    ('inventory:warehouse_create', {}),
    ('inventory:zone_create', {}),
    ('inventory:bin_create', {}),
    ('inventory:cc_plan_create', {}),
    ('inventory:adjustment_create', {}),
    ('inventory:lot_create', {}),
    ('inventory:serial_create', {}),
])
def test_staff_cannot_access_admin_create_pages(staff_client, name, kwargs):
    resp = staff_client.get(reverse(name, kwargs=kwargs), follow=False)
    # Mixin redirects with a flash message rather than 403
    assert resp.status_code == 302


def test_staff_cannot_post_adjustment(staff_client, acme, warehouse, bin_a, fg_product):
    from apps.inventory.services.movements import post_movement
    post_movement(
        tenant=acme, movement_type='receipt', product=fg_product,
        qty=10, to_bin=bin_a,
    )
    adj = inv_models.StockAdjustment.objects.create(
        tenant=acme, warehouse=warehouse, reason='damage', reason_notes='x',
    )
    inv_models.StockAdjustmentLine.objects.create(
        tenant=acme, adjustment=adj, bin=bin_a, product=fg_product,
        system_qty=10, actual_qty=8,
    )
    resp = staff_client.post(reverse('inventory:adjustment_post', args=[adj.pk]))
    assert resp.status_code == 302
    adj.refresh_from_db()
    assert adj.status == 'draft'  # not posted


def test_staff_cannot_delete_warehouse(staff_client, acme, warehouse):
    resp = staff_client.post(reverse('inventory:warehouse_delete', args=[warehouse.pk]))
    assert resp.status_code == 302
    assert inv_models.Warehouse.objects.filter(pk=warehouse.pk).exists()


# ---------- Multi-tenant IDOR ----------

def test_cross_tenant_warehouse_detail_404(globex_client, warehouse):
    """Globex user requesting an Acme warehouse must 404, not see data."""
    resp = globex_client.get(reverse('inventory:warehouse_detail', args=[warehouse.pk]))
    assert resp.status_code == 404


def test_cross_tenant_grn_detail_404(globex_client, acme, warehouse):
    grn = inv_models.GoodsReceiptNote.objects.create(tenant=acme, warehouse=warehouse)
    resp = globex_client.get(reverse('inventory:grn_detail', args=[grn.pk]))
    assert resp.status_code == 404


def test_cross_tenant_lot_detail_404(globex_client, acme, fg_product):
    lot = inv_models.Lot.objects.create(tenant=acme, product=fg_product, lot_number='L-X')
    resp = globex_client.get(reverse('inventory:lot_detail', args=[lot.pk]))
    assert resp.status_code == 404


def test_cross_tenant_movement_detail_404(globex_client, acme, fg_product, bin_a):
    from apps.inventory.services.movements import post_movement
    mv = post_movement(
        tenant=acme, movement_type='receipt', product=fg_product,
        qty=1, to_bin=bin_a,
    )
    resp = globex_client.get(reverse('inventory:movement_detail', args=[mv.pk]))
    assert resp.status_code == 404


# ---------- CSRF / GET-blocking on destructive actions ----------

def test_warehouse_delete_get_redirects(admin_client, warehouse):
    """GET on the delete URL should redirect to list, not delete."""
    resp = admin_client.get(reverse('inventory:warehouse_delete', args=[warehouse.pk]))
    assert resp.status_code == 302
    assert inv_models.Warehouse.objects.filter(pk=warehouse.pk).exists()


def test_adjustment_post_via_get_does_nothing(admin_client, acme, warehouse, bin_a, fg_product):
    adj = inv_models.StockAdjustment.objects.create(
        tenant=acme, warehouse=warehouse, reason='damage', reason_notes='x',
    )
    resp = admin_client.get(reverse('inventory:adjustment_post', args=[adj.pk]))
    # View does not implement GET; expect 405 (method not allowed) or 302 — either way no state change
    assert resp.status_code in (302, 405)
    adj.refresh_from_db()
    assert adj.status == 'draft'
